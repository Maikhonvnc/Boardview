# Alinha uma foto (ex. do XZZ) ao contorno de um boardview .bvr (BVRAW_FORMAT)
# do DigitalBoard, gerando <base>_bg.png + <base>.conf pro OpenBoardView.
# O .bvr tem os pads completos (inclui vias redondas) e nets; a foto entra de fundo.
#
# Uso: python align_bvr.py <arquivo.bvr> <foto> [rot] [mirror]
#   rot    = 0|90|180|270  (rotacao aplicada na foto antes de alinhar; default 90)
#   mirror = 0|1           (espelha a foto em X depois de rotacionar; default 0)
#
# Recompoe por secao: divide contorno e foto em 2 ilhas no eixo do maior vao,
# estica cada secao da foto exatamente sobre a bbox da ilha correspondente
# do .bvr => encaixe exato, offset 0, escala uniforme.
import sys, os, re
import numpy as np
from PIL import Image
import align_bg as A  # reusa bbox / connected_components / update_conf


def parse_bvr(path):
    segs, pins = [], []
    def nums(toks):  # tolera tokens nao-numericos coladas (ex "1593.478OUTLINE_SEGMENTED")
        out = []
        for t in toks:
            try: out.append(float(t))
            except ValueError: break
        return out
    for ln in open(path, encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s.startswith('OUTLINE_SEGMENTED'):
            v = nums(s.split()[1:])
            for i in range(0, len(v) - 3, 2):
                segs.append(((v[i], v[i + 1]), (v[i + 2], v[i + 3])))
        elif s.startswith('PIN_ORIGIN'):
            xy = nums(s.split()[1:3])
            if len(xy) == 2: pins.append((xy[0], xy[1]))
    if not segs:
        sys.exit('sem OUTLINE_SEGMENTED no .bvr')
    mnx = min(min(a[0], b[0]) for a, b in segs)
    mny = min(min(a[1], b[1]) for a, b in segs)
    segs = [((a[0]-mnx, a[1]-mny), (b[0]-mnx, b[1]-mny)) for a, b in segs]
    pins = [(x-mnx, y-mny) for x, y in pins]
    return segs, pins, (mnx, mny)


def auto_flip(crop, ib, pins):
    """Decide se a secao (crop orientado p/ ib) deve ser espelhada em X.
    Pinos bem alinhados caem sobre os pads metalicos (pixels CLAROS); escolhe a
    orientacao com maior brilho nos locais dos pinos. Retorna True se espelhar."""
    import numpy as np
    sec = [(x, y) for (x, y) in pins if ib[0] <= x <= ib[2] and ib[1] <= y <= ib[3]]
    if not sec: return False
    g = np.asarray(crop.convert('L'), dtype=float); ch, cw = g.shape
    def bright(flip):
        vals = []
        for x, y in sec:
            u = (x - ib[0]) / (ib[2]-ib[0]); v = (y - ib[1]) / (ib[3]-ib[1])
            if flip: u = 1 - u
            px = min(max(int(u * (cw-1)), 2), cw-3); py = min(max(int((1-v) * (ch-1)), 2), ch-3)
            vals.append(g[py-2:py+3, px-2:px+3].max())  # pad claro sob o pino
        return sum(vals)/len(vals)
    return bright(True) > bright(False)  # espelhado mais claro => precisa espelhar


def valley_split(segs, pins, eixos=(0, 1), frac=0.05):
    """Divide a placa em 2 secoes no maior vale de densidade de pinos.
    Retorna (axis, corte, [bbox_ilha0, bbox_ilha1]) — bboxes vem do contorno.
    `eixos` limita onde procurar, p/ o chamador poder tentar o outro eixo.
    `frac` e a altura (fracao do pico) abaixo da qual um bin conta como vale."""
    P = np.array(pins)
    best = None  # (largura_vale, axis, corte)
    for axis in eixos:
        v = P[:, axis]
        h, e = np.histogram(v, bins=40)
        thr = h.max() * frac
        i = 0
        while i < len(h):
            if h[i] < thr:
                j = i
                while j < len(h) and h[j] < thr: j += 1
                lo, hi = e[i], e[j] if j < len(e) else e[-1]
                mid = (lo + hi) / 2
                # so vales internos (nao nas bordas)
                if e[0] < lo and hi < e[-1]:
                    w = hi - lo
                    if best is None or w > best[0]:
                        best = (w, axis, mid)
                i = j
            else:
                i += 1
    if best is None:  # sem vale interno claro -> secao unica
        return None, None, [A.bbox([p for s in segs for p in s])]
    _, axis, cut = best
    lo = [p for s in segs for p in s if p[axis] < cut]
    hi = [p for s in segs for p in s if p[axis] >= cut]
    return axis, cut, [A.bbox(lo), A.bbox(hi)]


def secoes_validas(segs, pins):
    """valley_split + descarte de ilha espuria, TENTANDO OS DOIS EIXOS.

    Um pedaco solto do contorno (poucos pinos dentro) faz a placa ser dividida onde
    nao ha divisao e a escala sai absurda. Antes, quando isso acontecia, desistia-se
    da divisao — e ai uma placa que se divide bem no OUTRO eixo ficava inteira numa
    secao so. Era o caso do Mini 1: o maior vale estava em X e produzia uma ilha com
    2,3% dos pinos, entao ela virava secao unica e nao havia ajuste que a alinhasse
    (contraste +4,9). Dividindo em Y, que era o vale bom, as duas metades vao a
    +47,5 e +28,2. Agora, se o melhor eixo degenera, tenta-se o outro antes de
    desistir."""
    def tentar(eixos, frac=0.05):
        axis, cut, boxes = valley_split(segs, pins, eixos, frac)
        if axis is None:
            return None
        boxes = sorted(boxes, key=lambda b: b[axis])
        conta = [sum(1 for p in pins if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3])
                 for b in boxes]
        if min(conta) < 0.05 * max(1, len(pins)):
            return None
        return axis, boxes

    # Duas passadas. A primeira exige um vale quase vazio (5% do pico); a segunda
    # afrouxa para 15%. O Mavic 3 Pro precisava disso: a emenda entre as duas
    # metades tem 39 pinos e o corte so valia ate 35,7 — errou por 3 pinos e a
    # placa inteira virou uma secao so, que nao ha ajuste manual que salve.
    # O afrouxamento so entra quando a regra estrita nao achou NADA, entao nenhuma
    # placa que ja se dividia muda de resultado; e a checagem de equilibrio das
    # ilhas (acima) continua sendo quem da a ultima palavra.
    # Padrao: so a passada estrita. O afrouxamento (0.15) e uma CANDIDATA que o
    # foto_viewer.ilhas_e_pinos pede explicitamente e deixa a medida escolher. Se o
    # padrao fosse afrouxado, qc_align/refine_align/medir_afim (que chamam isto sem
    # a variavel) dividiriam o air3 e o rc-plus em duas, discordando das fotos que
    # o foto_viewer gerou inteiras — e o QC dessas placas sairia sem sentido.
    fracs = tuple(float(x) for x in
                  os.environ.get('BOARDVIEW_VALE_FRACS', '0.05').split(','))
    r = None
    for frac in fracs:
        r = tentar((0, 1), frac)
        if r is None:
            primeiro = valley_split(segs, pins, (0, 1), frac)[0]
            if primeiro is not None:             # o melhor eixo degenerou: tenta o outro
                r = tentar((1 - primeiro,), frac)
        if r is not None:
            break
    if r is None:
        return None, [A.bbox([p for s in segs for p in s])]
    return r


