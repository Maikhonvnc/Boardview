# Exporta TODAS as placas XZZ p/ o viewer local: viewer_data/<id>.json + <id>_bg.png
# (foto redimensionada) + boards.json (manifesto). Uso: python batch_export_viewer.py
import os, re, glob, json, subprocess, sys
from PIL import Image
from paths import BV, DRONES as DR

VD = os.path.join(BV, 'viewer_data')
os.makedirs(VD, exist_ok=True)
MAXW = 2600  # largura maxima da foto no viewer

def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

manifest = []
for pcb in sorted(glob.glob(DR + '/**/*.pcb', recursive=True)):
    if '__MACOSX' in pcb or os.path.basename(pcb).startswith('._') or 'yidiantong' in pcb.lower():
        continue
    base = os.path.splitext(os.path.basename(pcb))[0]
    folder = os.path.basename(os.path.dirname(pcb))
    sid = slug(base)
    jf = os.path.join(VD, sid + '.json')
    r = subprocess.run([sys.executable, os.path.join(BV, 'export_viewer.py'), pcb, jf],
                       capture_output=True, text=True)
    if not os.path.exists(jf):
        print(f'FALHOU {base}: {(r.stdout+r.stderr).strip()[-120:]}')
        continue
    d = json.load(open(jf))
    # copia/redimensiona a foto
    if d.get('img'):
        src = os.path.join(os.path.dirname(pcb), d['img']['file'])
        if os.path.exists(src):
            im = Image.open(src).convert('RGB')
            if im.width > MAXW:
                im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
            im.save(os.path.join(VD, sid + '_bg.jpg'), quality=88)
            d['img']['file'] = sid + '_bg.jpg'
        else:
            d['img'] = None
    json.dump(d, open(jf, 'w'), separators=(',', ':'))
    manifest.append({'id': sid, 'name': f'{folder}  |  {base}', 'pins': len(d['pins']),
                     'vias': len(d['vias']), 'img': bool(d.get('img'))})
    print(f'{sid}: {len(d["pins"])}p {len(d["vias"])}v {"foto" if d.get("img") else "sem foto"}')

manifest.sort(key=lambda m: m['name'])
json.dump(manifest, open(os.path.join(VD, 'boards.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(f'\n{len(manifest)} placas -> {VD}/boards.json')
