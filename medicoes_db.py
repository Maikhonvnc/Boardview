# Caderno de bancada: leituras de tensao e de modo diodo, gravadas em disco e so por
# acrescimo. E a fase 1 da plataforma de medicoes (ver PLATAFORMA.md).
#
# Por que existe: ate aqui as medicoes viviam so no localStorage do navegador — limpar
# os dados de navegacao, trocar de navegador ou abrir por 'localhost' em vez de
# '127.0.0.1' apagava tudo, e nada dizia quem mediu, em qual OS, em qual condicao.
#
# Regras deste arquivo:
#   - Nada e apagado nem alterado: corrigir uma leitura e gravar outra; apagar e gravar
#     um evento 'retira' que aponta (cancela) para uma medida da MESMA placa e malha.
#   - O servidor so responde depois do COMMIT (WAL + synchronous=FULL). Se ele disse
#     "aceita", esta no disco.
#   - Erro do DADO (texto que nao grava, alvo que nao existe) recusa so aquela leitura,
#     e a recusa fica no banco (tabela recusa). Erro PASSAGEIRO do banco (travado por
#     outro programa, disco cheio) sobe como excecao: o servidor responde 503 e o
#     navegador mantem tudo na fila. Confundir os dois perdia leitura valida.
#   - Cada leitura e identificada pela impressao digital da netlist (fp) + malha crua.
#     So vale fp que o servidor ja viu para AQUELA placa (tabela arquivo), e a malha e
#     conferida contra aquela versao do arquivo.
#   - Uuid gerado no navegador: reenviar a mesma leitura nao duplica (INSERT OR IGNORE).
#   - O espelho JSONL (legivel, um por dia) segue o seq guardado no proprio banco.
import os, sys, re, json, math, sqlite3, hashlib, datetime, threading, csv, io
from paths import BV