def find_blobs(img, axis):
    """2 blobs da foto no eixo dado (0=colunas/lado-a-lado, 1=linhas/empilhado)."""
    a = np.asarray(img.convert('RGB')).astype(int)
    h, w, _ = a.shape
    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    mask = np.abs(a - bg).sum(axis=2) > 60
    n = w if axis == 0 else h
    prof = mask.sum(axis=0) if axis == 0 else mask.sum(axis=1)
    span = h if axis == 0 else w
    active = prof > 0.02 * span
    ranges, start = [], None
    for i in range(n):
        if active[i] and start is None: start = i
        if not active[i] and start is not None:
            ranges.append((start, i - 1)); start = None
    if start is not None: ranges.append((start, n - 1))
    merged = []
    for r in ranges:
        if merged and r[0] - merged[-1][1] < 0.02 * n:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(list(r))
    merged = [r for r in merged if r[1] - r[0] > 0.1 * n]
    blobs = []
    for lo, hi in merged:
        if axis == 0:
            sub = mask[:, lo:hi + 1]; rows = np.where(sub.sum(axis=1) > 0.02 * (hi - lo))[0]
            blobs.append((lo, int(rows.min()), hi, int(rows.max())))
        else:
            sub = mask[lo:hi + 1, :]; cols = np.where(sub.sum(axis=0) > 0.02 * (hi - lo))[0]
            blobs.append((int(cols.min()), lo, int(cols.max()), hi))
    return blobs


