# Compoe a foto de fundo do <Modelo> - JUNTO.brd: coloca cada foto _bg de placa
# na posicao X do merge (mesma ordem/gap do merge_boards). Placas sem foto ficam
# vazias. Cria/atualiza o .conf do JUNTO apontando a imagem (offset 0, escala 1/ppu).
import os, sys, re, glob
from PIL import Image
from merge_boards import load_board, GAP
from paths import DRONES

def find_bg(pcb):
    base = re.sub(r'\.pcb$', '', pcb, flags=re.I)
    for c in (base + '_bg.png', base + '_bg.jpg'):
        if os.path.exists(c):
            return c
    return None

def update_conf(conf, kv):
    text = open(conf, encoding='utf-8', errors='replace').read() if os.path.exists(conf) else ''
    for k, v in kv.items():
        line = f'{k} = {v}'
        if re.search(r'(?m)^%s\s*=.*$' % re.escape(k), text):
            text = re.sub(r'(?m)^%s\s*=.*$' % re.escape(k), line, text)
        else:
            text += ('' if text.endswith('\n') or not text else '\n') + line + '\n'
    open(conf, 'w', encoding='utf-8', newline='\n').write(text)

def build(folder):
    fdir = folder
    pcbs = sorted(p for p in glob.glob(os.path.join(fdir, '*.pcb'))
                  if not os.path.basename(p).startswith('._')
                  and 'yidiantong' not in os.path.basename(p).lower())
    if len(pcbs) < 2:
        return None
    # offsets (mesma logica do merge)
    boards = []
    ox = 0; maxH = 0
    for pcb in pcbs:
        segs, comps, mx, my = load_board(pcb)
        boards.append({'pcb': pcb, 'ox': ox, 'w': mx, 'h': my, 'bg': find_bg(pcb)})
        ox += mx + GAP
        maxH = max(maxH, my)
    totalW = ox - GAP
    if not any(b['bg'] for b in boards):
        return None  # nenhuma placa tem foto -> nao vale compor
    ppu = min(1.4, 9000.0 / max(1, totalW))
    cw, ch = int(round(totalW * ppu)), int(round(maxH * ppu))
    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    used = 0
    for b in boards:
        if not b['bg']:
            continue
        img = Image.open(b['bg']).convert('RGBA')
        tw, th = max(1, int(round(b['w'] * ppu))), max(1, int(round(b['h'] * ppu)))
        img = img.resize((tw, th), Image.LANCZOS)
        px = int(round(b['ox'] * ppu))
        py = int(round((maxH - b['h']) * ppu))   # Y flip (topo = maxH)
        canvas.paste(img, (px, py), img)
        used += 1
    model = os.path.basename(fdir.rstrip('/\\'))
    bgname = f'{model} - JUNTO_bg.png'
    canvas.save(os.path.join(fdir, bgname))
    sx = totalW / cw
    conf = os.path.join(fdir, f'{model} - JUNTO.conf')
    kv = {}
    for P in ('Top', 'Bottom'):
        kv.update({f'{P}ImageFile': bgname, f'{P}ImageOffsetX': 0, f'{P}ImageOffsetY': 0,
                   f'{P}ImageScalingX': f'{sx:.6f}', f'{P}ImageScalingY': f'{sx:.6f}',
                   f'{P}ImageMirrorX': 'false', f'{P}ImageMirrorY': 'false',
                   f'{P}ImageTransparency': '0.000000'})
    update_conf(conf, kv)
    return f'{model}: {used}/{len(boards)} placas com foto, canvas {cw}x{ch}px'

if __name__ == '__main__':
    if len(sys.argv) > 1:      # pasta especifica
        r = build(sys.argv[1]); print(r or 'sem foto/placa unica')
    else:                       # todas
        DR = DRONES
        for f in sorted(os.listdir(DR)):
            fd = os.path.join(DR, f)
            if os.path.isdir(fd) and '__MACOSX' not in f:
                r = build(fd)
                if r: print(r)
