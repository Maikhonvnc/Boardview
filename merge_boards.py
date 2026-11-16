# Junta varias placas XZZ num unico arquivo .brd (ASCII, formato aberto do OBV),
# dispostas lado a lado (offset X + gap). Abre no OpenBoardView completo.
# Contorno: segmentos tracados em loops (a logica de hull do OBV levanta a caneta
# entre loops fechados). Nets prefixadas por placa (tag) p/ nao misturar malhas.
# Uso: python merge_boards.py <saida.brd> <tag1>=<pcb1> <tag2>=<pcb2> ...
#   ou: python merge_boards.py <saida.brd> <pcb1> <pcb2> ...   (tags automaticas)
import sys, os, re
from collections import defaultdict
from xzz_parts import load_parts
from align_bg import parse_outline_segments
from annotate import outline_min

GAP = 400  # distancia entre placas (unidades)

def trace_loops(segs):
    adj = defaultdict(list)
    for i, (a, b) in enumerate(segs):
        adj[a].append((i, b)); adj[b].append((i, a))
    used = [False] * len(segs)
    loops = []
    for si in range(len(segs)):
        if used[si]: continue
        a, b = segs[si]; used[si] = True
        chain = [a, b]; cur = b
        while True:
            nxt = None
            for (j, other) in adj[cur]:
                if not used[j]:
                    nxt = (j, other); break
            if nxt is None: break
            used[nxt[0]] = True; chain.append(nxt[1]); cur = nxt[1]
            if cur == chain[0]: break
        loops.append(chain)
    return loops

def autotag(pcb, idx):
    b = re.sub(r'\.pcb$', '', os.path.basename(pcb), flags=re.I)
    b = re.sub(r'(?i)\s*PCB\s*layer', '', b)
    m = re.search(r'(?i)(MB|SUB\s*[AB]|YiDianTong|Electrical\s*reg\w*|CPU[^-]*|short\s*circuit|gasket)', b)
    if m:
        return re.sub(r'\s+', '', m.group(1))[:8].upper()
    m = re.search(r'PP?\d{5,}[._]?\d*', b)
    return (m.group(0).replace('.', '').replace('_', '')[-6:] if m else 'B%d' % idx).upper()

def load_board(pcb):
    nets, parts = load_parts(pcb)
    segs_raw = parse_outline_segments(pcb)                  # 0-based (min->0)
    mnx, mny = outline_min(pcb)
    segs = [((int(a[0]), int(a[1])), (int(b[0]), int(b[1]))) for a, b in segs_raw]
    # pins 0-based
    comps = []
    for pname, pins in parts:
        pl = [(pn, net, int(x - mnx), int(y - mny)) for pn, net, x, y in pins]
        if pl: comps.append((pname, pl))
    maxX = max((max(s[0][0], s[1][0]) for s in segs), default=0)
    maxY = max((max(s[0][1], s[1][1]) for s in segs), default=0)
    return segs, comps, maxX, maxY

def main():
    out = sys.argv[1]
    specs = sys.argv[2:]
    boards = []
    for i, sp in enumerate(specs):
        if '=' in sp and not os.path.exists(sp):
            tag, pcb = sp.split('=', 1)
        else:
            pcb, tag = sp, autotag(sp, i)
        boards.append((tag.strip(), pcb))

    fmt_lines, part_lines, pin_lines = [], [], []
    nformat = nparts = npins = 0
    ox = 0
    legend = []
    for tag, pcb in boards:
        segs, comps, maxX, maxY = load_board(pcb)
        legend.append(f"{tag} = {os.path.basename(pcb)}")
        # contorno: cada segmento vira triplo A,B,A (mini-loop fechado) para o OBV
        # levantar a caneta entre segmentos (DrawOutlinePoints usa deteccao de hull).
        for (a, b) in segs:
            if a == b:
                continue
            ax, ay = a[0] + ox, a[1]; bx, by = b[0] + ox, b[1]
            fmt_lines.append(f"{ax} {ay}")
            fmt_lines.append(f"{bx} {by}")
            fmt_lines.append(f"{ax} {ay}")
            nformat += 3
        # parts/pins
        for pname, pins in comps:
            for (pn, net, x, y) in pins:
                npins += 1
                netname = f"{tag}.{net}" if net else ""
                pin_lines.append(f"{x + ox} {y} 1 {nparts + 1} {netname}")
            nparts += 1
            part_lines.append(f"{tag}:{pname} 4 {npins}")   # 4 = SMD Top
        ox += maxX + GAP

    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write("str_length:\n0\nvar_data:\n")
        f.write(f"{nformat} {nparts} {npins} 0\n")
        f.write("Format:\n"); f.write("\n".join(fmt_lines) + "\n")
        f.write("Parts:\n");  f.write("\n".join(part_lines) + "\n")
        f.write("Pins:\n");   f.write("\n".join(pin_lines) + "\n")
        f.write("Nails:\n")
    print(f"{out}: {len(boards)} placa(s), {nparts} parts, {npins} pins, {nformat} pts contorno")
    for l in legend: print("  " + l)

if __name__ == '__main__':
    main()