def compor(bvr, img_path, rot=90, mirror=False, flipsec=None, vflipsec=None, log=print):
    """Monta o canvas da foto no frame do .bvr (bbox do contorno, sem Y-flip).
    flipsec=None => decide o espelhamento de cada secao sozinho (auto_flip).
    Retorna (canvas RGBA, W_u, H_u, flips, secoes) — secoes = [(bbox_ilha, pinos)].
    Levanta ValueError quando blobs e ilhas nao batem (foto/rot errados)."""
    auto = flipsec is None
    flipsec = set() if auto else set(flipsec)
    vflipsec = set(vflipsec or ())

    segs, pins, _mins = parse_bvr(bvr)
    total = A.bbox([p for s in segs for p in s])
    W_u, H_u = total[2] - total[0], total[3] - total[1]
    axis, island_boxes = secoes_validas(segs, pins)
    log(f'.bvr {W_u:.0f}x{H_u:.0f}u  eixo divisao={"X" if axis==0 else "Y" if axis==1 else "unico"}  '
        f'ilhas: {[tuple(round(v) for v in b) for b in island_boxes]}')

    img = Image.open(img_path)
    if rot: img = img.rotate(-rot, expand=True)      # -rot => horario p/ rot>0
    if mirror: img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if axis is None:  # secao unica: 1 blob = bbox de conteudo da foto
        blobs = find_blobs(img, 0) or [(0, 0, img.width - 1, img.height - 1)]
        blobs = [(min(b[0] for b in blobs), min(b[1] for b in blobs),
                  max(b[2] for b in blobs), max(b[3] for b in blobs))]
    else:
        blobs = find_blobs(img, axis)
        blobs.sort(key=lambda b: b[axis])
    # foto XZZ tem 2 secoes (metades iguais) mas divisoria preta impede detectar 2;
    # se veio 1 blob e esperamos 2, corta o blob no meio do eixo.
    if len(blobs) == 1 and len(island_boxes) == 2:
        x0, y0, x1, y1 = blobs[0]
        if axis == 0:
            mid = (x0 + x1) // 2
            blobs = [(x0, y0, mid, y1), (mid + 1, y0, x1, y1)]
        else:
            mid = (y0 + y1) // 2
            blobs = [(x0, y0, x1, mid), (x0, mid + 1, x1, y1)]
        log(f'  -> dividido no meio ({"X" if axis==0 else "Y"}={mid}): {blobs}')
    if len(blobs) != len(island_boxes):
        raise ValueError(f'{len(blobs)} blobs != {len(island_boxes)} ilhas; tente outro rot/mirror')

    ppu_list = []
    pairs = list(zip(island_boxes, blobs))
    for ib, bl in pairs:
        ppu_list += [(bl[2]-bl[0]) / (ib[2]-ib[0]), (bl[3]-bl[1]) / (ib[3]-ib[1])]
    ppu = sum(ppu_list) / len(ppu_list)
    log(f'ppu por lado {[round(p,3) for p in ppu_list]} -> {ppu:.4f} '
        f'(disp {(max(ppu_list)-min(ppu_list))/ppu*100:.1f}%)')

    cw, ch = int(round(W_u * ppu)), int(round(H_u * ppu))
    src = img.convert('RGBA')
    flips, pecas = [], []
    for i, (ib, bl) in enumerate(pairs):
        crop = src.crop((bl[0], bl[1], bl[2] + 1, bl[3] + 1))
        do_flip = auto_flip(crop, ib, pins) if auto else (i in flipsec)
        if do_flip:                            # face de tras: espelha horizontal
            crop = crop.transpose(Image.FLIP_LEFT_RIGHT)
        if i in vflipsec:                      # secao de cabeca pra baixo: espelha vertical
            crop = crop.transpose(Image.FLIP_TOP_BOTTOM)
        flips.append(do_flip)
        tw = max(1, int(round((ib[2]-ib[0]) * ppu)))
        th = max(1, int(round((ib[3]-ib[1]) * ppu)))
        # sem Y-flip no destino: a ordem das secoes casa com o viewer DigitalBoard
        pecas.append(((int(round(ib[0]*ppu)), int(round(ib[1]*ppu))),
                      crop.resize((tw, th), Image.LANCZOS)))
    canvas = montar((cw, ch), pecas)
    log(f'composto {canvas.width}x{canvas.height}  flip_secao={flips} ({"auto" if auto else "manual"})')
    secoes = [(ib, [p for p in pins if ib[0] <= p[0] <= ib[2] and ib[1] <= p[1] <= ib[3]])
              for ib, _ in pairs]
    return canvas, W_u, H_u, flips, secoes, pecas


