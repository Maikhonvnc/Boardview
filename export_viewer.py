# Exporta uma placa XZZ (.pcb) para JSON do viewer local: outline, pinos (com net),
# vias (0x02, com net) e info da foto de fundo (do .conf). Coords deslocadas p/ min
# do outline (mesmo frame que a foto alinhada). Uso: python export_viewer.py <pcb> <saida.json>
import struct, sys, os, re, json
from Crypto.Cipher import DES  # pycryptodome

SCALE = 10000
DES_KEY = bytes.fromhex('DCFC12AC00000000')  # XZZPCBKey

def load(pcb):
    data = open(pcb, 'rb').read()
    idx = data.find(b'v6v6555v6v6'); end = idx if idx != -1 else len(data)
    xk = data[0x10]
    dec = bytes(b ^ xk for b in data[:end]) + data[end:] if xk else data
    return dec

def u32(d, o): return struct.unpack_from('<I', d, o)[0]

def des_dec(buf):
    c = DES.new(DES_KEY, DES.MODE_ECB)
    n = (len(buf) // 8) * 8
    return c.decrypt(bytes(buf[:n]))

def parse_nets(dec):
    # bloco de nets = ultimo bloco (offset em 0x28)
    net_off = u32(dec, 0x28) + 0x20
    size = u32(dec, net_off); p = net_off + 4; stop = net_off + 4 + size
    nets = {}
    while p < stop:
        ns = u32(dec, p); p += 4
        ni = u32(dec, p); p += 4
        name = dec[p:p + ns - 8].decode('ascii', 'replace'); p += ns - 8
        nets[ni] = name
    return nets

def main():
    pcb, out = sys.argv[1], sys.argv[2]
    dec = load(pcb)
    nets = parse_nets(dec)
    ms = u32(dec, 0x20) + 0x20
    total = u32(dec, ms); p = ms + 4; stop = ms + 4 + total
    segs, pins, vias = [], [], []
    while p < stop:
        bt = dec[p]; p += 1; bs = u32(dec, p); p += 4; off = p; p += bs
        if bt == 0x05:  # linha de contorno
            layer, x1, y1, x2, y2 = struct.unpack_from('<5I', dec, off)
            if layer == 28: segs.append((x1 // SCALE, y1 // SCALE, x2 // SCALE, y2 // SCALE))
        elif bt == 0x02:  # via
            v = struct.unpack_from('<8I', dec, off)
            vias.append((v[0] // SCALE, v[1] // SCALE, nets.get(v[6], '')))
        elif bt == 0x07:  # parte (DES) -> pinos 0x09
            b = des_dec(dec[off:off + bs])
            parse_part(b, pins, nets)
    # min do outline p/ deslocar
    xs = [s[0] for s in segs] + [s[2] for s in segs]; ys = [s[1] for s in segs] + [s[3] for s in segs]
    mnx, mny = min(xs), min(ys); mxx, mxy = max(xs), max(ys)
    W, H = mxx - mnx, mxy - mny
    sh = lambda x, y: (x - mnx, y - mny)
    outline = [sh(s[0], s[1]) + sh(s[2], s[3]) for s in segs]
    P = [{'x': x - mnx, 'y': y - mny, 'net': n, 'name': nm} for (x, y, n, nm) in pins]
    V = [{'x': x - mnx, 'y': y - mny, 'net': n} for (x, y, n) in vias]
    # foto de fundo do .conf
    conf = re.sub(r'\.pcb$', '.conf', pcb, flags=re.I)
    img = None
    if os.path.exists(conf):
        t = open(conf, encoding='utf-8', errors='replace').read()
        f = re.search(r'(?m)^TopImageFile\s*=\s*(.+)$', t)
        sx = re.search(r'(?m)^TopImageScalingX\s*=\s*([\d.]+)$', t)
        if f and sx:
            img = {'file': f.group(1).strip(), 'scale': float(sx.group(1))}
    json.dump({'W': W, 'H': H, 'outline': outline, 'pins': P, 'vias': V, 'img': img,
               'name': os.path.basename(pcb)}, open(out, 'w'), separators=(',', ':'))
    print(f'{os.path.basename(pcb)}: {len(P)} pinos, {len(V)} vias, {len(segs)} segs, {len(nets)} nets, WxH {W}x{H} -> {out}')

def parse_part(b, pins, nets):
    # replica parse_part_block do OBV: acha sub-blocos 0x09 (pinos)
    pt = 0
    part_size = u32(b, pt); pt += 4; pt += 18
    gname = u32(b, pt); pt += 4; pt += gname
    if pt >= len(b) or b[pt] != 0x06: return
    pt += 31
    pn = u32(b, pt); pt += 4; pt += pn
    while pt < part_size + 4 and pt < len(b):
        st = b[pt]; pt += 1
        if st == 0x09:
            pins.append(parse_pin(b, pt_ref := [pt], nets)); pt = pt_ref[0]
        elif st in (0x01, 0x05, 0x06):
            pt += u32(b, pt) + 4
        else:
            if st == 0x00: continue
            break

def parse_pin(b, ref, nets):
    pt = ref[0]
    bs = u32(b, pt); end = pt + bs + 4; pt += 4; pt += 4
    x = u32(b, pt); pt += 4; y = u32(b, pt); pt += 4; pt += 8
    ns = u32(b, pt); pt += 4
    name = b[pt:pt + ns].decode('ascii', 'replace'); pt += ns; pt += 32
    ni = u32(b, pt)
    ref[0] = end
    net = nets.get(ni, '')
    if net == 'NC': net = ''
    return (x // SCALE, y // SCALE, net, name)

if __name__ == '__main__':
    main()
