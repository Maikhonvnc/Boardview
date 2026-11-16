# Servidor local do hub+viewer. Serve a pasta Boardview e mapeia /_drones/ para
# a pasta de dados das placas (paths.DRONES), que fica fora do repo.
#
# SEGURANCA. Ate out/2026 ele servia QUALQUER arquivo do disco ('/C:/Windows/win.ini'
# ou '..%2F' saiam da pasta, porque o os.path.join aceita caminho absoluto e nada
# conferia o resultado) e gravava ajuste vindo de qualquer site. Agora:
#   - so serve o que esta na LISTA BRANCA abaixo (o que o HUB e os viewers usam);
#   - o caminho final e conferido com commonpath dentro da pasta certa;
#   - nao lista pastas (exceto PDFs-Drone, que o HUB abre como pasta);
#   - so atende os nomes de host esperados — isso barra o "DNS rebinding", em que
#     um site faz o navegador falar com 127.0.0.1 achando que e ele mesmo;
#   - o POST exige JSON, mesma origem e placa existente, e valida campo a campo.
# Ao levar isto para o servidor da empresa: ponha o nome/IP de la em
# BOARDVIEW_HOSTS (ex.: set BOARDVIEW_HOSTS=bancada.local:8777,10.0.0.5:8777).
#
# DOIS PAPEIS (fase 2, ver PLATAFORMA.md e servidor-central/LEIAME.md):
#   - central: o servidor da empresa. Guarda as leituras de todos e calcula o consenso.
#   - bancada: o PC do tecnico. Grava local (funciona sem rede) e uma thread manda as
#     leituras novas ao central; o consenso vem do central (com copia local p/ offline)
#     e uma vez por dia baixa uma copia do banco central. Vira bancada quando tem o
#     endereco do central em BOARDVIEW_CENTRAL ou no arquivo central.txt.
import http.server, socketserver, os, sys, re, json, math, shutil, posixpath, urllib.parse
import urllib.request, urllib.error, threading, datetime, tempfile
from paths import BV, DRONES
import medicoes_db as MDB          # caderno de bancada: /api/leituras (fase 1, ver PLATAFORMA.md)
import consenso                    # regra do "validado por N" (fase 2)
import anotacoes as ANOT           # classificacao/nomes por placa (dados/anotacoes)

PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8777   # 'python servidor.py 8788' p/ testar noutra porta

HOSTS = {f'127.0.0.1:{PORTA}', f'localhost:{PORTA}'} | {
    h.strip().lower() for h in os.environ.get('BOARDVIEW_HOSTS', '').split(',') if h.strip()}


def _ler_central():
    """Endereco do central (so esquema + host[:porta]) ou '' (este e o central / sozinho)."""
    url = os.environ.get('BOARDVIEW_CENTRAL', '').strip()
    if not url:
        try:
            with open(os.path.join(BV, 'central.txt'), encoding='utf-8-sig') as f:
                url = f.readline().strip()
        except OSError:
            return ''
    url = url.rstrip('/')
    if url and not re.fullmatch(r'https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?', url):
        print(f'AVISO: endereco do central invalido ({url[:80]!r}); sincronizacao desligada.')
        return ''
    return url

CENTRAL = _ler_central()

# O que pode ser servido, relativo a pasta Boardview, comparado em minusculas
# (no Windows 'MINE2_DB.HTML' e 'mine2_db.html' sao o mesmo arquivo).
ARQUIVOS = {'hub.html', 'viewer.html', 'favicon.ico'}
PASTAS = ('thumbs/', 'boards/', 'malhas/', 'cadernos/', 'netlists/', 'pdfs-drone/',
          'digitalboard/pdf/',      # so os PDFs: as paginas raspadas do DigitalBoard rodam script de terceiro
          'digital_viewer/assets/', 'digital_viewer/build/')
