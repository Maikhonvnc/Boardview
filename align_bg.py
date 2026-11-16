# Alinha foto de placa com boardview XZZPCB para background image do OpenBoardView.
# Uso: python align_bg.py <arquivo.pcb> <foto> [nome_saida_bg.png]
#
# Pipeline:
#  1. Parse do contorno (layer 28, blocos 0x05/0x01, escala 10000, min->(0,0)) — replica XZZPCBFile.cpp.
#  2. Ilhas do contorno por conectividade (union-find) agrupadas por faixas de X.
#  3. Blobs da placa na foto (threshold vs cor de fundo + densidade por coluna).
#  4. Se n_blobs == n_ilhas: recompoe canvas RGBA por secao (cada blob esticado
#     exatamente sobre o bbox da sua ilha) => offset 0, escala uniforme, fit exato.
#     Senao: mapeamento global bbox-uniao (aviso).
#  5. Grava Top/BottomImage* no <arquivo>.conf ao lado do .pcb.
import struct, sys, math, re, os
import numpy as np
from PIL import Image

SCALE = 10000

def parse_outline_segments(pcb_path):
    data = open(pcb_path, 'rb').read()
    idx = data.find(b'v6v6555v6v6')
    end = idx if idx != -1 else len(data)
    xk = data[0x10]
    if xk != 0:
        data = bytes(b ^ xk for b in data[:end]) + data[end:]
    u32 = lambda o: struct.unpack_from('<I', data, o)[0]
    main_start = u32(0x20) + 0x20
    total = u32(main_start)
    p = main_start + 4
    stop = main_start + 4 + total
    segs = []
    while p < stop:
        btype = data[p]; p += 1
        bsize = u32(p); p += 4
        off = p; p += bsize
        if btype == 0x05:
            layer, x1, y1, x2, y2 = struct.unpack_from('<5I', data, off)
            if layer == 28:
                segs.append(((x1 // SCALE, y1 // SCALE), (x2 // SCALE, y2 // SCALE)))
        elif btype == 0x01:
            layer, x, y, r, a0, a1 = struct.unpack_from('<6I', data, off)
            if layer == 28:
                cx, cy, rr = x // SCALE, y // SCALE, r // SCALE
                a0, a1 = a0 // SCALE, a1 // SCALE
                if a0 > a1: a0, a1 = a1, a0
                if a1 - a0 > 180: a0 += 360
                prev = None
                for i in range(10):
                    ang = math.radians(a0 + (a1 - a0) * i / 9.0)
                    pt = (int(cx + rr * math.cos(ang)), int(cy + rr * math.sin(ang)))
                    if prev is not None: segs.append((prev, pt))
                    prev = pt
    if not segs:
        sys.exit("nenhum segmento de contorno (layer 28)")
    mnx = min(min(a[0], b[0]) for a, b in segs)
    mny = min(min(a[1], b[1]) for a, b in segs)
    return [((a[0]-mnx, a[1]-mny), (b[0]-mnx, b[1]-mny)) for a, b in segs]

def connected_components(segs):
    parent = {}
    def key(p): return (p[0] // 3, p[1] // 3)
    def find(k):
        while parent.get(k, k) != k: k = parent[k]
        return k
    for a, b in segs:
        ka, kb = key(a), key(b)
        parent.setdefault(ka, ka); parent.setdefault(kb, kb)
        ra, rb = find(ka), find(kb)
        if ra != rb: parent[ra] = rb
    groups = {}
    for a, b in segs:
        groups.setdefault(find(key(a)), []).extend([a, b])
    return list(groups.values())

def bbox(pts):
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))

def group_islands(comps, n_target):
    # divide os componentes em n_target grupos cortando nos n_target-1 maiores
    # vaos positivos de X entre um grupo e o proximo (guiado pela foto)
    boxes = sorted((bbox(c), c) for c in comps)
    gaps = []  # (tamanho_do_vao, indice_do_corte)
    run_max = boxes[0][0][2]
    for i, (bx, _) in enumerate(boxes[1:], start=1):
        gap = bx[0] - run_max
        if gap > 0:
            gaps.append((gap, i))
        run_max = max(run_max, bx[2])
    cuts = sorted(i for _, i in sorted(gaps, reverse=True)[:n_target - 1])
    if len(cuts) < n_target - 1:
        return None  # nao ha vaos suficientes
    islands, prev = [], 0
    for c in cuts + [len(boxes)]:
        islands.append([p for _, comp in boxes[prev:c] for p in comp])
        prev = c
    return islands

def find_image_blobs(img):
    a = np.asarray(img.convert('RGB')).astype(int)
    h, w, _ = a.shape
    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    mask = np.abs(a - bg).sum(axis=2) > 60
    cols = mask.sum(axis=0)
    active = cols > 0.02 * h
    ranges, start = [], None
    for x in range(w):
        if active[x] and start is None: start = x
        if not active[x] and start is not None:
            ranges.append((start, x - 1)); start = None
    if start is not None: ranges.append((start, w - 1))
    merged = []
    for r in ranges:
        if merged and r[0] - merged[-1][1] < 0.02 * w:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append((r[0], r[1]))
    merged = [r for r in merged if r[1] - r[0] > 0.1 * w]
    blobs = []
    for x0, x1 in merged:
        sub = mask[:, x0:x1 + 1]
        rows = sub.sum(axis=1)
        act = np.where(rows > 0.02 * (x1 - x0))[0]
        blobs.append((x0, int(act.min()), x1, int(act.max())))
    return blobs

def update_conf(conf_path, keyvals):
    try:
        text = open(conf_path, encoding='utf-8', errors='replace').read()
    except FileNotFoundError:
        text = ''
    for k, v in keyvals.items():
        pat = re.compile(r'(?m)^%s\s*=.*$' % re.escape(k))
        line = f"{k} = {v}"
        if pat.search(text):
            text = pat.sub(line.replace('\\', '\\\\'), text)
        else:
            text += ("" if text.endswith("\n") or not text else "\n") + line + "\n"
    open(conf_path, 'w', encoding='utf-8', newline='\n').write(text)

def main():
    pcb_path, img_path = sys.argv[1], sys.argv[2]
    out_name = sys.argv[3] if len(sys.argv) > 3 else \
        os.path.basename(re.sub(r'\.pcb$', '_bg.png', pcb_path, flags=re.I))
    out_path = os.path.join(os.path.dirname(pcb_path), out_name)

    segs = parse_outline_segments(pcb_path)
    comps = connected_components(segs)
    total = bbox([p for s in segs for p in s])
    W_u, H_u = total[2] - total[0], total[3] - total[1]

    img = Image.open(img_path)
    blobs = find_image_blobs(img)
    blobs.sort(key=lambda b: b[0])
    print(f"foto {img.width}x{img.height}px, {len(blobs)} blob(s): {blobs}")

    islands = group_islands(comps, len(blobs))
    print(f"placa: {W_u} x {H_u} unidades, {len(comps)} comps -> "
          + (f"{len(islands)} ilha(s): " + ", ".join(str(bbox(i)) for i in islands) if islands else "sem divisao"))

    if islands and len(blobs) == len(islands) and len(blobs) >= 1:
        pairs = list(zip(sorted(islands, key=lambda i: bbox(i)[0]), blobs))
        ppus = []
        for isl, bl in pairs:
            ib = bbox(isl)
            ppus += [(bl[2]-bl[0]) / (ib[2]-ib[0]), (bl[3]-bl[1]) / (ib[3]-ib[1])]
        ppu = sum(ppus) / len(ppus)
        print(f"por secao, ppu: {[f'{v:.3f}' for v in ppus]} -> {ppu:.4f} (dispersao {(max(ppus)-min(ppus))/ppu*100:.1f}%)")
        cw, ch = int(round(W_u * ppu)), int(round(H_u * ppu))
        canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        src = img.convert('RGBA')
        for isl, bl in pairs:
            ib = bbox(isl)
            crop = src.crop((bl[0], bl[1], bl[2] + 1, bl[3] + 1))
            tw = max(1, int(round((ib[2]-ib[0]) * ppu)))
            th = max(1, int(round((ib[3]-ib[1]) * ppu)))
            crop = crop.resize((tw, th), Image.LANCZOS)
            canvas.paste(crop, (int(round(ib[0] * ppu)), int(round((H_u - ib[3]) * ppu))))
        canvas.save(out_path)
        sx, sy = W_u / canvas.width, H_u / canvas.height
        offx = offy = 0
        print(f"composto: {canvas.width}x{canvas.height}px -> {out_path}")
    else:
        print("AVISO: sem divisao por secao, usando mapeamento global do bbox uniao")
        ux0 = min(b[0] for b in blobs); uy0 = min(b[1] for b in blobs)
        ux1 = max(b[2] for b in blobs); uy1 = max(b[3] for b in blobs)
        sx = W_u / float(ux1 - ux0); sy = H_u / float(uy1 - uy0)
        offx = int(round(-ux0 * sx)); offy = int(round(-(img.height - uy1) * sy))
        img.convert('RGB').save(out_path)

    conf_path = re.sub(r'\.pcb$', '.conf', pcb_path, flags=re.I)
    kv = {}
    for P in ('Top', 'Bottom'):
        kv.update({
            f'{P}ImageFile': out_name,
            f'{P}ImageOffsetX': offx, f'{P}ImageOffsetY': offy,
            f'{P}ImageScalingX': f"{sx:.6f}", f'{P}ImageScalingY': f"{sy:.6f}",
            f'{P}ImageMirrorX': 'false', f'{P}ImageMirrorY': 'false',
            f'{P}ImageTransparency': '0.000000',
        })
    update_conf(conf_path, kv)
    print(f"conf: {conf_path}  scaling {sx:.6f}/{sy:.6f}  offset {offx},{offy}")

if __name__ == '__main__':
    main()