DADOS = os.environ.get('BOARDVIEW_DADOS') or os.path.join(BV, 'dados')   # fora das pastas servidas
DRONE = os.path.join(BV, 'digital_viewer', 'build', 'DRONE')
FORMATO = 1
MAX_LOTE = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS leitura (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid        TEXT NOT NULL UNIQUE,
  evento      TEXT NOT NULL CHECK (evento IN ('medida','retira')),
  placa       TEXT NOT NULL,
  fp          TEXT NOT NULL,
  alvo        TEXT NOT NULL,
  tipo        TEXT NOT NULL CHECK (tipo IN ('tensao','diodo')),
  papel       TEXT NOT NULL CHECK (papel IN ('ref','reparo')),
  valor       TEXT,
  valor_num   REAL,
  categoria   TEXT,
  alimentacao TEXT,
  momento     TEXT,
  os          TEXT,
  tecnico     TEXT NOT NULL,
  criado_em   TEXT NOT NULL,
  recebido_em TEXT NOT NULL,
  formato     INTEGER NOT NULL,
  cancela     TEXT
);
CREATE INDEX IF NOT EXISTS leitura_ponto ON leitura(fp, alvo, tipo);
CREATE INDEX IF NOT EXISTS leitura_placa ON leitura(placa);
CREATE TABLE IF NOT EXISTS recusa (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  recebido_em TEXT NOT NULL,
  motivo      TEXT NOT NULL,
  dado        TEXT NOT NULL
);
-- cada versao de arquivo de placa que o servidor ja viu: so um fp daqui e aceito
CREATE TABLE IF NOT EXISTS arquivo (
  placa    TEXT NOT NULL,
  fp       TEXT NOT NULL,
  alvos    TEXT NOT NULL,
  visto_em TEXT NOT NULL,
  PRIMARY KEY (placa, fp)
);
CREATE TABLE IF NOT EXISTS espelho (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  ultimo_seq INTEGER NOT NULL
);
-- bancada (fase 2): ate que seq deste banco o servidor central ja confirmou
CREATE TABLE IF NOT EXISTS sync (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  ultimo_seq INTEGER NOT NULL
);
"""

_trava = threading.Lock()
_cache_placa = {}          # nome real -> (mtime, tamanho, info)
_cache_nomes = (None, {})  # (mtime da pasta, {minusculo: nome real}) — trocado inteiro (threads)

A = re.ASCII
RE_PLACA = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}', A)
RE_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', A)
RE_OS = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._/-]{0,29}', A)
RE_NUM = re.compile(r'-?[0-9]{1,6}(\.[0-9]{1,6})?', A)
RE_FP = re.compile(r'[0-9a-f]{64}', A)
RE_CONTROLE = re.compile(r'[\x00-\x1f\x7f]')


class BancoOcupado(Exception):
    """Erro passageiro do banco: responder 503 e manter a leitura na fila."""


def conectar(pasta=None):
    pasta = pasta or DADOS
    os.makedirs(pasta, exist_ok=True)
    con = sqlite3.connect(os.path.join(pasta, 'medicoes.sqlite3'), timeout=3)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=FULL')
    con.executescript(SCHEMA)
    colunas = {r[1] for r in con.execute('PRAGMA table_info(leitura)')}
    if 'cancela' not in colunas:                    # banco criado antes da coluna existir
        con.execute('ALTER TABLE leitura ADD COLUMN cancela TEXT')
    return con


# --- a placa: impressao digital e alvos validos ---------------------------------
def nome_real(placa):
    """Nome do arquivo como esta no disco, ou None. No Windows 'MINE2' abre mine2.bvr;
    sem isto as leituras iam para uma 'placa' MINE2 que nenhuma lista mostra."""
    global _cache_nomes
    if not isinstance(placa, str) or not RE_PLACA.fullmatch(placa) or '..' in placa:
        return None
    try:
        mt = os.stat(DRONE).st_mtime
    except OSError:
        return None
    if _cache_nomes[0] != mt:
        _cache_nomes = (mt, {f[:-4].lower(): f[:-4] for f in os.listdir(DRONE) if f.lower().endswith('.bvr')})
    return _cache_nomes[1].get(placa.lower())


def info_placa(placa):
    """{placa, fp, n_malhas, alvos:set} do .bvr atual, ou None se a placa nao existe.

    fp = sha256 das linhas 'PECA|PINO|MALHA' do .bvr, ordenadas. Dois arquivos com
    o mesmo conteudo e nomes diferentes dao o mesmo fp; qualquer mudanca na netlist
    muda o fp. Alvos validos: toda malha crua, mais 'PECA.PINO' dos pinos sem malha
    (NC), que nao sao ligados entre si e por isso nao podem ser chaveados pela malha."""
    real = nome_real(placa)
    if real is None:
        return None
    caminho = os.path.join(DRONE, real + '.bvr')
    try:
        st = os.stat(caminho)
    except OSError:
        return None
    c = _cache_placa.get(real)
    if c and c[0] == st.st_mtime and c[1] == st.st_size:
        return c[2]
    linhas, malhas, nc = [], set(), set()
    peca = pino = None
    with open(caminho, encoding='utf-8', errors='replace') as f:
        for ln in f:
            s = ln.strip()
            if s.startswith('PART_NAME '):
                peca = s.split(None, 1)[1]
            elif s.startswith('PIN_NUMBER '):
                pino = s.split(None, 1)[1]
            elif s.startswith('PIN_NET'):
                rede = s.split(None, 1)[1] if ' ' in s else ''
                linhas.append(f'{peca}|{pino}|{rede}')
                if rede and rede != 'NC':
                    malhas.add(rede)
                else:
                    nc.add(f'{peca}.{pino}')
    fp = hashlib.sha256('\n'.join(sorted(linhas)).encode('utf-8')).hexdigest()
    info = {'placa': real, 'fp': fp, 'n_malhas': len(malhas), 'alvos': malhas | nc}
    _cache_placa[real] = (st.st_mtime, st.st_size, info)
    return info


def _registrar_versao(con, info, agora):
    """Guarda a versao atual do arquivo (fp + alvos) para aceitar leituras feitas nela
    mesmo depois de o .bvr ser trocado."""
    con.execute('INSERT OR IGNORE INTO arquivo (placa, fp, alvos, visto_em) VALUES (?,?,?,?)',
                (info['placa'], info['fp'], json.dumps(sorted(info['alvos'])), agora))


# --- validacao de uma leitura ---------------------------------------------------
def _texto(x, maximo):
    """Texto aceitavel: tamanho, sem caractere de controle e que codifica em UTF-8 (um
    emoji cortado ao meio deixa um 'surrogate' solto, que o SQLite nao grava)."""
    if not (isinstance(x, str) and 0 < len(x) <= maximo and not RE_CONTROLE.search(x)):
        return False
    try:
        x.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def _data_ok(s):
    if not (isinstance(s, str) and len(s) <= 30):
        return False
    try:
        datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False


def validar(d, agora=None, alvos_da_versao=None):
    """(linha pronta para o banco, None) ou (None, motivo).

    alvos_da_versao(placa, fp) -> set de alvos de uma versao ANTERIOR ja vista do
    arquivo, ou None. Sem ela (uso direto), so o fp atual e aceito."""
    if not isinstance(d, dict):
        return None, 'leitura tem que ser um objeto'
    u = d.get('uuid')
    if not (isinstance(u, str) and RE_UUID.fullmatch(u)):
        return None, 'uuid invalido'
    evento = d.get('evento', 'medida')
    if evento not in ('medida', 'retira'):
        return None, 'evento invalido'
    tipo, papel = d.get('tipo'), d.get('papel')
    if tipo not in ('tensao', 'diodo'):
        return None, 'tipo invalido'
    if papel not in ('ref', 'reparo'):
        return None, 'papel invalido'
    info = info_placa(d.get('placa'))
    if info is None:
        return None, 'placa desconhecida'
    alvo = d.get('alvo')
    if not _texto(alvo, 120):
        return None, 'alvo invalido'
    fp = d.get('fp') or info['fp']
    if not (isinstance(fp, str) and RE_FP.fullmatch(fp)):
        return None, 'fp invalido'
    if fp == info['fp']:
        alvos = info['alvos']
    else:
        alvos = alvos_da_versao(info['placa'], fp) if alvos_da_versao else None
        if alvos is None:
            return None, 'fp desconhecido para esta placa'
    if alvo not in alvos:
        return None, 'alvo nao existe nesta placa'
    tecnico = d.get('tecnico')
    if not _texto(tecnico, 40):
        return None, 'tecnico invalido'
    os_ = d.get('os') or None
    if os_ is not None and not (isinstance(os_, str) and RE_OS.fullmatch(os_)):
        return None, 'OS invalida'
    criado = d.get('criado_em')
    if not _data_ok(criado):
        return None, 'criado_em invalido'

    valor = valor_num = categoria = cancela = None
    if evento == 'medida':
        v = d.get('valor')
        if not (isinstance(v, str) and len(v) <= 16):
            return None, 'valor invalido'
        v = v.strip().replace(',', '.').upper()
        if tipo == 'diodo' and v == 'OL':
            valor, categoria = 'OL', 'OL'
        elif RE_NUM.fullmatch(v) and abs(float(v)) < 1000:
            valor_num = float(v)
            valor, categoria = repr(valor_num), 'num'   # '00000.5' e '0.50' viram '0.5'
        else:
            return None, 'valor invalido'
        if tipo == 'diodo' and valor_num is not None and valor_num < 0:
            return None, 'diodo negativo'
    else:
        cancela = d.get('cancela')
        if not (isinstance(cancela, str) and RE_UUID.fullmatch(cancela)):
            return None, 'retira sem a medida que ele cancela'

    alimentacao = momento = None
    if tipo == 'tensao':
        alimentacao = d.get('alimentacao')
        momento = d.get('momento')
        if alimentacao not in ('fonte', 'bateria'):
            return None, 'alimentacao invalida'
        if momento not in ('estavel', 'boot'):
            return None, 'momento invalido'

    agora = agora or datetime.datetime.now().isoformat(timespec='seconds')
    return {'uuid': u, 'evento': evento, 'placa': info['placa'], 'fp': fp, 'alvo': alvo,
            'tipo': tipo, 'papel': papel, 'valor': valor, 'valor_num': valor_num,
            'categoria': categoria, 'alimentacao': alimentacao, 'momento': momento,
            'os': os_, 'tecnico': tecnico, 'criado_em': criado, 'recebido_em': agora,
            'formato': FORMATO, 'cancela': cancela}, None


COLUNAS = ('uuid', 'evento', 'placa', 'fp', 'alvo', 'tipo', 'papel', 'valor', 'valor_num',
           'categoria', 'alimentacao', 'momento', 'os', 'tecnico', 'criado_em',
           'recebido_em', 'formato', 'cancela')
_SQL_INSERIR = (f'INSERT OR IGNORE INTO leitura ({",".join(COLUNAS)}) '
                f'VALUES ({",".join("?" * len(COLUNAS))})')
_ERRO_DO_DADO = (sqlite3.IntegrityError, sqlite3.InterfaceError, sqlite3.DataError,
                 sqlite3.ProgrammingError, UnicodeError)


def _cancela_valido(con, linha, novas):
    """O 'retira' tem que apontar para uma medida da MESMA placa, fp, malha, tipo e
    papel — no banco ou mais cedo neste mesmo lote."""
    chave = (linha['placa'], linha['fp'], linha['alvo'], linha['tipo'], linha['papel'])
    for n in novas:
        if n['uuid'] == linha['cancela'] and n['evento'] == 'medida' and \
                (n['placa'], n['fp'], n['alvo'], n['tipo'], n['papel']) == chave:
            return True
    return con.execute('SELECT 1 FROM leitura WHERE uuid=? AND evento=\'medida\' AND placa=? '
                       'AND fp=? AND alvo=? AND tipo=? AND papel=?',
                       (linha['cancela'],) + chave).fetchone() is not None


def _espelhar(con, pasta):
    """Acrescenta ao JSONL do dia toda linha com seq maior que a ultima espelhada (o
    seq fica no proprio banco). Falhar aqui nao perde nada: o banco tem a linha e o
    proximo envio completa."""
    r = con.execute('SELECT ultimo_seq FROM espelho WHERE id=1').fetchone()
    ultimo = r[0] if r else 0
    con.row_factory = sqlite3.Row
    linhas = con.execute('SELECT * FROM leitura WHERE seq > ? ORDER BY seq', (ultimo,)).fetchall()
    con.row_factory = None
    if not linhas:
        return
    por_dia = {}
    for x in linhas:
        por_dia.setdefault(x['recebido_em'][:10], []).append(dict(x))
    for dia, rs in por_dia.items():
        with open(os.path.join(pasta, f'leituras-{dia}.jsonl'), 'a', encoding='utf-8') as f:
            for x in rs:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    with con:
        con.execute('INSERT INTO espelho (id, ultimo_seq) VALUES (1, ?) '
                    'ON CONFLICT(id) DO UPDATE SET ultimo_seq=excluded.ultimo_seq', (linhas[-1]['seq'],))


def inserir(leituras, pasta=None):
    """Grava um lote. Devolve {aceitas:[uuid], rejeitadas:[{uuid, motivo}]}.

    'aceitas' inclui as que ja estavam no banco (reenvio): para o navegador, as duas
    querem dizer "pode tirar da fila". 'rejeitadas' tambem podem sair da fila: a recusa
    fica guardada na tabela recusa. ValueError = lote invalido (400); BancoOcupado =
    erro passageiro (503, a fila mantem tudo)."""
    if not isinstance(leituras, list) or not leituras:
        raise ValueError('lote vazio')
    if len(leituras) > MAX_LOTE:
        raise ValueError(f'no maximo {MAX_LOTE} leituras por envio')
    pasta = pasta or DADOS
    agora = datetime.datetime.now().isoformat(timespec='seconds')
    with _trava:
        try:
            con = conectar(pasta)
        except sqlite3.OperationalError as e:
            raise BancoOcupado(str(e))
        try:
            try:
                with con:
                    for d in leituras:                       # versao atual de cada placa
                        info = info_placa(d.get('placa')) if isinstance(d, dict) else None
                        if info:
                            _registrar_versao(con, info, agora)

                def versao(placa, fp):
                    r = con.execute('SELECT alvos FROM arquivo WHERE placa=? AND fp=?', (placa, fp)).fetchone()
                    return set(json.loads(r[0])) if r else None

                boas, rejeitadas, recusas = [], [], []
                for d in leituras:
                    linha, motivo = validar(d, agora, versao)
                    if not motivo and linha['evento'] == 'retira' and not _cancela_valido(con, linha, boas):
                        motivo = 'retira aponta para medida que nao existe nesta placa/malha'
                    if motivo:
                        u = d.get('uuid') if isinstance(d, dict) else None
                        u = u if isinstance(u, str) and RE_UUID.fullmatch(u) else None
                        rejeitadas.append({'uuid': u, 'motivo': motivo})
                        recusas.append((d, motivo))
                    else:
                        boas.append(linha)
                try:
                    with con:
                        for linha in boas:
                            con.execute(_SQL_INSERIR, [linha[c] for c in COLUNAS])
                except _ERRO_DO_DADO:
                    # algo escapou da validacao: grava uma a uma e recusa so as que falham
                    gravadas = []
                    for linha in boas:
                        try:
                            with con:
                                con.execute(_SQL_INSERIR, [linha[c] for c in COLUNAS])
                            gravadas.append(linha)
                        except _ERRO_DO_DADO as e:
                            motivo = 'nao gravou: ' + type(e).__name__
                            rejeitadas.append({'uuid': linha['uuid'], 'motivo': motivo})
                            recusas.append((linha, motivo))
                    boas = gravadas
                if recusas:
                    with con:
                        for dado, motivo in recusas:
                            con.execute('INSERT INTO recusa (recebido_em, motivo, dado) VALUES (?,?,?)',
                                        (agora, motivo, json.dumps(dado, ensure_ascii=True, default=str)[:20000]))
            except sqlite3.OperationalError as e:            # travado, disco cheio, I/O
                raise BancoOcupado(str(e))
            try:
                _espelhar(con, pasta)
            except Exception as e:                           # o banco ja tem as linhas
                print(f'[caderno] espelho JSONL atrasado: {e}', file=sys.stderr)
        finally:
            con.close()
    return {'aceitas': [l['uuid'] for l in boas], 'rejeitadas': rejeitadas}


def listar(placa, pasta=None, limite=5000):
    """Leituras da placa, mais novas primeiro. limite=None traz todas (o consenso precisa)."""
    real = nome_real(placa) or placa
    con = conectar(pasta)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM leitura WHERE placa=? ORDER BY seq DESC LIMIT ?',
                           (real, -1 if limite is None else limite)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# --- sincronizacao bancada -> central (fase 2) -------------------------------------
# A bancada manda ao central, em ordem de seq, as linhas que ele ainda nao confirmou.
# Reenviar nao duplica (o uuid e o mesmo). O ponteiro so anda quando o central
# RESPONDEU o lote (aceitas + rejeitadas — a recusa fica gravada la, com o dado inteiro).
CAMPOS_ENVIO = ('uuid', 'evento', 'placa', 'fp', 'alvo', 'tipo', 'papel', 'valor',
                'alimentacao', 'momento', 'os', 'tecnico', 'criado_em', 'cancela')


def pendentes_sync(pasta=None, limite=MAX_LOTE):
    """[(seq, leitura pronta para o POST)] ainda nao confirmadas pelo central."""
    con = conectar(pasta)
    try:
        r = con.execute('SELECT ultimo_seq FROM sync WHERE id=1').fetchone()
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM leitura WHERE seq > ? ORDER BY seq LIMIT ?',
                           (r[0] if r else 0, limite)).fetchall()
        return [(x['seq'], {c: x[c] for c in CAMPOS_ENVIO if x[c] is not None}) for x in rows]
    finally:
        con.close()


def marcar_sync(seq, pasta=None):
    """O central respondeu ate este seq: avanca o ponteiro (nunca volta)."""
    con = conectar(pasta)
    try:
        with con:
            con.execute('INSERT INTO sync (id, ultimo_seq) VALUES (1, ?) ON CONFLICT(id) '
                        'DO UPDATE SET ultimo_seq=MAX(ultimo_seq, excluded.ultimo_seq)', (seq,))
    finally:
        con.close()


def reiniciar_sync(pasta=None):
    """Faz a bancada mandar TUDO de novo ao central (ex.: o central voltou de um backup e
    perdeu as leituras mais novas). Nao duplica: o central ignora uuid repetido."""
    con = conectar(pasta)
    try:
        with con:
            con.execute('DELETE FROM sync')
    finally:
        con.close()


def backup_para(destino, pasta=None):
    """Copia consistente do banco (API de backup do SQLite: certa mesmo com o WAL e com
    gente gravando). A copia sai num arquivo so, sem -wal/-shm."""
    con = conectar(pasta)
    try:
        dst = sqlite3.connect(destino)
        try:
            con.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
        finally:
            dst.close()
    finally:
        con.close()


def conferir_copia(arquivo):
    """Restauracao de teste: abre a copia, confere a integridade e calcula o consenso de
    todas as placas, como o servidor faria. Levanta erro se algo falhar."""
    import consenso
    con = sqlite3.connect(arquivo)
    try:
        ok = con.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise ValueError(f'copia com defeito: {ok}')
        con.row_factory = sqlite3.Row
        linhas = [dict(r) for r in con.execute('SELECT * FROM leitura ORDER BY seq')]
    finally:
        con.close()
    por_placa = {}
    for l in linhas:
        por_placa.setdefault(l['placa'], []).append(l)
    pontos = sum(len(alvos) for ls in por_placa.values() for alvos in consenso.por_placa(ls).values())
    return {'leituras': len(linhas), 'placas': len(por_placa), 'pontos_com_voto': pontos}


def backup(pasta_destino, manter=30, pasta=None):
    """Backup do servidor central (systemd timer): copia, confere e guarda as 'manter'
    mais novas. Devolve (arquivo, resultado da conferencia)."""
    os.makedirs(pasta_destino, exist_ok=True)
    carimbo = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
    alvo = os.path.join(pasta_destino, f'medicoes-{carimbo}.sqlite3')
    tmp = alvo + '.conferindo'
    backup_para(tmp, pasta)
    try:
        r = conferir_copia(tmp)
    except Exception:
        os.remove(tmp)
        raise
    os.replace(tmp, alvo)
    for velho in sorted(f for f in os.listdir(pasta_destino)
                        if f.startswith('medicoes-') and f.endswith('.sqlite3'))[:-manter]:
        os.remove(os.path.join(pasta_destino, velho))
    return alvo, r


def situacao_sync(pasta=None):
    """{enviadas, faltam} para o status do painel."""
    con = conectar(pasta)
    try:
        r = con.execute('SELECT ultimo_seq FROM sync WHERE id=1').fetchone()
        ultimo = r[0] if r else 0
        faltam = con.execute('SELECT COUNT(*) FROM leitura WHERE seq > ?', (ultimo,)).fetchone()[0]
        return {'ultimo_seq': ultimo, 'faltam': faltam}
    finally:
        con.close()


def exportar_csv(placa=None, pasta=None):
    real = (nome_real(placa) or placa) if placa else None
    con = conectar(pasta)
    try:
        sql = f'SELECT {",".join(("seq",) + COLUNAS)} FROM leitura'
        rows = con.execute(sql + (' WHERE placa=?' if real else '') + ' ORDER BY seq',
                           (real,) if real else ()).fetchall()
    finally:
        con.close()
    # texto digitado que comeca com = + - @ vira formula ao abrir no Excel: um apostrofo
    # na frente faz ele aparecer como texto (so nas colunas de texto livre)
    livres = {i + 1 for i, c in enumerate(COLUNAS) if c in ('tecnico', 'os', 'alvo')}
    def celula(i, x):
        return "'" + x if i in livres and isinstance(x, str) and x.lstrip()[:1] in ('=', '+', '-', '@') else x
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')                   # ';' abre direto no Excel em pt-BR
    w.writerow(('seq',) + COLUNAS)
    w.writerows([celula(i, x) for i, x in enumerate(r)] for r in rows)
    return buf.getvalue()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'csv':
        sys.stdout.write(exportar_csv(sys.argv[2] if len(sys.argv) > 2 else None))
    elif cmd == 'backup' and len(sys.argv) > 2:
        arq, r = backup(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
        print(f'{arq}: {r["leituras"]} leituras, {r["placas"]} placas, conferido')
    elif cmd == 'conferir' and len(sys.argv) > 2:
        print(conferir_copia(sys.argv[2]))
    elif cmd == 'reenviar':
        reiniciar_sync()
        print(f'ok: as {situacao_sync()["faltam"]} leituras deste PC vao de novo ao central '
              '(com o servidor desta bancada aberto)')
    else:
        print('uso: python medicoes_db.py csv [placa]          exporta o caderno em CSV\n'
              '     python medicoes_db.py backup PASTA [N]     copia conferida, guarda as N mais novas (30)\n'
              '     python medicoes_db.py conferir ARQUIVO     restauracao de teste de uma copia\n'
              '     python medicoes_db.py reenviar             bancada: manda tudo de novo ao central')
