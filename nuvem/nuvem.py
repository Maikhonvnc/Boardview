# Administra o Boardview na nuvem (Supabase). Rode na pasta do programa:
#
#   python nuvem/nuvem.py enviar           placas, fotos, leituras e anotacoes (pode repetir)
#   python nuvem/nuvem.py tecnico "Nome"   cria o acesso (ou troca o codigo) e mostra o codigo
#   python nuvem/nuvem.py cortar "Nome"    desliga o acesso na hora
#   python nuvem/nuvem.py listar
#   python nuvem/nuvem.py backup-ligar     backup automatico todo dia (uma vez, neste PC)
#   python nuvem/nuvem.py backup           faz um backup agora (nao pede chave)
#   python nuvem/nuvem.py restaurar X.zip  devolve a nuvem o que FALTAR la
#
# Pede a chave SECRETA do projeto (Settings > API Keys) sem mostrar na tela e sem gravar.
# So LE dados/ deste PC. Repetir "enviar" nao duplica leitura nem passa por cima de
# anotacao/ajuste que ja esta na nuvem.
import os, sys, re, json, glob, getpass, hashlib, secrets, sqlite3, mimetypes, unicodedata
import datetime, subprocess, tempfile, zipfile
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import medicoes_db as MDB                                   # noqa: E402

BUILD = os.path.join(RAIZ, 'digital_viewer', 'build')
ALFABETO = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'               # sem 0/O e 1/I
URL = CHAVE = None


def configurar(secreta=True):
    global URL, CHAVE
    with open(os.path.join(RAIZ, 'nuvem-config.js'), encoding='utf-8') as f:
        cfg = f.read()
    URL = os.environ.get('BOARDVIEW_NUVEM_URL') or re.search(r"url: '([^']+)'", cfg).group(1)
    if not secreta:
        CHAVE = re.search(r"chave: '([^']+)'", cfg).group(1)
        return
    CHAVE = os.environ.get('BOARDVIEW_NUVEM_SECRETA') or getpass.getpass('Chave secreta (nao aparece ao colar): ').strip()
    if CHAVE.startswith('sb_publishable_'):
        sys.exit('Essa e a chave publicavel. Aqui precisa ser a secreta (sb_secret_... ou service_role).')


def req(metodo, caminho, corpo=None, cab=None, cru=False):
    h = {'apikey': CHAVE, 'Authorization': 'Bearer ' + CHAVE, 'User-Agent': 'boardview'}
    if corpo is not None and not isinstance(corpo, bytes):
        corpo = json.dumps(corpo).encode('utf-8')
        h['Content-Type'] = 'application/json'
    h.update(cab or {})
    r = urllib.request.Request(URL + caminho, data=corpo, headers=h, method=metodo)
    for vez in range(4):
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                b = resp.read()
                return b if cru else (json.loads(b) if b else None)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or vez == 3:
                raise RuntimeError(f'{metodo} {caminho.split("?")[0]}: {e.code} {e.read()[:300].decode("utf-8", "replace")}')
        except urllib.error.URLError:
            if vez == 3:
                raise


def novas(tabela, linhas, chave):
    """Insere so o que ainda nao existe."""
    for i in range(0, len(linhas), 500):
        req('POST', f'/rest/v1/{tabela}?on_conflict={chave}', linhas[i:i + 500],
            {'Prefer': 'resolution=ignore-duplicates,return=minimal'})


def arquivos():
    """{caminho no bucket: arquivo}: so o que o viewer abre (os JSON brutos do COBRE nao vao)."""
    pad = ['*.json', 'DRONE/*.bvr', 'SM/*_borda.jpg', 'FOTO/*', 'COBRE/*.cobre.json']
    return {os.path.relpath(a, BUILD).replace(os.sep, '/'): a
            for p in pad for a in glob.glob(os.path.join(BUILD, p)) if os.path.isfile(a)}


def enviar_arquivos():
    locais = arquivos()
    manifesto = {}
    for c, a in locais.items():
        with open(a, 'rb') as f:
            manifesto[c] = hashlib.sha256(f.read()).hexdigest()
    try:
        antes = json.loads(req('GET', '/storage/v1/object/authenticated/placas/manifesto.json', cru=True))
    except RuntimeError as e:
        if ': 400 ' not in str(e) and ': 404 ' not in str(e):
            raise
        antes = {}

    def um(c):
        with open(locais[c], 'rb') as f:
            subir(c, f.read(), mimetypes.guess_type(c)[0] or 'application/octet-stream')
    falta = sorted(c for c in manifesto if antes.get(c) != manifesto[c])
    with ThreadPoolExecutor(4) as ex:
        for i, _ in enumerate(ex.map(um, falta), 1):
            print(f'\rarquivos: {i}/{len(falta)}', end='', flush=True)
    subir('manifesto.json', json.dumps(manifesto).encode(), 'application/json')      # por ultimo
    print(f'\rarquivos: {len(falta)} enviados, {len(manifesto) - len(falta)} ja estavam la')


