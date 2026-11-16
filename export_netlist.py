# Exporta a netlist de cada .pcb XZZ para CSV: Componente, Pino, Net, X, Y.
# Gera tambem, por placa, um resumo de nets (net -> nº de pinos) para achar rails.
# Uso: python export_netlist.py <raiz Drones> <pasta saida>
import os, sys, csv, re
from collections import defaultdict
from xzz_parts import load_parts

def export(pcb, outdir):
    try:
        nets, parts = load_parts(pcb)
    except Exception as e:
        return f"ERRO {type(e).__name__}: {e}"
    if not parts:
        return "sem parts (formato?)"
    base = re.sub(r'\.pcb$', '', os.path.basename(pcb), flags=re.I)
    # netlist plana
    rows = []
    net_pins = defaultdict(int)
    for pname, pins in parts:
        for pinname, net, x, y in pins:
            rows.append((pname, pinname, net, x, y))
            net_pins[net] += 1
    with open(os.path.join(outdir, base + ' - netlist.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Componente', 'Pino', 'Net', 'X', 'Y'])
        w.writerows(rows)
    # resumo de nets, maiores primeiro (rails de alimentacao/terra no topo)
    with open(os.path.join(outdir, base + ' - nets.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Net', 'Qtd pinos'])
        for net, n in sorted(net_pins.items(), key=lambda kv: -kv[1]):
            w.writerow([net, n])
    return f"{len(parts)} comps, {len(rows)} pinos, {len(net_pins)} nets"

def main():
    root, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for dp, dirs, files in os.walk(root):
        if '__MACOSX' in dp: continue
        for fn in sorted(files):
            if fn.lower().endswith('.pcb') and not fn.startswith('._'):
                print(f"{fn}  ->  {export(os.path.join(dp, fn), outdir)}")

if __name__ == '__main__':
    main()