LISTAVEIS = ('pdfs-drone',)       # pastas que o HUB abre como pasta
VIEWER = 'digital_viewer/'        # arquivos soltos do viewer: so .html/.js de primeiro nivel...
VIEWER_FORA = {'digital_viewer/mine2_db.html'}   # ...menos este, que carrega SCRIPT3.js de bizoonydb.github.io


def _dentro(base, alvo):
    base = os.path.normcase(os.path.realpath(base))
    alvo = os.path.normcase(os.path.realpath(alvo))
    try:
        return os.path.commonpath([base, alvo]) == base
    except ValueError:                       # drives diferentes no Windows
        return False


def _rel(caminho_url):
    """Caminho da URL -> relativo e normalizado, ou None se for suspeito."""
    p = urllib.parse.unquote(caminho_url.split('?', 1)[0].split('#', 1)[0])
    # barra invertida, NUL, ':' (drive 'C:' ou fluxo alternativo '::$DATA') — nada
    # disso aparece em nome de arquivo legitimo do projeto
    if '\\' in p or '\x00' in p or ':' in p:
        return None
    rel = posixpath.normpath('/' + p).lstrip('/')   # '/../x' normaliza para '/x'
    return None if rel.startswith('..') else rel


def resolver(caminho_url):
    """URL -> caminho no disco, ou None se nao pode ser servido."""
    rel = _rel(caminho_url)
    if not rel or rel == '.':
        return None
    baixo = rel.lower()
    if baixo.startswith('_drones/'):
        alvo = os.path.join(DRONES, rel[len('_drones/'):])
        return alvo if _dentro(DRONES, alvo) else None
    permitido = (baixo in ARQUIVOS
                 or any(baixo == d.rstrip('/') or baixo.startswith(d) for d in PASTAS)
                 or (baixo.startswith(VIEWER) and '/' not in baixo[len(VIEWER):]
                     and baixo.endswith(('.html', '.js')) and baixo not in VIEWER_FORA))
    if not permitido:
        return None
    alvo = os.path.join(BV, rel)
    return alvo if _dentro(BV, alvo) else None


# --- validacao do ajuste da foto ------------------------------------------------
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

LIMITES = {'dx': 1e5, 'dy': 1e5, 'rot': 1e3}     # deslocamento (unidades da placa) e giro

# --- anotacoes do modo Classificar: o armazenamento e a validacao estao em anotacoes.py;
# aqui fica so a parte de rede da bancada (buscar do central, levar a fila).
def _do_central(placa):
    """Anotacoes da placa no central (so as secoes conhecidas). Na 1a vez que esta bancada
    fala com ele sobre a placa, poe na fila o que so existe aqui (ANOT.primeiro_contato)."""
    dado = _central('/api/anotacoes/' + urllib.parse.quote(placa), timeout=6)
    if not isinstance(dado, dict):
        raise ValueError('resposta do central sem anotacoes')
    dado = {s: dict(dado[s]) for s in ANOT.SECOES if isinstance(dado.get(s), dict)}
    ANOT.primeiro_contato(placa, dado)
    return dado


def anotacoes_da_placa(placa):
    """Na bancada: as do central, por cima as daqui que ainda nao chegaram la (guardando
    copia); central fora -> a ultima copia. No central ou sozinho: o arquivo local."""
    if CENTRAL:
        try:
            dado = ANOT.substituir(placa, ANOT.aplicar(_do_central(placa), ANOT.pendentes(placa)))
            return dict(dado, origem='central')
        except Exception:
            pass
    return dict(ANOT.ler(placa), origem='copia' if CENTRAL else 'local')


