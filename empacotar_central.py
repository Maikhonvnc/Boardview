# Monta o pacote para instalar/atualizar o servidor central (Linux) — fase 2.
#
#   python empacotar_central.py            essencial: viewer, HUB, caderno (~110 MB)
#   python empacotar_central.py --pdfs     + PDFs-Drone e DigitalBoard/pdf (~0,9 GB)
#   python empacotar_central.py --drones   + um 2o pacote com a pasta Drones (/_drones/)
#
# Fica de FORA de proposito: dados/ (o banco do central e o do central, nao o deste PC),
# central.txt (faria o central sincronizar com outro), copias .bak, zips e __pycache__.
# Passo a passo do servidor: servidor-central/LEIAME.md.
import os, io, sys, json, tarfile, datetime, argparse
from paths import BV, DRONES

ARQUIVOS = ['servidor.py', 'paths.py', 'medicoes_db.py', 'consenso.py', 'anotacoes.py', 'bvr.py', 'sugerir_placas.py',
            'exportar_placa.py', 'HUB.html', 'viewer.html', 'favicon.ico']
PASTAS = ['digital_viewer', 'thumbs', 'boards', 'Malhas', 'Cadernos', 'Netlists', 'servidor-central']
PASTAS_PDF = ['PDFs-Drone', 'DigitalBoard/pdf']
FORA_EXT = ('.bak', '.zip', '.tmp', '.pyc', '.conferindo', '.baixando')
FORA_DIR = {'__pycache__', 'anteriores'}


def _dono_root(ti):
    """No servidor os arquivos ficam do root, so leitura para o servico."""
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = 'root'
    ti.mode = 0o755 if ti.isdir() or ti.name.endswith('.sh') else 0o644
    return ti


def _arquivos(base, pastas, soltos=()):
    for f in soltos:
        if os.path.isfile(os.path.join(base, f)):
            yield f
    for p in pastas:
        raiz = os.path.join(base, p)
        if not os.path.isdir(raiz):
            print(f'  (sem {p}, pulando)')
            continue
        for d, subs, fs in os.walk(raiz):
            subs[:] = sorted(s for s in subs if s not in FORA_DIR)
            for f in sorted(fs):
                # build/COBRE: so os .cobre.json enxutos; os originais baixados tem ~50 MB cada
                if os.path.basename(d) == 'COBRE' and not f.endswith('.cobre.json'):
                    continue
                # build/anotacoes e so a semente antiga; a de hoje vem de dados/ (ver empacotar)
                if os.path.basename(d) == 'anotacoes' and os.path.basename(os.path.dirname(d)) == 'build':
                    continue
                if not f.lower().endswith(FORA_EXT):
                    yield os.path.relpath(os.path.join(d, f), base).replace(os.sep, '/')


def empacotar(destino, base, nomes, extras=()):
    n = 0
    with tarfile.open(destino, 'w:gz', compresslevel=6) as tar:
        for rel in nomes:
            tar.add(os.path.join(base, rel), arcname=rel, recursive=False, filter=_dono_root)
            n += 1
        for arcname, dado in extras:
            ti = tarfile.TarInfo(arcname)
            ti.size = len(dado)
            ti.mtime = int(datetime.datetime.now().timestamp())
            tar.addfile(_dono_root(ti), io.BytesIO(dado))
            n += 1
    mb = os.path.getsize(destino) / 1e6
    print(f'{destino}\n  {n} arquivos, {mb:.0f} MB')


def main():
    ap = argparse.ArgumentParser(description='pacote do servidor central')
    ap.add_argument('--pdfs', action='store_true', help='inclui PDFs-Drone e DigitalBoard/pdf')
    ap.add_argument('--drones', action='store_true', help='gera tambem o pacote da pasta Drones')
    ap.add_argument('--saida', default=os.path.dirname(BV), help='pasta onde gravar (padrao: a de cima do repo)')
    a = ap.parse_args()
    if os.path.exists(os.path.join(BV, 'central.txt')):
        print('(central.txt deste PC fica de fora — e da bancada, nao do servidor)')
    hoje = datetime.date.today().isoformat()
    pastas = PASTAS + (PASTAS_PDF if a.pdfs else [])
    # Semente das anotacoes: o estado de HOJE deste PC (dados/anotacoes), nao a pasta
    # build/anotacoes parada no tempo. No central ela so e usada para placa que ainda nao
    # tem arquivo em dados/ — atualizar o central nunca apaga o que ja foi marcado la.
    import anotacoes as ANOT
    semente = [(f'digital_viewer/build/anotacoes/{p}.json',
                json.dumps(ANOT.ler(p), ensure_ascii=False, indent=1, sort_keys=True).encode('utf-8'))
               for p in ANOT.placas()]
    empacotar(os.path.join(a.saida, f'boardview-central-{hoje}.tar.gz'), BV, _arquivos(BV, pastas, ARQUIVOS), semente)
    if a.drones:
        if not os.path.isdir(DRONES):
            sys.exit(f'pasta Drones nao encontrada: {DRONES}')
        empacotar(os.path.join(a.saida, f'boardview-drones-{hoje}.tar.gz'), DRONES, _arquivos(DRONES, ['.']))
    print('\nProximo passo (servidor-central/LEIAME.md):\n'
          f'  scp {os.path.join(a.saida, f"boardview-central-{hoje}.tar.gz")} USUARIO@SERVIDOR:/tmp/')


if __name__ == '__main__':
    main()