def subir(c, dado, tipo):
    req('POST', '/storage/v1/object/placas/' + urllib.parse.quote(c), dado, {'Content-Type': tipo, 'x-upsert': 'true'})


def enviar_placas():
    placas = sorted(f[:-4] for f in os.listdir(MDB.DRONE) if f.lower().endswith('.bvr'))
    atuais = {}
    for p in placas:
        info = MDB.info_placa(p)
        atuais[p] = info['fp']
        req('POST', '/rest/v1/placa_versao?on_conflict=placa,fp',
            [{'placa': p, 'fp': info['fp'], 'n_malhas': info['n_malhas'], 'alvos': sorted(info['alvos']), 'atual': True}],
            {'Prefer': 'resolution=merge-duplicates,return=minimal'})
        req('PATCH', f'/rest/v1/placa_versao?placa=eq.{urllib.parse.quote(p)}&fp=neq.{info["fp"]}', {'atual': False},
            {'Prefer': 'return=minimal'})
    print(f'placas: {len(placas)}')
    return atuais


def enviar_dados(atuais):
    banco = os.path.join(MDB.DADOS, 'medicoes.sqlite3')
    if os.path.exists(banco):
        con = sqlite3.connect('file:' + urllib.parse.quote(banco.replace(os.sep, '/')) + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        for r in con.execute('SELECT placa, fp, alvos FROM arquivo'):
            if atuais.get(r['placa']) != r['fp']:          # versao antiga que ainda tem leitura
                al = json.loads(r['alvos'])
                novas('placa_versao', [{'placa': r['placa'], 'fp': r['fp'], 'n_malhas': len(al), 'alvos': al, 'atual': False}], 'placa,fp')
        ls = [{c: r[c] for c in MDB.COLUNAS} for r in con.execute('SELECT * FROM leitura ORDER BY seq')]
        con.close()
        novas('leitura', ls, 'uuid')
        print(f'leituras: {len(ls)} deste PC conferidas na nuvem')
    n = 0
    for a in glob.glob(os.path.join(MDB.DADOS, 'anotacoes', '*.json')):
        placa = os.path.basename(a)[:-5]
        if placa.startswith('recusadas-') or placa not in atuais:
            continue
        with open(a, encoding='utf-8') as f:
            d = json.load(f)
        linhas = [{'placa': placa, 'secao': s, 'chave': k, 'valor': v}
                  for s in ('tipos', 'nomes', 'malhas', 'sugestoes') for k, v in (d.get(s) or {}).items()]
        novas('anotacao', linhas, 'placa,secao,chave')
        n += len(linhas)
    print(f'anotacoes: {n} deste PC conferidas na nuvem')
    ja = {r['placa'] for r in req('GET', '/rest/v1/ajuste?select=placa')}
    for a in glob.glob(os.path.join(BUILD, 'ajustes', '*.json')):
        placa = os.path.basename(a)[:-5]
        if placa in atuais and placa not in ja:
            with open(a, encoding='utf-8') as f:
                req('POST', '/rest/v1/ajuste', [{'placa': placa, 'dados': json.load(f)}], {'Prefer': 'return=minimal'})


def usuario(nome):
    """Mesma regra do entrar.html."""
    n = unicodedata.normalize('NFKD', nome)
    n = ''.join(c for c in n if not unicodedata.category(c).startswith('M')).lower()
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', n))


def achar(nome):
    return [t for t in req('GET', '/rest/v1/tecnico?select=id,nome,ativo') if usuario(t['nome']) == usuario(nome)]


def tecnico(nome, mostrar=True):
    nome = ' '.join(nome.split())
    if not usuario(nome) or len(nome) > 40:
        sys.exit('Nome invalido.')
    codigo = '-'.join(''.join(secrets.choice(ALFABETO) for _ in range(4)) for _ in range(5))     # 100 bits
    t = achar(nome)
    if t:
        req('PUT', '/auth/v1/admin/users/' + t[0]['id'], {'password': codigo})
        req('PATCH', '/rest/v1/tecnico?id=eq.' + t[0]['id'], {'ativo': True}, {'Prefer': 'return=minimal'})
    else:
        u = req('POST', '/auth/v1/admin/users', {'email': usuario(nome) + '@tecnico.boardview.local',
                                                 'password': codigo, 'email_confirm': True})
        req('POST', '/rest/v1/tecnico', [{'id': u['id'], 'nome': nome}], {'Prefer': 'return=minimal'})
    if not mostrar:
        return codigo
    print(f'Nome:   {nome}\nCodigo: {codigo}\n(so aparece agora; perdeu, rode de novo e o antigo deixa de valer)')


def cortar(nome):
    t = achar(nome)
    if not t:
        sys.exit('Nao achei esse nome.')
    req('PATCH', '/rest/v1/tecnico?id=eq.' + t[0]['id'], {'ativo': False}, {'Prefer': 'return=minimal'})
    print('Acesso cortado: ' + t[0]['nome'])


# --- backup -----------------------------------------------------------------------
# A tarefa diaria NAO usa a chave secreta: entra como o tecnico "Backup", com o codigo
# cifrado pelo Windows (DPAPI: so abre nesta conta deste PC). Da para cortar so ele.
TECNICO_BACKUP = 'Backup'
TAREFA = 'Boardview - backup da nuvem'
PASTA_BACKUP = os.environ.get('BOARDVIEW_BACKUP_NUVEM') or os.path.join(os.path.dirname(RAIZ), 'Boardview-backups-nuvem')
MANTER = 60


def _ps(comando, **amb):
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', comando], capture_output=True,
                       text=True, env=dict(os.environ, **amb), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode:
        raise RuntimeError('powershell: ' + r.stderr[:400])
    return r.stdout.strip()


def _arq_codigo():
    return os.path.join(PASTA_BACKUP, 'acesso.dpapi')


def guardar_codigo(codigo):
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    c = _ps("$ErrorActionPreference='Stop'; ConvertTo-SecureString $env:BV_X -AsPlainText -Force | ConvertFrom-SecureString", BV_X=codigo)
    with open(_arq_codigo(), 'w') as f:
        f.write(c)


def ler_codigo():
    if not os.path.exists(_arq_codigo()):
        sys.exit('Backup ainda nao ligado neste PC. Rode: python nuvem/nuvem.py backup-ligar')
    with open(_arq_codigo()) as f:
        c = f.read().strip()
    return _ps("$ErrorActionPreference='Stop'; $s = ConvertTo-SecureString $env:BV_X; "
               "[Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))", BV_X=c)


def backup_ligar():
    guardar_codigo(tecnico(TECNICO_BACKUP, mostrar=False))
    print(backup())
    py = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    agendar(TAREFA, py if os.path.exists(py) else sys.executable)
    print('Backup diario ligado (13h; se o PC estiver desligado, roda quando ligar).')


def agendar(nome, py):
    _ps("$ErrorActionPreference='Stop'; "
        "$a = New-ScheduledTaskAction -Execute $env:BV_PY -Argument ('\"' + $env:BV_ARQ + '\" backup') -WorkingDirectory $env:BV_DIR; "
        "$t = New-ScheduledTaskTrigger -Daily -At 13:00; "
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20); "
        "Register-ScheduledTask -TaskName $env:BV_NOME -Action $a -Trigger $t -Settings $s -Force | Out-Null",
        BV_PY=py, BV_ARQ=os.path.abspath(__file__), BV_DIR=RAIZ, BV_NOME=nome)


