# Gera miniaturas leves p/ os cards do HUB (a tela inicial carregava 302 MB de fotos).
# Fonte: 1a foto da placa; se nao houver, a borda do DigitalBoard. Saida: thumbs/<slug>.jpg
import os, re, glob, json, sys
from PIL import Image
from paths import BV, DRONES
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
Image.MAX_IMAGE_PIXELS = None                       # fotos de placa sao enormes

TH     = os.path.join(BV, 'thumbs')
LARG   = 560
os.makedirs(TH, exist_ok=True)

def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def conf_foto(pcb):
    c = re.sub(r'\.pcb$', '.conf', pcb, flags=re.I)
    if not os.path.exists(c): return None
    m = re.search(r'(?m)^TopImageFile\s*=\s*(.+)$', open(c, encoding='utf-8', errors='replace').read())
    if not m: return None
    p = os.path.join(os.path.dirname(pcb), m.group(1).strip())
    return p if os.path.exists(p) else None

# fallback: bordas do DigitalBoard por modelo
BORDAS = {'air3s': 'Picsart_25-09-18_11-28-49-180.jpg', 'rc pro': None}
bordas_dir = os.path.join(BV, 'DigitalBoard', 'bordas')

def render_bvr(folder, out):
    """Desenha pads+contorno do boardview do modelo (fallback de miniatura)."""
    import glob as g
    from PIL import ImageDraw
    key = re.sub(r'[^a-z0-9]', '', folder.lower().replace('dji', '').replace('mavic', ''))[:7]
    cand = [q for q in g.glob(os.path.join(BV, 'DigitalBoard', 'boardview-bvr', '*.bvr'))
            if key and key in re.sub(r'[^a-z0-9]', '', os.path.basename(q).lower())]
    if not cand: return False
    segs, pins = [], []
    for ln in open(sorted(cand, key=len)[0], encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s.startswith('OUTLINE_SEGMENTED'):
            v = []
            for tk in s.split()[1:]:
                try: v.append(float(tk))
                except ValueError: break
            for i in range(0, len(v) - 3, 2): segs.append((v[i], v[i+1], v[i+2], v[i+3]))
        elif s.startswith('PIN_ORIGIN'):
            try: pins.append((float(s.split()[1]), float(s.split()[2])))
            except (ValueError, IndexError): pass
    if not segs: return False
    xs = [c for s in segs for c in (s[0], s[2])]; ys = [c for s in segs for c in (s[1], s[3])]
    mnx, mny, mxx, mxy = min(xs), min(ys), max(xs), max(ys)
    W, H = mxx - mnx, mxy - mny
    if W <= 0 or H <= 0: return False
    sc = LARG / W
    im = Image.new('RGB', (LARG, max(1, int(H * sc))), (10, 14, 22))
    d = ImageDraw.Draw(im)
    T = lambda x, y: ((x - mnx) * sc, im.height - 1 - (y - mny) * sc)
    # so os pads: o contorno vem como segmentos soltos e ligar tudo vira risco diagonal
    for x, y in pins:
        px, py = T(x, y); d.rectangle([px-1, py-1, px+1, py+1], fill=(210, 170, 60))
    im.save(out, quality=82, optimize=True)
    return True

feitas = {}
for folder in sorted(os.listdir(DRONES)):
    d = os.path.join(DRONES, folder)
    if not os.path.isdir(d) or '__MACOSX' in folder: continue
    src = None
    for pcb in sorted(glob.glob(os.path.join(d, '*.pcb'))):
        if os.path.basename(pcb).startswith('._'): continue
        src = conf_foto(pcb)
        if src: break
    if not src:                                     # tenta borda do DigitalBoard
        k = folder.lower().replace('dji ', '').replace('mavic ', '').strip()
        cand = [p for p in glob.glob(os.path.join(bordas_dir, '*.jpg'))
                if re.sub(r'[^a-z0-9]', '', os.path.basename(p).lower()).startswith(re.sub(r'[^a-z0-9]', '', k)[:6])]
        src = cand[0] if cand else None
    if not src:                                     # ultimo recurso: desenha do .bvr
        out = os.path.join(TH, slug(folder) + '.jpg')
        if render_bvr(folder, out):
            feitas[folder] = os.path.basename(out)
            print(f'   {folder:24} desenhado do .bvr -> {os.path.getsize(out)/1024:>5.0f} KB')
        else:
            print(f'   {folder:24} sem imagem')
        continue
    try:
        im = Image.open(src).convert('RGB')
        im.thumbnail((LARG, LARG * 3), Image.LANCZOS)
        out = os.path.join(TH, slug(folder) + '.jpg')
        im.save(out, quality=82, optimize=True)
        feitas[folder] = os.path.basename(out)
        print(f'   {folder:24} {os.path.getsize(src)/1e6:>6.1f} MB -> {os.path.getsize(out)/1024:>5.0f} KB')
    except Exception as e:
        print(f'   {folder:24} ERRO {e}')

json.dump(feitas, open(os.path.join(TH, '_map.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
tot = sum(os.path.getsize(os.path.join(TH, f)) for f in os.listdir(TH) if f.endswith('.jpg'))
print(f'\n{len(feitas)} miniaturas, {tot/1024:.0f} KB no total (antes: 302 MB)')
