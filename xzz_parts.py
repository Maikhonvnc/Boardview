# Decripta e parseia blocos de componente (0x07, DES-ECB) de arquivos XZZPCB.
# Uso: python xzz_parts.py <arquivo.pcb> [dump]   (dump = imprime amostra)
import struct, sys
from Crypto.Cipher import DES

KEY = bytes.fromhex('DCFC12AC00000000')
_des = DES.new(KEY, DES.MODE_ECB)

def decrypt(b):
    n = len(b) // 8 * 8
    return _des.decrypt(b[:n]) + b[n:]

def load_parts(path):
    data = open(path, 'rb').read()
    idx = data.find(b'v6v6555v6v6')
    end = idx if idx != -1 else len(data)
    xk = data[0x10]
    if xk: data = bytes(c ^ xk for c in data[:end]) + data[end:]
    u32 = lambda o: struct.unpack_from('<I', data, o)[0]

    ns = u32(0x28) + 0x20
    nsz = u32(ns)
    nets, p = {}, ns + 4
    while p < ns + 4 + nsz:
        size = u32(p); nidx = u32(p + 4)
        nets[nidx] = data[p+8:p+size].decode('ascii', 'replace')
        p += size

    ms = u32(0x20) + 0x20
    pt, stop = ms + 4, ms + 4 + u32(ms)
    parts = []
    while pt < stop:
        bt = data[pt]; sz = struct.unpack_from('<I', data, pt+1)[0]
        blk = data[pt+5:pt+5+sz]; pt += 5 + sz
        if bt != 7: continue
        buf = decrypt(bytes(blk))
        b32 = lambda o: struct.unpack_from('<I', buf, o)[0]
        try:
            cp = 0
            psize = b32(cp); cp += 4 + 18
            gsz = b32(cp); cp += 4 + gsz
            if cp >= len(buf) or buf[cp] != 6: continue
            cp += 31
            pnsz = b32(cp); cp += 4
            pname = buf[cp:cp+pnsz].decode('ascii', 'replace'); cp += pnsz
            pins = []
            while cp < psize + 4 and cp < len(buf):
                st = buf[cp]; cp += 1
                if st in (1, 5, 6):
                    cp += b32(cp) + 4
                elif st == 9:
                    pbs = b32(cp); pend = cp + pbs + 4
                    x = b32(cp+8) // 10000; y = b32(cp+12) // 10000
                    pn = b32(cp+24)
                    pinname = buf[cp+28:cp+28+pn].decode('ascii', 'replace')
                    net = b32(cp+28+pn+32)
                    pins.append((pinname, nets.get(net, f'net#{net}'), x, y))
                    cp = pend
                elif st == 0:
                    pass
                else:
                    break
            parts.append((pname, pins))
        except (struct.error, IndexError):
            continue
    return nets, parts

if __name__ == '__main__':
    nets, parts = load_parts(sys.argv[1])
    print(f"{len(nets)} nets, {len(parts)} parts")
    if 'dump' in sys.argv:
        for pname, pins in parts[:10]:
            extra = ' ...' if len(pins) > 4 else ''
            print(f"PART {pname!r}: {pins[:4]}{extra} ({len(pins)} pinos)")