def backup():
    """Baixa leituras, anotacoes e ajustes de todas as placas num .zip conferido."""
    codigo = ler_codigo()
    configurar(secreta=False)
    s = req('POST', '/auth/v1/token?grant_type=password', {'email': usuario(TECNICO_BACKUP) + '@tecnico.boardview.local', 'password': codigo})
    cab = {'Authorization': 'Bearer ' + s['access_token']}
    rpc = lambda f, placa: req('POST', '/rest/v1/rpc/' + f, {'p_placa': placa}, cab)
    man = json.loads(req('GET', '/storage/v1/object/authenticated/placas/manifesto.json', cab=cab, cru=True))
    placas = sorted(c[6:-4] for c in man if c.startswith('DRONE/') and c.endswith('.bvr'))
    if not placas:
        raise RuntimeError('a nuvem nao devolveu nenhuma placa')
    dado = {p: {'leituras': rpc('bv_leituras', p), 'anotacoes': rpc('bv_anotacoes', p), 'ajuste': rpc('bv_ajuste', p)} for p in placas}
    n = contar(dado)
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    velhos = sorted(glob.glob(os.path.join(PASTA_BACKUP, 'nuvem-*.zip')))
    alvo = os.path.join(PASTA_BACKUP, datetime.datetime.now().strftime('nuvem-%Y-%m-%d-%H%M%S.zip'))
    fd, tmp = tempfile.mkstemp(dir=PASTA_BACKUP, suffix='.tmp')
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('nuvem.json', json.dumps(dado, ensure_ascii=False))
        if abrir_backup(tmp) != dado:
            raise RuntimeError('o zip nao confere com o que foi baixado')
        os.replace(tmp, alvo)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    # leitura nunca some da nuvem: menos que antes = algo errado, nao apaga os antigos
    if velhos and n['leituras'] < contar(abrir_backup(velhos[-1]))['leituras']:
        raise RuntimeError(f'ATENCAO: a nuvem tem MENOS leituras que o backup anterior. Guardei {alvo} e mantive os antigos.')
    for v in (velhos + [alvo])[:-MANTER]:
        os.remove(v)
    return f'{alvo}: {n["leituras"]} leituras, {n["anotacoes"]} anotacoes, {len(placas)} placas, conferido'