def sincronizar_anotacoes():
    """Leva ao central as classificacoes/nomes feitos nesta bancada. Uma mudanca que o
    central RECUSA (versao diferente do programa, por exemplo) sai da fila e fica em
    dados/anotacoes/recusadas-<placa>.json — nao trava as outras para sempre."""
    for placa in ANOT.placas():
        if ANOT.falta_primeiro_contato(placa):
            _do_central(placa)
    total = 0
    for placa in ANOT.placas_pendentes():
        pend = ANOT.pendentes(placa)[:5000]
        if not pend:
            continue
        caminho = '/api/anotacoes/' + urllib.parse.quote(placa)
        try:
            r = _central(caminho, {'mudancas': pend}, timeout=30)
            for x in (r.get('recusadas') or []) if isinstance(r, dict) else []:
                if isinstance(x, dict) and isinstance(x.get('i'), int) and 0 <= x['i'] < len(pend):
                    ANOT.recusar(placa, pend[x['i']], x.get('motivo'))
        except urllib.error.HTTPError as e:
            if e.code not in (400, 413):
                raise
            for m in pend:                             # central antigo recusa o lote: isola a ruim
                try:
                    _central(caminho, {'mudancas': [m]}, timeout=20)
                except urllib.error.HTTPError as e1:
                    if e1.code not in (400, 413):
                        raise
                    ANOT.recusar(placa, m, f'central respondeu {e1.code}: {e1.reason}')
                    print(f'[sync] central recusou anotacao de {placa}: {m[:2]}', file=sys.stderr)
        ANOT.entregues(placa, len(pend))
        total += len(pend)
    return total


def validar_ajuste(placa, dados):
    """(dict limpo, None) ou (None, motivo). So guarda as chaves DESTA placa: o
    viewer manda tudo o que tem no navegador, inclusive ajuste de outras placas,
    e gravar isso aqui espalhava ajuste velho entre os arquivos."""
    if not isinstance(dados, dict):
        return None, 'esperava um objeto JSON'
    limpo = {}
    for k, v in dados.items():
        if k == 'troca|' + placa:
            if v is not True:
                return None, f'{k} tem que ser true'
            limpo[k] = True
            continue
        pre, _, n = k.rpartition('|')
        if pre != placa:
            continue                          # ajuste de outra placa: descarta
        if not (n.isdigit() and int(n) <= 9) or not isinstance(v, dict):
            return None, f'chave invalida: {k[:60]}'
        a = {}
        for c, x in v.items():
            if c in ('fh', 'fv'):
                if not isinstance(x, bool):
                    return None, f'{k}.{c} tem que ser true/false'
                a[c] = x
            elif c in LIMITES:
                if not _num(x) or abs(x) > LIMITES[c]:
                    return None, f'{k}.{c} fora do limite'
                a[c] = float(x)
            elif c in ('sx', 'sy'):
                if not _num(x) or not (0.01 < x < 100):
                    return None, f'{k}.{c} fora do limite'
                a[c] = float(x)
            else:
                return None, f'campo desconhecido: {c[:30]}'
        limpo[k] = a
    return limpo, None


# --- fase 2: consenso, sincronizacao com o central, copia do banco --------------------
_SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # tailnet: direto
_acordar_sync = threading.Event()
_sync = {'ok_em': None, 'erro': None, 'copia': None, 'erro_copia': None, 'erro_anotacoes': None,
         'recusadas': 0, 'recusa_motivo': None}   # recusadas: desde que este servidor subiu
_trava_ajuste = threading.Lock()      # com threads, dois POST /ajuste nao gravam juntos
COPIAS_CENTRAL = 14                   # dias de copia do banco central guardados em cada PC


def _agora():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _gravar_atomico(alvo, dado):
    """Grava inteiro num temporario com nome unico e troca: quem le nunca ve meio arquivo."""
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(alvo), suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(dado)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, alvo)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _central(caminho, corpo=None, timeout=8, maximo=2_000_000, cru=False):
    """GET (sem corpo) ou POST JSON ao central. Devolve o JSON (ou os bytes, se cru)."""
    u = urllib.parse.urlsplit(CENTRAL)
    cab = {'Accept': 'application/json'}
    dado = None
    if corpo is not None:
        dado = json.dumps(corpo).encode('utf-8')
        # o central so aceita POST JSON "da mesma origem" — a origem e ele mesmo
        cab.update({'Content-Type': 'application/json', 'Origin': f'{u.scheme}://{u.netloc}'})
    with _SEM_PROXY.open(urllib.request.Request(CENTRAL + caminho, data=dado, headers=cab),
                         timeout=timeout) as r:
        bruto = r.read(maximo + 1)
    if len(bruto) > maximo:
        raise ValueError('resposta do central grande demais')
    return bruto if cru else json.loads(bruto.decode('utf-8'))


