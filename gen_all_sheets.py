import os, sys, csv, re
from collections import OrderedDict
from xzz_parts import load_parts

def natural(r):
    m = re.match(r'([A-Za-z]+)(\d+)', r)
    return (m.group(1), int(m.group(2))) if m else (r, 0)

def gen(pcb, out):
    nets, parts = load_parts(pcb)
    if not parts: return 0
    rows = []
    for pname, pins in parts:
        uniq = list(OrderedDict.fromkeys(net for _, net, _, _ in pins))
        signal = [n for n in uniq if n != 'GND'] or uniq
        rows.append((pname, ' / '.join(uniq), len(pins), signal[0] if signal else ''))
    rows.sort(key=lambda r: natural(r[0]))
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Componente', 'Nets', 'NpPinos', 'NetPrincipal', 'Tensao', 'Obs'])
        for r in rows: w.writerow([r[0], r[1], r[2], r[3], '', ''])
    return len(rows)

root, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
for dp, dirs, files in os.walk(root):
    if '__MACOSX' in dp: continue
    for fn in sorted(files):
        if fn.lower().endswith('.pcb') and not fn.startswith('._'):
            base = re.sub(r'\.pcb$', ' - caderno.csv', fn, flags=re.I)
            n = gen(os.path.join(dp, fn), os.path.join(outdir, base))
            print(f"{fn} -> {n} componentes")
