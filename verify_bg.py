# Desenha contorno (layer 28) e test pads (bloco 0x09) do .pcb sobre a foto,
# usando o mapeamento do .conf, para inspecionar o alinhamento visualmente.
# Tambem clusteriza o contorno por conectividade (union-find) p/ listar ilhas.
# Uso: python verify_bg.py <arquivo.pcb> <foto> <saida.png>
import struct, sys, math, re
from PIL import Image, ImageDraw

SCALE = 10000

def load(pcb_path):
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
    segs, pads = [], []
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
        elif btype == 0x09:
            x, y = struct.unpack_from('<2I', data, off + 4)
            pads.append((x // SCALE, y // SCALE))
    mnx = min(min(a[0], b[0]) for a, b in segs)
    mny = min(min(a[1], b[1]) for a, b in segs)
    segs = [((a[0]-mnx, a[1]-mny), (b[0]-mnx, b[1]-mny)) for a, b in segs]
    pads = [(x-mnx, y-mny) for x, y in pads]
    return segs, pads

def islands(segs):
    # union-find sobre endpoints arredondados (tolerancia 3 unidades)
    parent = {}
    def key(p): return (p[0] // 3, p[1] // 3)
    def find(k):
        while parent.get(k, k) != k: k = parent[k]
        return k
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    for a, b in segs:
        ka, kb = key(a), key(b)
        parent.setdefault(ka, ka); parent.setdefault(kb, kb)
        union(ka, kb)
    groups = {}
    for a, b in segs:
        groups.setdefault(find(key(a)), []).append((a, b))
    return list(groups.values())

def main():
    pcb_path, img_path, out_png = sys.argv[1], sys.argv[2], sys.argv[3]
    segs, pads = load(pcb_path)
    comps = islands(segs)
    comps.sort(key=lambda c: -len(c))
    print(f"{len(segs)} segs, {len(pads)} test pads, {len(comps)} componentes conexos:")
    for c in comps[:8]:
        xs = [p[0] for s in c for p in s]; ys = [p[1] for s in c for p in s]
        print(f"  comp {len(c)} segs, bbox x {min(xs)}..{max(xs)}  y {min(ys)}..{max(ys)}")

    conf_path = re.sub(r'\.pcb$', '.conf', pcb_path, flags=re.I)
    conf = open(conf_path, encoding='utf-8', errors='replace').read()
    g = lambda k, d=0.0: float(re.search(r'(?m)^%s\s*=\s*([-\d.]+)' % k, conf).group(1)) if re.search(r'(?m)^%s\s*=\s*([-\d.]+)' % k, conf) else d
    offx, offy, sx, sy = g('TopImageOffsetX'), g('TopImageOffsetY'), g('TopImageScalingX', 1), g('TopImageScalingY', 1)
    print(f"conf: offset {offx},{offy} scaling {sx}/{sy}")

    im = Image.open(img_path).convert('RGB')
    dr = ImageDraw.Draw(im)
    H = im.height
    def to_px(x, y):
        return ((x - offx) / sx, H - (y - offy) / sy)
    for a, b in segs:
        dr.line([to_px(*a), to_px(*b)], fill=(255, 0, 0), width=5)
    for x, y in pads:
        px, py = to_px(x, y)
        dr.ellipse([px-6, py-6, px+6, py+6], outline=(0, 255, 0), width=3)
    im.thumbnail((1600, 1600))
    im.save(out_png)
    print(f"overlay: {out_png}")

if __name__ == '__main__':
    main()