def consenso_local(info):
    """Consenso calculado do banco DESTE servidor (no central: o de todos)."""
    return {'placa': info['placa'], 'fp': info['fp'], 'origem': 'local', 'calculado_em': _agora(),
            # o viewer usa a MESMA tolerancia para dizer se a placa da bancada esta fora
            'tolerancia': {'diodo': list(consenso.TOL_DIODO), 'tensao': list(consenso.TOL_TENSAO)},
            'versoes': consenso.por_placa(MDB.listar(info['placa'], limite=None))}


def consenso_da_placa(info):
    """Na bancada: o do central (guardando copia); central fora -> a copia; sem copia ->
    o das leituras deste PC, avisando. No central (ou sozinho): o local."""
    if not CENTRAL:
        return consenso_local(info)
    copia = os.path.join(MDB.DADOS, 'consenso', info['placa'] + '.json')
    try:
        dado = _central('/api/consenso?placa=' + urllib.parse.quote(info['placa']), timeout=4)
        if not (isinstance(dado, dict) and isinstance(dado.get('versoes'), dict)):
            raise ValueError('resposta sem versoes')
        dado['origem'] = 'central'
        _gravar_atomico(copia, json.dumps(dado, ensure_ascii=False).encode('utf-8'))
        return dado
    except Exception:
        pass
    try:
        with open(copia, encoding='utf-8') as f:
            dado = json.load(f)
        dado.update(origem='copia', aviso='central fora: consenso da ultima vez que ele respondeu')
        return dado
    except (OSError, ValueError):
        return dict(consenso_local(info), aviso='central fora e sem copia: so as leituras deste PC')


def sincronizar():
    """Manda ao central, em lotes e em ordem, tudo o que ele ainda nao confirmou.
    Devolve quantas foram. Qualquer falha sobe (o ponteiro nao anda)."""
    total = 0
    while True:
        pend = MDB.pendentes_sync()
        if not pend:
            return total
        r = _central('/api/leituras', {'leituras': [d for _, d in pend]}, timeout=20)
        if not (isinstance(r, dict) and isinstance(r.get('aceitas'), list)
                and isinstance(r.get('rejeitadas'), list)
                and len(r['aceitas']) + len(r['rejeitadas']) == len(pend)):
            raise ValueError('resposta do central nao confere com o lote')
        if r['rejeitadas']:
            # Ficou gravada na tabela recusa do central, com o dado inteiro, mas NAO entrou
            # no caderno de la. O ponteiro anda (senao a fila travava para sempre), entao a
            # bancada tem que DIZER: antes o painel mostrava "central em dia" e o voto sumia
            # em silencio. Causa tipica: .bvr deste PC diferente do do central. Depois de
            # igualar os programas: python medicoes_db.py reenviar.
            motivos = {}
            for x in r['rejeitadas']:
                print(f'[sync] central recusou {x.get("uuid")}: {x.get("motivo")}', file=sys.stderr)
                motivos[str(x.get('motivo'))[:80]] = motivos.get(str(x.get('motivo'))[:80], 0) + 1
            _sync['recusadas'] = (_sync.get('recusadas') or 0) + len(r['rejeitadas'])
            _sync['recusa_motivo'] = max(motivos, key=motivos.get)
            try:
                with open(os.path.join(MDB.DADOS, 'recusadas-pelo-central.jsonl'), 'a', encoding='utf-8') as f:
                    for x in r['rejeitadas']:
                        f.write(json.dumps({'em': _agora(), 'uuid': x.get('uuid'), 'motivo': x.get('motivo')},
                                           ensure_ascii=False) + chr(10))
            except OSError:
                pass
        MDB.marcar_sync(pend[-1][0])
        total += len(pend)


