# Injeta anotacoes no banco do OpenBoardView (<base>_pcb.sqlite3) a partir de um
# CSV de mapa. Serve p/ reproduzir "mapa de tensoes" e marcacao 2.4/5.8 do Digital
# Board: os dados vem do CSV (medidos/curados), as POSICOES vem da netlist do .pcb.
#
# CSV de mapa (cabecalho obrigatorio), 1 linha por alvo:
#   tipo,alvo,nota
#   net,VBAT_net_name,7.6V            -> etiqueta em um ponto da net
#   net,SNet123,3V3                   -> idem
#   part,U1201,PMIC 2.4G TX           -> etiqueta no componente
#   pin,U1201-A5,5V8 rail             -> etiqueta num pino especifico (part-pin)
# "alvo" para net = nome exato da net; para part = nome do componente;
#          para pin = "Componente-Pino".
#
# Uso: python annotate.py <arquivo.pcb> <mapa.csv> [--side N] [--wipe]
import struct, sys, csv, re, os, sqlite3
from collections import defaultdict
from xzz_parts import load_parts

def outline_min(path):
    data = open(path, 'rb').read()
    idx = data.find(b'v6v6555v6v6'); end = idx if idx != -1 else len(data)
    xk = data[0x10]
    if xk: data = bytes(c ^ xk for c in data[:end]) + data[end:]
    u32 = lambda o: struct.unpack_from('<I', data, o)[0]
    ms = u32(0x20) + 0x20
    pt, stop = ms + 4, ms + 4 + u32(ms)
    mnx = mny = None
    while pt < stop:
        bt = data[pt]; sz = u32(pt+1); off = pt+5; pt += 5 + sz
        if bt == 5:  # line segment
            layer = u32(off)
            if layer == 28:
                for ox in (u32(off+4), u32(off+12)):
                    mnx = ox if mnx is None else min(mnx, ox)
                for oy in (u32(off+8), u32(off+16)):
                    mny = oy if mny is None else min(mny, oy)
    return (mnx or 0)//10000, (mny or 0)//10000

def sqlite_name(pcb):
    base, _ = os.path.splitext(pcb)  # troca ultima extensao
    return base + '_pcb.sqlite3'

def main():
    pcb = sys.argv[1]; mapcsv = sys.argv[2]
    side = int(sys.argv[sys.argv.index('--side')+1]) if '--side' in sys.argv else 0
    wipe = '--wipe' in sys.argv
    nets, parts = load_parts(pcb)
    mnx, mny = outline_min(pcb)

    # indices: net -> lista de (x,y); part -> (x,y centroide, pins); (part,pin)->(x,y,net)
    net_pts = defaultdict(list)
    part_pts = defaultdict(list)
    pin_idx = {}
    for pname, pins in parts:
        for pinname, net, x, y in pins:
            net_pts[net].append((x, y))
            part_pts[pname].append((x, y))
            pin_idx[(pname, pinname)] = (x, y, net)

    def centroid(pts):
        return (sum(p[0] for p in pts)//len(pts), sum(p[1] for p in pts)//len(pts))

    db = sqlite_name(pcb)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS annotations(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "visible INTEGER, pin TEXT, part TEXT, net TEXT, posx INTEGER, posy INTEGER,"
                "side INTEGER, note TEXT);")
    if wipe:
        con.execute("DELETE FROM annotations;")

    # detecta o formato: "caderno" (Componente;Tensao;Obs) ou "mapa" (tipo,alvo,nota)
    with open(mapcsv, encoding='utf-8-sig') as f:
        head = f.readline()
    delim = ';' if head.count(';') >= head.count(',') else ','
    caderno = 'Componente' in head

    def rows_from_caderno(f):
        for row in csv.DictReader(f, delimiter=';'):
            v = (row.get('Tensao') or '').strip()
            if not v:
                continue  # so linhas medidas
            obs = (row.get('Obs') or '').strip()
            nota = f"{v} — {obs}" if obs else v
            yield 'part', (row.get('Componente') or '').strip(), nota

    def rows_from_mapa(f):
        for row in csv.DictReader(f, delimiter=delim):
            yield ((row.get('tipo') or '').strip().lower(),
                   (row.get('alvo') or '').strip(),
                   (row.get('nota') or '').strip())

    added = miss = 0
    with open(mapcsv, encoding='utf-8-sig') as f:
        reader = rows_from_caderno(f) if caderno else rows_from_mapa(f)
        for tipo, alvo, nota in reader:
            if not tipo or not alvo or not nota:
                continue
            net = part = pin = ''
            if tipo == 'net':
                if alvo not in net_pts: miss += 1; continue
                x, y = centroid(net_pts[alvo]); net = alvo
            elif tipo == 'part':
                if alvo not in part_pts: miss += 1; continue
                x, y = centroid(part_pts[alvo]); part = alvo
            elif tipo == 'pin':
                key = tuple(alvo.split('-', 1))
                if len(key) != 2 or key not in pin_idx: miss += 1; continue
                x, y, net = pin_idx[key]; part, pin = key
            else:
                continue
            con.execute("INSERT INTO annotations(visible,pin,part,net,posx,posy,side,note)"
                        " VALUES(1,?,?,?,?,?,?,?)",
                        (pin, part, net, x - mnx, y - mny, side, nota))
            added += 1
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
    con.close()
    print(f"{db}: +{added} anotacoes (nao encontradas: {miss}); total no banco: {n}")

if __name__ == '__main__':
    main()