def montar(tamanho, pecas, espelhar=()):
    """Remonta o canvas a partir das pecas devolvidas por compor(), espelhando em X
    as secoes indicadas. Espelhar a peca ja redimensionada da no mesmo pixel que
    espelhar antes de redimensionar, entao da p/ testar as combinacoes de face sem
    recompor tudo (que e o passo caro)."""
    canvas = Image.new('RGBA', tamanho, (0, 0, 0, 0))
    for i, (xy, crop) in enumerate(pecas):
        if i in espelhar:
            crop = crop.transpose(Image.FLIP_LEFT_RIGHT)
        canvas.paste(crop, xy)
    return canvas


def main():
    bvr, img_path = sys.argv[1], sys.argv[2]
    rot = int(sys.argv[3]) if len(sys.argv) > 3 else 90
    mirror = len(sys.argv) > 4 and sys.argv[4] in ('1', 'true', 'True')
    # indices de secao p/ espelhar em X (face de tras). Se omitido -> auto por secao.
    auto = len(sys.argv) <= 5
    flipsec = None if auto else (set(int(x) for x in sys.argv[5].split(','))
                                 if sys.argv[5] not in ('', '-1') else set())
    # flip VERTICAL por secao (indice, ex "1"); argv[6]. Face que fica de cabeca pra baixo.
    vflipsec = set(int(x) for x in sys.argv[6].split(',')) if len(sys.argv) > 6 and sys.argv[6] not in ('', '-1') else set()
    out_name = os.path.basename(re.sub(r'\.bvr$', '_bg.png', bvr, flags=re.I))
    out_path = os.path.join(os.path.dirname(bvr), out_name)

    try:
        canvas, W_u, H_u, flips, _sec, _pc = compor(bvr, img_path, rot, mirror, flipsec, vflipsec)
    except ValueError as e:
        sys.exit(f'AVISO: {e}')
    canvas.save(out_path)
    sx, sy = W_u / canvas.width, H_u / canvas.height
    print(f'flip_secao={flips} -> {out_path}')

    conf = re.sub(r'\.bvr$', '.conf', bvr, flags=re.I)
    kv = {}
    for P in ('Top', 'Bottom'):
        kv.update({f'{P}ImageFile': out_name, f'{P}ImageOffsetX': 0, f'{P}ImageOffsetY': 0,
                   f'{P}ImageScalingX': f'{sx:.6f}', f'{P}ImageScalingY': f'{sy:.6f}',
                   f'{P}ImageMirrorX': 'false', f'{P}ImageMirrorY': 'false',
                   f'{P}ImageTransparency': '0.000000'})
    A.update_conf(conf, kv)
    print(f'conf {conf}  scaling {sx:.6f}/{sy:.6f}')


if __name__ == '__main__':
    main()