def copiar_banco_central():
    """Baixa o banco do central, faz a restauracao de teste (abre a copia, confere a
    integridade e calcula o consenso) e so entao guarda. E o "backup em cada PC": um
    arquivo por dia (os ultimos COPIAS_CENTRAL), refeito a cada 6 h — senao a copia do dia
    era a de quando o PC ligou, antes das medicoes daquele dia."""
    pasta = os.path.join(MDB.DADOS, 'copia-central')
    alvo = os.path.join(pasta, f'medicoes-central-{datetime.date.today().isoformat()}.sqlite3')
    try:
        if datetime.datetime.now().timestamp() - os.path.getmtime(alvo) < 6 * 3600:
            return None
    except OSError:
        pass                                          # ainda nao tem a de hoje
    bruto = _central('/api/backup', timeout=120, maximo=300_000_000, cru=True)
    os.makedirs(pasta, exist_ok=True)
    tmp = alvo + '.conferindo'
    with open(tmp, 'wb') as f:
        f.write(bruto)
    try:
        r = MDB.conferir_copia(tmp)
    except Exception:
        os.remove(tmp)
        raise
    os.replace(tmp, alvo)
    for velho in sorted(f for f in os.listdir(pasta)
                        if f.startswith('medicoes-central-') and f.endswith('.sqlite3'))[:-COPIAS_CENTRAL]:
        os.remove(os.path.join(pasta, velho))
    return dict(r, arquivo=os.path.basename(alvo))


def _laco_sync():
    """Thread da bancada. Acorda a cada 30 s ou logo depois de uma leitura nova; com o
    central fora, espera cada vez mais (ate 5 min) para nao martelar."""
    espera = 30
    while True:
        _acordar_sync.clear()
        try:
            n = sincronizar()
            _sync.update(ok_em=_agora(), erro=None)
            if n:
                print(f'[sync] {n} leitura(s) entregue(s) ao central')
            espera = 30
            try:                        # separado: um problema aqui nao segura o caderno nem a copia
                a = sincronizar_anotacoes()
                _sync['erro_anotacoes'] = None
                if a:
                    print(f'[sync] {a} classificacao(oes)/nome(s) entregue(s) ao central')
            except Exception as e:
                _sync['erro_anotacoes'] = f'{type(e).__name__}: {str(e)[:150]}'
            try:
                c = copiar_banco_central()
                if c:
                    _sync.update(copia=c, erro_copia=None)
                    print(f'[sync] copia do banco central conferida: {c["leituras"]} leituras')
            except Exception as e:
                _sync['erro_copia'] = f'{type(e).__name__}: {str(e)[:150]}'
        except urllib.error.HTTPError as e:
            dica = ' (confira BOARDVIEW_HOSTS no central)' if e.code in (403, 421) else ''
            _sync['erro'] = f'central respondeu {e.code}{dica}'
            espera = min(espera * 2, 300)
        except Exception as e:
            _sync['erro'] = f'{type(e).__name__}: {str(e)[:150]}'
            espera = min(espera * 2, 300)
        _acordar_sync.wait(espera)


