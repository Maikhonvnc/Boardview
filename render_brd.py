# Renderiza um .brd usando o MESMO algoritmo de contorno do OBV (DrawOutlinePoints)
# para prever fielmente o que o OpenBoardView vai mostrar. Desenha contorno + pinos.
import sys
from PIL import Image, ImageDraw

def load_brd(path):
    fmt, pins = [], []
    blk = None
    for line in open(path, encoding='utf-8'):
        t = line.strip()
        if t == 'Format:': blk = 'f'; continue
        if t == 'Parts:': blk = 'p'; continue
        if t == 'Pins:': blk = 'i'; continue
        if t == 'Nails:': blk = 'n'; continue
        if t in ('str_length:', 'var_data:') or not t:
            if blk is None: continue
        if blk == 'f':
            p = t.split()
            if len(p) == 2:
                try: fmt.append((int(p[0]), int(p[1])))
                except: pass
        elif blk == 'i':
            p = t.split()
            if len(p) >= 4:
                try: pins.append((int(p[0]), int(p[1]), p[4] if len(p) > 4 else ''))
                except: pass
    return fmt, pins

def outline_segments_obv(fmt):
    # replica BoardView::DrawOutlinePoints (com deteccao de hull/jump)
    segs = []
    n = len(fmt)
    if n < 1: return segs
    jump = 1
    fp = fmt[0]
    i = 0
    while i < n - 1:
        pa = fmt[i]; pb = fmt[i + 1]
        if pa == pb:
            i += 1; continue
        if (not jump) and fp == pb:
            if i < n - 2:
                fp = fmt[i + 2]; jump = 1; i += 1
        else:
            jump = 0
        segs.append((pa, pb))
        i += 1
    return segs

def main():
    brd, out = sys.argv[1], sys.argv[2]
    fmt, pins = load_brd(brd)
    xs = [p[0] for p in fmt] + [p[0] for p in pins]
    ys = [p[1] for p in fmt] + [p[1] for p in pins]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    W = 1600; sc = W / (maxx - minx); H = int((maxy - miny) * sc) + 20
    img = Image.new('RGB', (W + 20, H), (11, 14, 19))
    dr = ImageDraw.Draw(img)
    def X(x): return int((x - minx) * sc) + 10
    def Y(y): return H - (int((y - miny) * sc) + 10)   # flip Y
    for x, y, net in pins:
        c = (51, 65, 85) if net.endswith('.GND') else (34, 170, 51)
        dr.ellipse([X(x)-1, Y(y)-1, X(x)+1, Y(y)+1], fill=c)
    for a, b in outline_segments_obv(fmt):
        dr.line([X(a[0]), Y(a[1]), X(b[0]), Y(b[1])], fill=(203, 213, 225), width=1)
    img.save(out)
    print(f"{out}: {len(fmt)} pts contorno -> {len(outline_segments_obv(fmt))} linhas, {len(pins)} pinos, {W+20}x{H}px")

if __name__ == '__main__':
    main()
