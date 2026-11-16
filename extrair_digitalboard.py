# Extracao EXAUSTIVA de tudo relacionado a drone dos repositorios DigitalBoard.
# Criterios: (1) local - dentro de pasta DRONE; (2) nome - regex ampla incluindo as
# grafias erradas do repo (mine2, mavc3); (3) catalogo oficial db/drone.html;
# (4) assets referenciados pelas paginas de drone; (5) datasheets dos chips.
# Uso: python extrair_digitalboard.py
import zipfile, os, re, hashlib, json, sys
from paths import DIGITALBOARD
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ZIPDIR = r'E:/pcbs'
OUT = DIGITALBOARD

LOC  = re.compile(r'/DRONE/', re.I)
NAME = re.compile(r'mavic|mavc|mini\s?[1-9]|mini[1-9]|mine[1-9]|air\s?[23]|air[23]|air.?2s|air.?3s|'
                  r'avata|phantom|inspire|matrice|agras|spark|tello|drone|dji|'
                  r'rc[\s_-]?(pro|plus|n1)|rcn1|4p[\s_]?imu|goggle|osmo|ronin|'
                  r'pp00\d{4}|p02073|p024422|mini5pro|d12000', re.I)
NOT  = re.compile(r'ipad|iphone|samsung|realme|moto|xiaomi|redmi|poco|oppo|vivo|huawei|nokia|'
                  r'infinix|tecno|galaxy|radeon|geforce|nvidia|asrock|macbook|xbox|ps[45]|'
                  r'lg[\s_]k|/SM-|note\s?\d|edge\s?\d|airpods', re.I)
DATASHEET = re.compile(r'datasheet-drones/', re.I)
CATALOGO  = {'db/drone.html', 'db/drone_lite.html'}
KEEP = {'.bvr','.pcb','.dbs','.db','.pdf','.json','.html','.sqlite3','.jpg','.jpeg','.png','.svg','.js','.hdmi','.htm','.txt','.csv'}
TIPO = {'.bvr':'boardview-bvr', '.pcb':'boardview-pcb', '.dbs':'bitmap-dbs', '.db':'bitmap-dbs',
        '.pdf':'pdf', '.json':'dados-json', '.html':'paginas-html', '.sqlite3':'anotacoes',
        '.jpg':'imagens', '.jpeg':'imagens', '.png':'imagens', '.svg':'imagens', '.js':'scripts',
        '.hdmi':'paginas-html', '.htm':'paginas-html', '.txt':'outros', '.csv':'outros'}

def selecionar():
    zips = {}
    sel = {}                      # (zip, path) -> motivo
    for zp in sorted(os.listdir(ZIPDIR)):
        if not zp.endswith('.zip'): continue
        z = zipfile.ZipFile(os.path.join(ZIPDIR, zp)); zips[zp] = z
        for i in z.infolist():
            n = i.filename
            if n.endswith('/'): continue
            if os.path.splitext(n)[1].lower() not in KEEP: continue
            rel = n.split('/', 1)[-1]
            base = os.path.basename(n)
            if DATASHEET.search(n):                       sel[(zp, n)] = 'datasheet'
            elif LOC.search(n):                           sel[(zp, n)] = 'local'
            elif rel in CATALOGO:                         sel[(zp, n)] = 'catalogo'
            elif NAME.search(base) and not NOT.search(n): sel[(zp, n)] = 'nome'
            elif NAME.search(n)  and not NOT.search(n):   sel[(zp, n)] = 'caminho'
    # indice por basename p/ resolver referencias
    idx = {}
    for zp, z in zips.items():
        for i in z.infolist():
            if not i.filename.endswith('/'):
                idx.setdefault(os.path.basename(i.filename).lower(), []).append((zp, i.filename))
    # expande: assets citados pelas paginas de drone (ignora paginas-indice)
    REF = re.compile(r'["\']([^"\'<>]+\.(?:bvr|jpg|jpeg|png|json|pdf|svg|dbs|sqlite3))["\']', re.I)
    for (zp, n), motivo in list(sel.items()):
        if os.path.splitext(n)[1].lower() != '.html': continue
        try: t = zips[zp].read(n).decode('utf-8', 'replace')
        except Exception: continue
        refs = set(REF.findall(t))
        if len(refs) > 60: continue                    # pagina-indice: nao explode
        for r in refs:
            b = os.path.basename(r.replace('%20', ' ')).lower()
            for cand in idx.get(b, []):
                if cand not in sel and not NOT.search(cand[1]):
                    sel[cand] = 'referencia'
    return zips, sel

def main():
    zips, sel = selecionar()
    vistos, cont, mb = {}, {}, 0
    for (zp, n), motivo in sorted(sel.items()):
        try: data = zips[zp].read(n)
        except Exception as e:
            print('  falha:', n, e); continue
        h = hashlib.md5(data).hexdigest()
        if h in vistos: continue
        ext = os.path.splitext(n)[1].lower()
        sub = 'datasheets' if motivo == 'datasheet' else TIPO.get(ext, 'outros')
        d = os.path.join(OUT, sub); os.makedirs(d, exist_ok=True)
        base = os.path.basename(n); dest = os.path.join(d, base); i = 1
        while os.path.exists(dest) and hashlib.md5(open(dest,'rb').read()).hexdigest() != h:
            stem, e2 = os.path.splitext(base); dest = os.path.join(d, f'{stem} ({i}){e2}'); i += 1
        if not os.path.exists(dest):
            with open(dest, 'wb') as f: f.write(data)
        vistos[h] = dest; cont[sub] = cont.get(sub, 0) + 1; mb += len(data)
    print(f'\n{sum(cont.values())} arquivos unicos ({mb/1e6:.0f} MB) em {OUT}')
    for k in sorted(cont): print(f'   {k:18} {cont[k]:>4}')
    from collections import Counter
    print('\nmotivos:', dict(Counter(sel.values())))

if __name__ == '__main__':
    main()