class H(http.server.SimpleHTTPRequestHandler):
    _alvo = None
    timeout = 15        # conexao parada (navegador travado, ou de proposito) solta em 15 s

    def _host_ok(self):
        if (self.headers.get('Host') or '').strip().lower() in HOSTS:
            return True
        self.send_error(421, 'host nao reconhecido')
        return False

    def _redir(self, para):
        self.send_response(302)
        self.send_header('Location', para)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _servir(self, so_cabecalho):
        if not self._host_ok():
            return
        caminho = self.path.split('?', 1)[0]
        if caminho.startswith('/api/'):
            return self._api_get(caminho)
        if caminho in ('', '/'):
            return self._redir('/HUB.html')
        if caminho.rstrip('/').lower() == '/digital_viewer':
            return self._redir('/digital_viewer/index.html')
        alvo = resolver(self.path)
        if alvo is None or not os.path.exists(alvo):
            self.send_error(404)
            return
        self._alvo = alvo
        (super().do_HEAD if so_cabecalho else super().do_GET)()

    def do_GET(self):  self._servir(False)
    def do_HEAD(self): self._servir(True)

    def translate_path(self, path):
        # so chega aqui depois de resolver() ter aprovado; sem aprovacao, um caminho
        # que nao existe
        return self._alvo or os.path.join(BV, '__nao_servido__')

    def list_directory(self, path):
        rel = os.path.relpath(path, BV).replace(os.sep, '/').lower()
        if rel in LISTAVEIS:
            return super().list_directory(path)
        self.send_error(404)
        return None

    def end_headers(self):
        # servidor de desenvolvimento: nada de cache. Sem isto o navegador segura o
        # SCRIPT3.js/index.html antigos e as mudancas "nao acontecem" — pior ainda,
        # um arquivo velho junto com um novo faz a foto sumir sem dar erro.
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    # --- respostas e checagens comuns ----------------------------------------------
    def send_error(self, code, message=None, explain=None):
        # a mensagem vai na linha de status: tirar quebras de linha, senao um texto
        # enviado pelo cliente (o nome de uma chave invalida) vira cabecalho
        if message:
            message = re.sub(r'[\r\n]+', ' ', str(message))[:200]
        super().send_error(code, message, explain)

    def _resposta(self, corpo, tipo, extra=None):
        dado = corpo.encode('utf-8') if isinstance(corpo, str) else corpo
        self.send_response(200)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(dado)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dado)

    def _json(self, obj):
        self._resposta(json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

    def _post_ok(self):
        """Mesma origem + JSON. O navegador manda Origin em todo POST, e outro site manda
        o dele. E exigir JSON obriga o navegador a pedir licenca antes (preflight
        OPTIONS), que este servidor nao concede — um site qualquer nao grava aqui."""
        origem = (self.headers.get('Origin') or '').lower()
        if origem and origem not in {e + h for e in ('http://', 'https://') for h in HOSTS}:
            self.send_error(403, 'origem nao permitida'); return False
        if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
            self.send_error(415, 'so aceito application/json'); return False
        return True

    def _ler_json(self, maximo):
        """Corpo JSON ou None (ja respondeu o erro). Qualquer falha de parse vira 400 —
        inclusive JSON aninhado demais, que levanta RecursionError (nao e ValueError)
        e antes derrubava o servidor."""
        try:
            n = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self.send_error(400, 'Content-Length invalido'); return None
        if n <= 0 or n > maximo:
            self.send_error(413); return None
        try:
            return json.loads(self.rfile.read(n).decode('utf-8'))
        except Exception:
            self.send_error(400, 'json invalido'); return None

    # --- caderno de bancada (fase 1) -------------------------------------------------
    def _api_get(self, caminho):
        consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        placa = (consulta.get('placa') or [None])[0]
        if caminho.startswith('/api/arquivo/'):
            info = MDB.info_placa(urllib.parse.unquote(caminho[len('/api/arquivo/'):]))
            if info is None:
                self.send_error(404, 'placa desconhecida'); return
            return self._json({'placa': info['placa'], 'fp': info['fp'], 'n_malhas': info['n_malhas']})
        if caminho == '/api/leituras':
            if MDB.info_placa(placa) is None:
                self.send_error(404, 'placa desconhecida'); return
            return self._json({'leituras': MDB.listar(placa)})
        if caminho == '/api/leituras.csv':
            if placa is not None and MDB.info_placa(placa) is None:
                self.send_error(404, 'placa desconhecida'); return
            nome = f'caderno-{placa or "todas"}.csv'
            return self._resposta('﻿' + MDB.exportar_csv(placa), 'text/csv; charset=utf-8',
                                  {'Content-Disposition': f'attachment; filename="{nome}"'})
        # --- fase 2 ---
        if caminho == '/api/consenso':
            info = MDB.info_placa(placa)
            if info is None:
                self.send_error(404, 'placa desconhecida'); return
            return self._json(consenso_da_placa(info))
        if caminho.startswith('/api/anotacoes/'):
            placa = urllib.parse.unquote(caminho[len('/api/anotacoes/'):])
            if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}', placa) or '..' in placa:
                self.send_error(400, 'nome de placa invalido'); return
            return self._json(anotacoes_da_placa(placa))
        if caminho == '/api/sync':
            faltam = MDB.situacao_sync()['faltam'] if CENTRAL else 0
            return self._json(dict(_sync, papel='bancada' if CENTRAL else 'local',
                                   central=CENTRAL or None, faltam=faltam))
        if caminho == '/api/backup':
            # copia consistente do banco (API de backup do SQLite, segura com o WAL)
            os.makedirs(MDB.DADOS, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=MDB.DADOS, suffix='.backup')
            os.close(fd)
            try:
                MDB.backup_para(tmp)
                with open(tmp, 'rb') as f:
                    dado = f.read()
            finally:
                os.remove(tmp)
            return self._resposta(dado, 'application/vnd.sqlite3',
                                  {'Content-Disposition': 'attachment; filename="medicoes.sqlite3"'})
        self.send_error(404)

    def _post_leituras(self):
        if not self._post_ok():
            return
        corpo = self._ler_json(500_000)
        if corpo is None:
            return
        if not isinstance(corpo, dict) or not isinstance(corpo.get('leituras'), list):
            self.send_error(400, 'esperava {"leituras": [...]}'); return
        try:
            resultado = MDB.inserir(corpo['leituras'])
        except MDB.BancoOcupado:
            # banco travado por outro programa / disco cheio: erro PASSAGEIRO. 503 faz o
            # navegador manter as leituras na fila e reenviar — nunca vira recusa
            self.send_error(503, 'banco ocupado, tente de novo'); return
        except ValueError as e:
            self.send_error(400, str(e)); return
        self._json(resultado)
        if CENTRAL and resultado['aceitas']:
            _acordar_sync.set()                      # bancada: leva ao central ja

    def _post_anotacoes(self, placa):
        """POST /api/anotacoes/<placa> {"mudancas": [[secao, chave, valor|null], ...]}
        -> dados/anotacoes/<placa>.json = {tipos, nomes, malhas} (anotacoes.py).
        Manda so o que mudou (nao o arquivo inteiro): dois tecnicos classificando ao
        mesmo tempo nao apagam o trabalho um do outro."""
        if not self._post_ok():
            return
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}', placa) or '..' in placa:
            self.send_error(400, 'nome de placa invalido'); return
        if not os.path.exists(os.path.join(BV, 'digital_viewer', 'build', 'DRONE', placa + '.bvr')):
            self.send_error(404, 'placa desconhecida'); return
        corpo = self._ler_json(2_000_000)
        if corpo is None:
            return
        muds = corpo.get('mudancas') if isinstance(corpo, dict) else None
        if not isinstance(muds, list) or len(muds) > 20000:
            self.send_error(400, 'esperava {"mudancas": [[secao, chave, valor], ...]}'); return
        # Cada mudanca e julgada sozinha: uma invalida (navegador com versao diferente do
        # programa) e recusada e as outras gravam — recusar o lote inteiro deixava a fila
        # do navegador e a da bancada tentando para sempre.
        boas, recusadas = [], []
        for i, m in enumerate(muds):
            ok, motivo = ANOT.validar(m)
            if ok:
                boas.append(m)
            else:
                recusadas.append({'i': i, 'motivo': motivo})
        if boas:
            ANOT.gravar(placa, boas)
            if CENTRAL:                    # bancada: guarda para levar ao central
                ANOT.enfileirar(placa, boas)
                _acordar_sync.set()
        self._json({'ok': True, 'gravadas': len(boas), 'recusadas': recusadas})

    def do_POST(self):
        """POST /ajuste/<placa> (alinhamento da foto) e POST /api/leituras (caderno).

        O navegador nao escreve em disco sozinho — sem isto so daria para baixar o
        JSON e mover na mao. Como o viewer ja roda contra este servidor, ele manda o
        ajuste ao soltar o mouse e fica gravado na hora, por placa.
        """
        if not self._host_ok():
            return
        p = urllib.parse.unquote(self.path.split('?', 1)[0])
        if p == '/api/leituras':
            return self._post_leituras()
        if p.startswith('/api/anotacoes/'):
            return self._post_anotacoes(p[len('/api/anotacoes/'):])
        if not p.startswith('/ajuste/'):
            self.send_error(404); return
        if not self._post_ok():
            return
        placa = p[len('/ajuste/'):]
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}', placa) or '..' in placa:
            self.send_error(400, 'nome de placa invalido'); return
        if not os.path.exists(os.path.join(BV, 'digital_viewer', 'build', 'DRONE', placa + '.bvr')):
            self.send_error(404, 'placa desconhecida'); return
        dados = self._ler_json(200_000)
        if dados is None:
            return
        limpo, motivo = validar_ajuste(placa, dados)
        if motivo:
            self.send_error(400, motivo); return

        pasta = os.path.join(BV, 'digital_viewer', 'build', 'ajustes')
        os.makedirs(pasta, exist_ok=True)
        alvo = os.path.join(pasta, placa + '.json')
        with _trava_ajuste:
            if os.path.exists(alvo):             # guarda a versao anterior: um ajuste ruim nao apaga o bom
                anteriores = os.path.join(pasta, 'anteriores')
                os.makedirs(anteriores, exist_ok=True)
                shutil.copy2(alvo, os.path.join(anteriores, placa + '.json'))
            tmp = alvo + '.tmp'                  # grava inteiro antes de trocar
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(limpo, f, ensure_ascii=False, indent=1)
            os.replace(tmp, alvo)
        corpo = json.dumps({'ok': True, 'arquivo': placa + '.json'}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a): pass              # silencioso

