# Exporta um .pcb para Boardview/boards/<base>.js (window.BOARD=...) que o
# viewer.html local renderiza offline. Coords em espaco OBV (alinha com a foto).
# Se houver JSON Digital Board com diodeReading, mescla as leituras.
# Uso: python export_board.py <arquivo.pcb> <outdir_boards> [board.json]
import sys, os, re, json
from xzz_parts import load_parts
from align_bg import parse_outline_segments
from annotate import outline_min

def furl(p):
    return 'file:///' + p.replace('\\', '/').replace('#', '%23').replace(' ', '%20')

def export(pcb, outdir, jsonpath=None):
    nets, parts = load_parts(pcb)
    segs = parse_outline_segments(pcb)          # ja 0-based (min->0)
    mnx, mny = outline_min(pcb)
    outline = [[a[0], a[1], b[0], b[1]] for a, b in segs]
    maxX = max((max(s[0], s[2]) for s in outline), default=0)
    maxY = max((max(s[1], s[3]) for s in outline), default=0)
    # leituras do JSON (por componente.pino)
    reads = {}
    if jsonpath and os.path.exists(jsonpath):
        jd = json.load(open(jsonpath, encoding='utf-8'))
        for c in jd.get('components', []):
            cid = c.get('id') or c.get('name')
            for p in c.get('pins', []):
                dr = str(p.get('diodeReading', '') or '').strip()
                if dr:
                    reads[(cid, str(p.get('name', '')))] = dr
    comps = []
    for pname, pins in parts:
        pl = []
        for pinname, net, x, y in pins:
            pl.append({'x': round(x - mnx, 1), 'y': round(y - mny, 1),
                       'name': pinname, 'net': net,
                       'r': reads.get((pname, str(pinname)))})
        if pl:
            cx = round(sum(p['x'] for p in pl) / len(pl), 1)
            cy = round(sum(p['y'] for p in pl) / len(pl), 1)
            comps.append({'id': pname, 'x': cx, 'y': cy, 'pins': pl})
    base = re.sub(r'\.pcb$', '', os.path.basename(pcb))
    # foto de fundo (_bg.png ao lado do .pcb)
    photo = None
    for cand in (base + '_bg.png', base + '_bg.jpg'):
        pp = os.path.join(os.path.dirname(pcb), cand)
        if os.path.exists(pp):
            photo = furl(pp); break
    board = {'name': base, 'bbox': {'minX': 0, 'minY': 0, 'maxX': maxX, 'maxY': maxY},
             'outline': outline, 'comps': comps}
    if photo:
        board['photo'] = photo
    out = os.path.join(outdir, base + '.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('window.BOARD=' + json.dumps(board, ensure_ascii=False, separators=(',', ':')) + ';')
    nr = sum(1 for c in comps for p in c['pins'] if p['r'])
    return len(comps), len(outline), nr, os.path.getsize(out) // 1024

if __name__ == '__main__':
    pcb, outdir = sys.argv[1], sys.argv[2]
    jp = sys.argv[3] if len(sys.argv) > 3 else None
    os.makedirs(outdir, exist_ok=True)
    nc, no, nr, kb = export(pcb, outdir, jp)
    print(f"{os.path.basename(pcb)}: {nc} comps, {no} outline, {nr} leituras, {kb} KB")
