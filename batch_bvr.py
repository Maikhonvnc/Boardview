# Batch: para cada placa XZZ que tem .bvr correspondente no repo DigitalBoard,
# extrai o .bvr (renomeia p/ <base>_DB.bvr, evita conflito de .conf com o .pcb),
# alinha a foto do XZZ por baixo (rotacao auto pelo eixo de divisao) e gera um
# thumbnail de verificacao (pinos sobre o bg). Monta um contact sheet.
#
# Uso: python batch_bvr.py [contact.png]
import os, re, glob, zipfile, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import align_bvr as V, align_bg as A
from paths import BV, DRONES as DR

ZIP = 'E:/pcbs/PDFJS-2774a1fbd651bcabc635e43aa971f86a3530321a.zip'
SCR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BV, 'contact_bvr.png')

def photo_of(pcb):
    d = os.path.dirname(pcb); base = os.path.splitext(os.path.basename(pcb))[0]
    conf = os.path.join(d, base + '.conf')
    if not os.path.exists(conf): return None
    m = re.search(r'(?m)^TopImageFile\s*=\s*(.+)$', open(conf, encoding='utf-8', errors='replace').read())
    if not m: return None
    p = os.path.join(d, m.group(1).strip())
    return p if os.path.exists(p) else None

# indexa .bvr do repo por nome-base minusculo
zf = zipfile.ZipFile(ZIP)
bvr_members = {}
for n in zf.namelist():
    m = re.search(r'/build/DRONE/(.+)\.bvr$', n, re.I)
    if m: bvr_members[m.group(1).lower()] = n

def overlay_thumb(bvr, bgpath, conf, W=560):
    segs, pins, _ = V.parse_bvr(bvr)
    bg = Image.open(bgpath).convert('RGB')
    t = open(conf, encoding='utf-8', errors='replace').read()
    sx = float(re.search(r'TopImageScalingX = ([\d.]+)', t)[1])
    sy = float(re.search(r'TopImageScalingY = ([\d.]+)', t)[1])
    d = ImageDraw.Draw(bg); H = bg.height; Wd = bg.width
    for (x, y) in pins[::2]:
        px = x / sx; py = H - 1 - y / sy
        d.ellipse([px-4, py-4, px+4, py+4], outline=(0, 255, 255), width=3)
    scale = W / bg.width
    return bg.resize((W, int(bg.height * scale)), Image.LANCZOS)

def main():
    rows = []
    for pcb in sorted(glob.glob(DR + '/**/*.pcb', recursive=True)):
        if '__MACOSX' in pcb or os.path.basename(pcb).startswith('._'): continue
        base = os.path.splitext(os.path.basename(pcb))[0]
        if base.lower() not in bvr_members or 'yidiantong' in base.lower(): continue
        photo = photo_of(pcb)
        if not photo: continue
        d = os.path.dirname(pcb)
        bvr = os.path.join(d, base + '_DB.bvr')
        try:
            with open(bvr, 'wb') as f:
                f.write(zf.read(bvr_members[base.lower()]))
            # testa rot0 e rot90, escolhe a de MENOR dispersao (auto-corrige rotacao);
            # dentro da familia mantem a variante nao-espelhada (auto_flip cuida da face)
            def run(rot):
                r = subprocess.run(['python', os.path.join(BV, 'align_bvr.py'), bvr, photo, str(rot), '0'],
                                   capture_output=True, text=True)
                m = re.search(r'disp ([\d.]+)%', r.stdout)
                return (float(m.group(1)) if m else 1e9), r
            cands = {rot: run(rot) for rot in (0, 90)}
            rot = min(cands, key=lambda k: cands[k][0])
            disp_v, r = cands[rot]
            if rot != 90:  # re-roda a vencedora p/ deixar bg/conf dela no disco
                disp_v, r = run(rot)
            conf = re.sub(r'\.bvr$', '.conf', bvr, flags=re.I)
            flip = re.search(r'flip_secao=\[([^\]]*)\]', r.stdout)
            ok = os.path.exists(conf) and 'AVISO' not in r.stdout and 'Traceback' not in r.stderr
            print(f'{base:45} rot{rot} disp={disp_v:.1f}% flip=[{flip.group(1) if flip else "?"}] {"OK" if ok else "FALHOU:"+(r.stdout+r.stderr).strip()[-90:]}')
            if ok:
                th = overlay_thumb(bvr, re.sub(r'\.bvr$', '_bg.png', bvr, flags=re.I), conf)
                rows.append((base, rot, f'{disp_v:.1f}', th))
        except Exception as e:
            print(f'{base:45} ERRO {e}')
    # contact sheet
    if not rows: print('nada processado'); return
    cols = 3
    tw = rows[0][3].width
    pad = 8; lbl = 26
    cellh = max(r[3].height for r in rows) + lbl + pad
    nrows = (len(rows) + cols - 1) // cols
    sheet = Image.new('RGB', (cols*(tw+pad)+pad, nrows*cellh+pad), (25, 30, 40))
    dd = ImageDraw.Draw(sheet)
    for i, (base, rot, disp, th) in enumerate(rows):
        cx = pad + (i % cols)*(tw+pad); cy = pad + (i//cols)*cellh
        dd.text((cx, cy), f'{base[:44]}  rot{rot} disp{disp}%', fill=(255, 255, 255))
        sheet.paste(th, (cx, cy+lbl))
    sheet.save(SCR)
    print(f'\ncontact sheet -> {SCR}  ({len(rows)} placas)')

if __name__ == '__main__':
    main()
