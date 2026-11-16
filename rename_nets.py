# Renomeia malhas (nets) num .pcb XZZPCB reescrevendo o net block (ultimo bloco,
# texto puro apos XOR 0x18). Indices preservados => pinos continuam ligados.
# Uso: python rename_nets.py <arquivo.pcb> <mapa.csv> [--apply]
#   mapa.csv: colunas  De;Para   (De = nome atual da net, ex Net15; Para = BOTAO_LIGA)
# Sem --apply: so mostra o que mudaria. Com --apply: faz backup .pcb.bak e reescreve.
import struct, sys, csv, os, shutil

def load_deob(path):
    raw = open(path, 'rb').read()
    idx = raw.find(b'v6v6555v6v6')
    xk = raw[0x10]
    if idx == -1:  # sem marcador: XOR no arquivo todo
        dd = bytes(b ^ xk for b in raw) if xk else bytearray(raw)
        marker_at = None
    else:          # XOR ate o marcador
        dd = bytes(b ^ xk for b in raw[:idx]) + raw[idx:] if xk else bytes(raw)
        marker_at = idx
    return bytearray(dd), xk, marker_at

def net_block_span(dd):
    u32 = lambda o: struct.unpack_from('<I', dd, o)[0]
    ns = u32(0x28) + 0x20
    size = u32(ns)
    return ns, size  # bloco = dd[ns : ns+4+size], entradas comecam em ns+4

def read_nets(dd):
    ns, size = net_block_span(dd)
    u32 = lambda o: struct.unpack_from('<I', dd, o)[0]
    p, stop = ns + 4, ns + 4 + size
    nets = []  # (index, name)
    while p < stop:
        sz = u32(p); ix = u32(p + 4)
        name = dd[p+8:p+sz].decode('ascii', 'replace')
        nets.append((ix, name)); p += sz
    return ns, size, nets

def rewrite(path, mapping, apply):
    dd, xk, marker_at = load_deob(path)
    if marker_at is not None:
        sys.exit("arquivo tem marcador v6v6555v6v6 (layout diferente) — nao tratado")
    ns, old_size, nets = read_nets(dd)
    # monta novo net block
    changed = 0
    out = bytearray()
    for ix, name in nets:
        newname = mapping.get(name, name)
        if newname != name:
            changed += 1
        b = newname.encode('ascii', 'replace')
        entry = struct.pack('<II', 8 + len(b), ix) + b
        out += entry
    print(f"{os.path.basename(path)}: {len(nets)} nets, {changed} renomeadas")
    for ix, name in nets:
        if name in mapping and mapping[name] != name:
            print(f"   [{ix}] {name} -> {mapping[name]}")
    if not apply:
        print("(dry-run; use --apply para gravar)")
        return
    # reconstroi: dd ate ns (inclusive header), novo size, novo net block, resto NADA (era o fim)
    new_dd = bytearray(dd[:ns])
    new_dd += struct.pack('<I', len(out))  # novo net_block_size
    new_dd += out
    # nao ha marcador; XOR o arquivo todo de volta
    if xk:
        new_dd = bytes(b ^ xk for b in new_dd)
    shutil.copy2(path, path + '.bak')
    open(path, 'wb').write(new_dd)
    print(f"gravado (backup em {os.path.basename(path)}.bak); net block {old_size}B -> {len(out)}B")

def main():
    pcb, mapcsv = sys.argv[1], sys.argv[2]
    apply = '--apply' in sys.argv
    mapping = {}
    with open(mapcsv, encoding='utf-8-sig') as f:
        # aceita ; ou ,
        sample = f.readline(); f.seek(0)
        delim = ';' if sample.count(';') >= sample.count(',') else ','
        for row in csv.DictReader(f, delimiter=delim):
            de = (row.get('De') or '').strip()
            para = (row.get('Para') or '').strip()
            if de and para:
                mapping[de] = para
    rewrite(pcb, mapping, apply)

if __name__ == '__main__':
    main()
