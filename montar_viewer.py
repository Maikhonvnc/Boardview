# Monta o viewer local com TODAS as placas do DigitalBoard, usando o pareamento
# OFICIAL (.bvr + borda) lido das paginas *_db.html deles. A borda oficial ja vem
# alinhada ao .bvr, entao nao precisa de ajuste.
# Uso: python montar_viewer.py
import os, re, glob, json, shutil
from paths import DIGITALBOARD, DV_BUILD

DB  = DIGITALBOARD
DV  = DV_BUILD
os.makedirs(f'{DV}/DRONE', exist_ok=True)
os.makedirs(f'{DV}/SM', exist_ok=True)

def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', os.path.splitext(s)[0].lower()).strip('-')

# nome bonito por pagina
NICE = {
    'AIR2 PCB_db': 'DJI Air 2', 'AIR2_ELETRICAL_db': 'DJI Air 2 — Regulacao',
    'AIR3S_db': 'DJI Air 3S', 'MAVIC3 REG_db': 'DJI Mavic 3 — Regulacao',
    'air2_cpu_mem_db': 'DJI Air 2 — CPU/Memoria', 'air2s_db': 'DJI Air 2S',
    'air3_db': 'DJI Air 3', 'mavic pro_db': 'DJI Mavic Pro', 'mavic2_db': 'DJI Mavic 2',
    'mavic3_db': 'DJI Mavic 3', 'mavic3pro_db': 'DJI Mavic 3 Pro', 'mini1_db': 'DJI Mini 1',
    'mini3_db': 'DJI Mini 3', 'mini3pro_db': 'DJI Mini 3 Pro', 'mini4pro_db': 'DJI Mini 4 Pro',
    'mini4pro_sub1_db': 'DJI Mini 4 Pro — SUB A', 'mini4pro_sub2_db': 'DJI Mini 4 Pro — SUB B',
    'mine2_db': 'DJI Mini 2',
}
IGNORAR = {'DRONE', 'drone (1)', 'drone (2)', 'drone_lite'}   # paginas genericas/vazias

pairs = []
for page in sorted(glob.glob(f'{DB}/paginas-html/*.html')):
    t = open(page, encoding='utf-8', errors='replace').read()
    mb = re.search(r'loadImage\(\s*["\']([^"\']+)["\']', t)
    bl = re.findall(r"['\"]([^'\"]*\.bvr)['\"]", t)
    if not bl: continue                       # sem boardview nao da p/ montar
    borda = os.path.basename(mb.group(1)) if mb else ''
    bvr = os.path.basename(bl[-1]).replace('%20', ' ')
    name = os.path.splitext(os.path.basename(page))[0]
    if name in IGNORAR: continue
    pairs.append((name, bvr, borda))

manifest = []
for name, bvr, borda in pairs:
    src_bvr = f'{DB}/boardview-bvr/{bvr}'
    src_bor = f'{DB}/bordas/{borda}' if borda else ''
    if not os.path.exists(src_bvr):
        # apelido: o repo tem o mesmo arquivo com nomes diferentes (dedup por conteudo).
        key = re.sub(r'[^a-z0-9]', '', os.path.splitext(bvr)[0].lower())
        cand = [p for p in glob.glob(f'{DB}/boardview-bvr/*.bvr')
                if re.sub(r'[^a-z0-9]', '', os.path.splitext(os.path.basename(p))[0].lower()).startswith(key)]
        if not cand:
            print(f'  ! sem bvr: {bvr}  ({name})'); continue
        src_bvr = cand[0]
        print(f'    (apelido) {bvr} -> {os.path.basename(src_bvr)}')
    sid = slug(name.replace('_db', '').replace(' ', '-'))
    shutil.copy(src_bvr, f'{DV}/DRONE/{sid}.bvr')
    tem_borda = bool(src_bor) and os.path.exists(src_bor)
    if tem_borda:
        shutil.copy(src_bor, f'{DV}/SM/{sid}_borda.jpg')
    manifest.append({'id': sid, 'name': NICE.get(name, name), 'borda': tem_borda,
                     'foto': os.path.exists(f'{DV}/FOTO/{sid}_foto.jpg')})
    print(f'  {sid:22} <- {bvr[:34]:34} + {borda[:28] if tem_borda else "(sem borda)"}')

# funde as fotos ja alinhadas (slugs antigos) nas placas oficiais: se o .bvr for o
# MESMO conteudo, e a mesma placa -> a foto vira so outra camada de fundo dela.
def sig(p):
    """Assinatura pelos DADOS (o repo tem o mesmo boardview salvo com bytes diferentes)."""
    n = 0; xs = []; ys = []
    for ln in open(p, encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s.startswith('PIN_ORIGIN'):
            try:
                x, y = float(s.split()[1]), float(s.split()[2])
                xs.append(x); ys.append(y); n += 1
            except (ValueError, IndexError): pass
    if not n: return None
    return (n, round(max(xs) - min(xs)), round(max(ys) - min(ys)))
oficial = {}
for m in manifest:
    s = sig(f'{DV}/DRONE/{m["id"]}.bvr')
    if s: oficial[s] = m
for f in sorted(glob.glob(f'{DV}/FOTO/*_foto.jpg')):
    sid = os.path.basename(f).replace('_foto.jpg', '')
    if any(m['id'] == sid for m in manifest): continue
    bvr = f'{DV}/DRONE/{sid}.bvr'
    if not os.path.exists(bvr): continue
    h = sig(bvr)
    if h in oficial:                     # mesma placa: move a foto p/ o slug oficial
        alvo = oficial[h]
        shutil.move(f, f'{DV}/FOTO/{alvo["id"]}_foto.jpg')
        alvo['foto'] = True
        os.remove(bvr)
        print(f'    (fundido) foto de {sid} -> {alvo["id"]}')
    else:
        manifest.append({'id': sid, 'name': sid + '  (foto XZZ)', 'borda': False, 'foto': True})

manifest.sort(key=lambda m: m['name'])
json.dump(manifest, open(f'{DV}/boards.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(f'\n{len(manifest)} placas no viewer  '
      f'({sum(m["borda"] for m in manifest)} com borda oficial, {sum(m["foto"] for m in manifest)} com foto)')

if __name__ == '__main__':
    pass