class Servidor(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Uma thread por conexao: um navegador travado (ou um PDF grande indo para um PC
    # lento) nao congela os outros. O banco tem trava propria (MDB._trava).
    daemon_threads = True
    # No Windows, SO_REUSEADDR deixa um SEGUNDO servidor subir na mesma porta sem erro, e
    # as leituras do caderno passam a ir para o processo velho. La se usa o modo
    # exclusivo: o segundo falha com "porta em uso" (tratado abaixo). Fora do Windows,
    # reuse_address so evita esperar o TIME_WAIT ao reiniciar.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        import socket
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == '__main__':
    try:
        with Servidor(('127.0.0.1', PORTA), H) as s:
            print(f'Hub:    http://127.0.0.1:{PORTA}/HUB.html')
            print(f'Viewer: http://127.0.0.1:{PORTA}/digital_viewer/index.html')
            if CENTRAL:              # so depois de pegar a porta: um segundo processo nao sincroniza
                threading.Thread(target=_laco_sync, name='sync-central', daemon=True).start()
                print(f'Bancada: as leituras tambem vao para o central {CENTRAL}')
            print('(feche esta janela para parar)', flush=True)
            s.serve_forever()
    except OSError as e:
        print(f'ERRO: porta {PORTA} ja esta em uso ({e}).')
        print('Feche a outra janela do servidor e tente de novo.')
        if sys.stdin and sys.stdin.isatty():         # no systemd nao ha teclado
            input('Enter para sair...')
        sys.exit(1)
