# Administra o Boardview na nuvem (Supabase). Rode na pasta do programa:
#
#   python nuvem/nuvem.py enviar           placas, fotos, leituras e anotacoes (pode repetir)
#   python nuvem/nuvem.py tecnico "Nome"   cria o acesso (ou troca o codigo) e mostra o codigo
#   python nuvem/nuvem.py cortar "Nome"    desliga o acesso na hora
#   python nuvem/nuvem.py listar
#
# Pede a chave SECRETA do projeto (Settings > API Keys) sem mostrar na tela e sem gravar.
# So LE dados/ deste PC. Repetir "enviar" nao duplica leitura nem passa por cima de
# anotacao/ajuste que ja esta na nuvem.
import os, sys, re, json, glob, getpass, hashlib, secrets, sqlite3, mimetypes, unicodedata
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import medicoes_db as MDB                                   # noqa: E402

BUILD = os.path.join(RAIZ, 'digital_viewer', 'build')
ALFABETO = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'               # sem 0/O e 1/I
URL = CHAVE = None


def configurar():
    global URL, CHAVE
    with open(os.path.join(RAIZ, 'nuvem-config.js'), encoding='utf-8') as f:
        URL = os.environ.get('BOARDVIEW_NUVEM_URL') or re.search(r"url: '([^']+)'", f.read()).group(1)
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


def tecnico(nome):
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
    print(f'Nome:   {nome}\nCodigo: {codigo}\n(so aparece agora; perdeu, rode de novo e o antigo deixa de valer)')


def cortar(nome):
    t = achar(nome)
    if not t:
        sys.exit('Nao achei esse nome.')
    req('PATCH', '/rest/v1/tecnico?id=eq.' + t[0]['id'], {'ativo': False}, {'Prefer': 'return=minimal'})
    print('Acesso cortado: ' + t[0]['nome'])


def main(a):
    if not a or a[0] not in ('enviar', 'tecnico', 'cortar', 'listar') or (a[0] in ('tecnico', 'cortar') and len(a) != 2):
        sys.exit('uso: python nuvem/nuvem.py enviar | tecnico "Nome" | cortar "Nome" | listar')
    configurar()
    if a[0] == 'enviar':
        enviar_dados(enviar_placas())
        enviar_arquivos()
    elif a[0] == 'listar':
        for t in req('GET', '/rest/v1/tecnico?select=nome,ativo&order=nome'):
            print(t['nome'], '' if t['ativo'] else '(cortado)')
    else:
        (tecnico if a[0] == 'tecnico' else cortar)(a[1])


if __name__ == '__main__':
    main(sys.argv[1:])
