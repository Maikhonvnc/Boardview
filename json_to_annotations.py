# Converte o JSON Digital Board (skilbypm v1.0) em anotacoes OBV: cada pino com
# diodeReading (ou campo de tensao) vira etiqueta clicavel no ponto certo.
# Coord OBV = pin.x + dx, pin.y + dy, onde (dx,dy) alinha o JSON ao .pcb do usuario
# (JSON ja vem transladado; ajuste fino comparando componentes comuns).
# Uso: python json_to_annotations.py <board.json> <board.pcb> [--apply]
import json, sys, os, re, sqlite3
from xzz_parts import load_parts
from annotate import outline_min, sqlite_name

VOLT_KEYS = ('voltage','volt','tensao','vcc','value2')  # tolerante a versoes futuras

def coord_offset(jd, pcb):
    # casa componentes por nome entre JSON e .pcb; dx,dy medianos
    _, parts = load_parts(pcb)
    mnx, mny = outline_min(pcb)
    pcb_pos = {}
    for pname, pins in parts:
        if pins:
            pcb_pos[pname] = (pins[0][2]-mnx, pins[0][3]-mny)  # 1o pino, coord OBV
    dxs, dys = [], []
    for c in jd['components']:
        nm = c.get('id') or c.get('name')
        pins = c.get('pins') or []
        if nm in pcb_pos and pins:
            jx, jy = pins[0]['x'], pins[0]['y']
            ox, oy = pcb_pos[nm]
            dxs.append(ox-jx); dys.append(oy-jy)
    if not dxs:
        return 0.0, 0.0, 0
    dxs.sort(); dys.sort()
    return dxs[len(dxs)//2], dys[len(dys)//2], len(dxs)

def readings(jd):
    for c in jd['components']:
        part = c.get('id') or c.get('name')
        for p in c.get('pins', []):
            val = str(p.get('diodeReading','') or '').strip()
            label = 'diodo' if val else ''
            if not val:
                for vk in VOLT_KEYS:
                    v = str(p.get(vk,'') or '').strip()
                    if v: val, label = v, 'V'; break
            if val:
                note = f'{val}' if label!='diodo' else f'D {val}'
                yield part, p.get('name',''), p.get('netName',''), p['x'], p['y'], note

def main():
    jpath, pcb = sys.argv[1], sys.argv[2]
    apply = '--apply' in sys.argv
    jd = json.load(open(jpath, encoding='utf-8'))
    dx, dy, nmatch = coord_offset(jd, pcb)
    print(f"offset JSON->OBV: dx={dx:.1f} dy={dy:.1f} (de {nmatch} componentes casados)")
    rs = list(readings(jd))
    print(f"leituras (diodo/tensao) no JSON: {len(rs)}")
    if not rs:
        print("  (JSON ainda sem leituras — a galera do Digital Board esta preenchendo)")
    for part, pin, net, x, y, note in rs[:8]:
        print(f"  {part}.{pin} [{net}] @ ({x:.0f},{y:.0f}) = {note}")
    if not apply or not rs:
        if apply: print("nada para gravar")
        return
    db = sqlite_name(pcb)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS annotations(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "visible INTEGER, pin TEXT, part TEXT, net TEXT, posx INTEGER, posy INTEGER,"
                "side INTEGER, note TEXT);")
    # remove anotacoes antigas desta origem (prefixo marcador) p/ reimportar limpo
    con.execute("DELETE FROM annotations WHERE note LIKE 'DB:%'")
    n = 0
    for part, pin, net, x, y, note in rs:
        con.execute("INSERT INTO annotations(visible,pin,part,net,posx,posy,side,note)"
                    " VALUES(1,?,?,?,?,?,0,?)",
                    (pin, part, net, int(round(x+dx)), int(round(y+dy)), 'DB:'+note))
        n += 1
    con.commit(); con.close()
    print(f"gravadas {n} anotacoes em {os.path.basename(db)} (prefixo DB:)")

if __name__ == '__main__':
    main()
