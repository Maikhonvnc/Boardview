import struct, sys
data = open(sys.argv[1], 'rb').read()
idx = data.find(b'v6v6555v6v6')
print('tamanho:', len(data), '| marcador v6v6555v6v6 em:', hex(idx) if idx>=0 else 'ausente')
xk = data[0x10]
print('xor_key[0x10]:', hex(xk))
end = idx if idx != -1 else len(data)
dd = bytes(b ^ xk for b in data[:end]) + data[end:] if xk else data
u32 = lambda o: struct.unpack_from('<I', dd, o)[0]
main_off = u32(0x20); net_off = u32(0x28)
print('main_data_offset(0x20):', main_off, '-> start', main_off+0x20)
print('net_data_offset (0x28):', net_off,  '-> start', net_off+0x20)
ms = main_off+0x20; ns = net_off+0x20
print('main_block_size @start:', u32(ms))
print('net_block_size  @start:', u32(ns))
print('main block: [%d .. %d]' % (ms, ms+4+u32(ms)))
print('net  block: [%d .. %d]' % (ns, ns+4+u32(ns)))
print('ordem:', 'NET antes de MAIN' if ns < ms else 'MAIN antes de NET')
print('net block termina no fim do arquivo util?', ns+4+u32(ns), 'vs end', end, '(idx marcador)', idx)
# amostra de nets
p = ns+4; stop = ns+4+u32(ns); k=0
while p < stop and k < 5:
    sz = u32(p); ix = u32(p+4); nm = dd[p+8:p+sz].decode('ascii','replace'); p += sz; k+=1
    print('  net idx=%d size=%d name=%r' % (ix, sz, nm))
