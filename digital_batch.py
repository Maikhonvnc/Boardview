# SUPERSEDIDO por foto_viewer.py — mantido so como referencia.
# Este script tirava os .bvr de um zip em E:/pcbs (que nao existe mais) e
# nao tinha o passo de refino, entao as fotos saiam ~1% fora dos pads.
# Prepara TODAS as placas p/ o viewer local do DigitalBoard:
#  - extrai o .bvr do repo -> digital_viewer/build/DRONE/<id>.bvr
#  - alinha a foto XZZ ao .bvr (rot auto + flip auto) -> build/FOTO/<id>_foto.jpg (reduzida)
#  - manifesto build/boards.json (dropdown) + contact sheet p/ conferir flips
import os, re, glob, json, zipfile, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw
import align_bvr as V, align_bg as A
from paths import BV, DRONES as DR

DV = os.path.join(BV, 'digital_viewer', 'build')
ZIP = 'E:/pcbs/PDFJS-2774a1fbd651bcabc635e43aa971f86a3530321a.zip'
MAXW = 2400
os.makedirs(os.path.join(DV, 'DRONE'), exist_ok=True)
os.makedirs(os.path.join(DV, 'FOTO'), exist_ok=True)

# flips ja verificados (por leitura de texto) — [rot, flipsec]
KNOWN = {
    'DJI Mini2-PP001950.03 PCB layer': (90, '0'),
    'Mini3-PP003401.01 PCB layer': (0, '0,1'),
    'DJI mini3 Pro-PP002663 PCB layer': (0, ''),
    'Mavic PRO-P024422 PCB layer': (90, ''),
    'DJI 4P IMU-P02073.05 PCB layer': (0, ''),
    'DJI Mavic3 PP002022.10 PCB layer': (90, ''),
    'DJI Mavic3 Pro-PP003253.03 PCB layer': (90, ''),
    'Mini4 Pro-PP003675.04 MB PCB layer': (0, ''),
}

def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def photo_of(pcb):
    d = os.path.dirname(pcb); base = os.path.splitext(os.path.basename(pcb))[0]
    conf = os.path.join(d, base + '.conf')
    if not os.path.exists(conf): return None
    m = re.search(r'(?m)^TopImageFile\s*=\s*(.+)$', open(conf, encoding='utf-8', errors='replace').read())
    if not m: return None
    p = os.path.join(d, m.group(1).strip())
    return p if os.path.exists(p) else None

zf = zipfile.ZipFile(ZIP)
bvr_members = {}
for n in zf.namelist():
    m = re.search(r'/build/DRONE/(.+)\.bvr$', n, re.I)
    if m: bvr_members[m.group(1).lower()] = n

manifest, rows = [], []
for pcb in sorted(glob.glob(DR + '/**/*.pcb', recursive=True)):
    if '__MACOSX' in pcb or os.path.basename(pcb).startswith('._') or 'yidiantong' in pcb.lower():
        continue
    base = os.path.splitext(os.path.basename(pcb))[0]
    if base.lower() not in bvr_members:
        continue
    photo = photo_of(pcb)
    if not photo:
        continue
    sid = slug(base); folder = os.path.basename(os.path.dirname(pcb))
    bvr = os.path.join(DV, 'DRONE', sid + '.bvr')
    try:
        with open(bvr, 'wb') as f:
            f.write(zf.read(bvr_members[base.lower()]))
        if base in KNOWN:
            rot, flip = KNOWN[base]
        else:  # auto: rot com menor dispersao; flip auto
            def disp(r):
                out = subprocess.run(['python', os.path.join(BV, 'align_bvr.py'), bvr, photo, str(r), '0'],
                                     capture_output=True, text=True)
                m = re.search(r'disp ([\d.]+)%', out.stdout)
                return float(m.group(1)) if m else 1e9
            rot = min((0, 90), key=disp); flip = None
        args = ['python', os.path.join(BV, 'align_bvr.py'), bvr, photo, str(rot), '0']
        if flip is not None: args.append(flip)
        r = subprocess.run(args, capture_output=True, text=True)
        conf = re.sub(r'\.bvr$', '.conf', bvr, flags=re.I)
        bgp = re.sub(r'\.bvr$', '_bg.png', bvr, flags=re.I)
        if not os.path.exists(bgp) or 'AVISO' in r.stdout:
            print(f'FALHOU {sid}: {(r.stdout+r.stderr).strip()[-90:]}'); continue
        im = Image.open(bgp).convert('RGB')
        if im.width > MAXW: im = im.resize((MAXW, round(im.height*MAXW/im.width)), Image.LANCZOS)
        im.save(os.path.join(DV, 'FOTO', sid + '_foto.jpg'), quality=86)
        os.remove(bgp); os.remove(conf)
        fs = re.search(r'flip_secao=\[([^\]]*)\]', r.stdout)
        manifest.append({'id': sid, 'name': f'{folder}  |  {base}'})
        # thumb p/ contact sheet
        segs, pins, mins = V.parse_bvr(bvr)
        tb = A.bbox([p for s in segs for p in s]); W, H = tb[2], tb[3]
        th = im.copy(); S = th.width / W; d = ImageDraw.Draw(th)
        for (x, y) in pins[::3]:
            px, py = x*S, th.height-1-y*S
            d.ellipse([px-2, py-2, px+2, py+2], outline=(0, 255, 255))
        rows.append((sid, rot, fs.group(1) if fs else '?', th.resize((360, round(th.height*360/th.width)))))
        print(f'{sid}: rot{rot} flip=[{fs.group(1) if fs else "?"}] {"(verificado)" if base in KNOWN else "(auto)"}')
    except Exception as e:
        print(f'ERRO {sid}: {e}')

json.dump(manifest, open(os.path.join(DV, 'boards.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(f'\n{len(manifest)} placas -> {DV}/boards.json')

# contact sheet
if rows:
    cols = 4; pad = 6; lbl = 16
    tw = rows[0][3].width; ch = max(r[3].height for r in rows) + lbl + pad
    nr = (len(rows)+cols-1)//cols
    sheet = Image.new('RGB', (cols*(tw+pad)+pad, nr*ch+pad), (20, 25, 35)); dd = ImageDraw.Draw(sheet)
    for i, (sid, rot, fs, th) in enumerate(rows):
        cx = pad+(i % cols)*(tw+pad); cy = pad+(i//cols)*ch
        dd.text((cx, cy), f'{sid[:34]} r{rot} f[{fs}]', fill=(255, 255, 0)); sheet.paste(th, (cx, cy+lbl))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BV, 'digital_contact.png')
    sheet.save(out); print('contact sheet ->', out)
