# Gera um "caderno de medicao" CSV por placa: um componente por linha, com suas
# nets, para o usuario preencher Tensao/Obs. Depois annotate.py le o caderno
# preenchido e injeta as linhas com Tensao como anotacoes no OBV.
# Uso: python gen_sheet.py <arquivo.pcb> <saida.csv>
import sys, csv, re
from collections import OrderedDict
from xzz_parts import load_parts

def natural(refdes):
    m = re.match(r'([A-Za-z]+)(\d+)', refdes)
    return (m.group(1), int(m.group(2))) if m else (refdes, 0)

def main():
    pcb, out = sys.argv[1], sys.argv[2]
    nets, parts = load_parts(pcb)
    rows = []
    for pname, pins in parts:
        uniq = list(OrderedDict.fromkeys(net for _, net, _, _ in pins))
        signal = [n for n in uniq if n != 'GND'] or uniq   # nets fora de GND primeiro
        rows.append((pname, ' / '.join(uniq), len(pins), signal[0] if signal else ''))
    rows.sort(key=lambda r: natural(r[0]))
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')  # ; = Excel PT-BR abre em colunas direto
        w.writerow(['Componente', 'Nets', 'NpPinos', 'NetPrincipal', 'Tensao', 'Obs'])
        for pname, allnets, npin, principal in rows:
            w.writerow([pname, allnets, npin, principal, '', ''])
    print(f"{out}: {len(rows)} componentes para preencher (coluna Tensao)")

if __name__ == '__main__':
    main()