def contar(dado):
    return {'leituras': sum(len(d['leituras']) for d in dado.values()),
            'anotacoes': sum(len(s) for d in dado.values() for s in d['anotacoes'].values())}


def abrir_backup(arq):
    with zipfile.ZipFile(arq) as z:
        return json.loads(z.read('nuvem.json'))


def restaurar(arq):
    dado = abrir_backup(arq)
    for p, d in dado.items():
        novas('leitura', [{c: r.get(c) for c in MDB.COLUNAS} for r in sorted(d['leituras'], key=lambda r: r['seq'])], 'uuid')
        novas('anotacao', [{'placa': p, 'secao': s, 'chave': k, 'valor': v} for s, o in d['anotacoes'].items() for k, v in o.items()],
              'placa,secao,chave')
    ja = {r['placa'] for r in req('GET', '/rest/v1/ajuste?select=placa')}
    for p, d in dado.items():
        if d['ajuste'] and p not in ja:
            req('POST', '/rest/v1/ajuste', [{'placa': p, 'dados': d['ajuste']}], {'Prefer': 'return=minimal'})
    n = contar(dado)
    print(f'Conferido na nuvem: {n["leituras"]} leituras e {n["anotacoes"]} anotacoes do backup (so entrou o que faltava).')


def backup_com_registro():
    """Roda sem janela: o resultado vai para registro.txt, e a falha abre um aviso."""
    try:
        txt = backup()
    except BaseException as e:
        txt = 'FALHOU: ' + (str(e) or type(e).__name__)
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    with open(os.path.join(PASTA_BACKUP, 'registro.txt'), 'a', encoding='utf-8') as f:
        f.write(datetime.datetime.now().isoformat(timespec='seconds') + ' ' + txt + chr(10))
    if sys.stdout:
        print(txt)
    elif txt.startswith('FALHOU'):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, txt[:600], 'Backup do Boardview', 0x30)
    if txt.startswith('FALHOU'):
        sys.exit(1)


def main(a):
    com_nome = ('tecnico', 'cortar', 'restaurar')
    if not a or a[0] not in com_nome + ('enviar', 'listar', 'backup', 'backup-ligar') or (a[0] in com_nome and len(a) != 2):
        sys.exit('uso: python nuvem/nuvem.py enviar | tecnico "Nome" | cortar "Nome" | listar | backup-ligar | backup | restaurar X.zip')
    if a[0] == 'backup':
        return backup_com_registro()
    configurar()
    if a[0] == 'enviar':
        enviar_dados(enviar_placas())
        enviar_arquivos()
    elif a[0] == 'backup-ligar':
        backup_ligar()
    elif a[0] == 'restaurar':
        restaurar(a[1])
    elif a[0] == 'listar':
        for t in req('GET', '/rest/v1/tecnico?select=nome,ativo&order=nome'):
            print(t['nome'], '' if t['ativo'] else '(cortado)')
    else:
        (tecnico if a[0] == 'tecnico' else cortar)(a[1])


if __name__ == '__main__':
    main(sys.argv[1:])
