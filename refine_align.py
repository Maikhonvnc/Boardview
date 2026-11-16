# Mede e corrige o erro residual do alinhamento foto x pads do digital_viewer.
#
# Ideia: pad metalico aparece na foto como mancha CLARA em relacao ao entorno
# imediato. Renderiza-se uma mascara dos PIN_ORIGIN do .bvr no MESMO mapeamento
# que o viewer usa (imagem esticada na bbox do contorno, Y invertido) e cruza-se
# com a foto passa-alta. O pico da correlacao diz o quanto a foto esta fora.
#
# A busca e por secao (cada metade da placa entra na foto com escala propria) e
# cobre escala X/Y + deslocamento: grosseira numa reducao, fina numa intermediaria
# e, por ultimo, so deslocamento na resolucao cheia.
#
# Uso: python refine_align.py [id ...] [--apply]
#   sem --apply: so mede as fotos ja existentes em build/FOTO
#   com --apply: reescreve build/FOTO/<id>_foto.jpg corrigido
import os, sys, glob
import numpy as np
from PIL import Image
from paths import BV
import align_bvr as V, align_bg as A

DV = os.path.join(BV, 'digital_viewer', 'build')


def highpass(gray, k=15):
    """Realca pad claro sobre substrato escuro: tira a media local (box blur por
    imagem integral) e normaliza. Robusto a iluminacao desigual da foto."""
    g = np.asarray(gray, dtype=np.float64)
    s = 2 * k + 1
    pad = np.pad(g, k, mode='edge')
    ii = np.pad(pad.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    win = (ii[s:, s:] - ii[:-s, s:] - ii[s:, :-s] + ii[:-s, :-s]) / (s * s)
    d = g - win[:g.shape[0], :g.shape[1]]
    sd = d.std()
    return d / sd if sd > 1e-6 else d


def _mask(px, py, shape, r):
    m = np.zeros(shape, np.float64)
    ih, iw = shape
    px = np.rint(px).astype(int); py = np.rint(py).astype(int)
    ok = (px >= r) & (px < iw - r) & (py >= r) & (py < ih - r)
    px, py = px[ok], py[ok]
    if len(px) == 0: return None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                m[py + dy, px + dx] = 1.0
    return m


def _corr(FT, shape, m, lim):
    """Melhor deslocamento (|d| <= lim) da mascara contra a foto ja em Fourier.
    Devolve (dx, dy, score normalizado)."""
    mn = m - m.mean()
    n = np.sqrt((mn * mn).sum()) or 1.0
    c = np.fft.irfft2(FT * np.conj(np.fft.rfft2(mn)), shape) / n
    h, w = shape
    lim = max(0, min(int(lim), (h - 1) // 2, (w - 1) // 2))
    ys = np.r_[0:lim + 1, h - lim:h]
    xs = np.r_[0:lim + 1, w - lim:w]
    box = c[np.ix_(ys, xs)]
    i = np.unravel_index(np.argmax(box), box.shape)
    dy = ys[i[0]]; dx = xs[i[1]]
    return (dx - w if dx > lim else dx), (dy - h if dy > lim else dy), float(box[i])


def _pix(pins, W, H, iw, ih):
    """Pinos (unidades do .bvr) -> pixels da imagem, na convencao do viewer."""
    x = np.array([p[0] for p in pins]) / W * (iw - 1)
    y = (1 - np.array([p[1] for p in pins]) / H) * (ih - 1)
    return x, y


def _reduz(sub, alvo):
    f = min(1.0, alvo / max(sub.size))
    g = sub.convert('L')
    if f < 1.0:
        g = g.resize((max(8, int(g.width * f)), max(8, int(g.height * f))), Image.LANCZOS)
    return np.asarray(g, dtype=np.float64), (g.width / sub.width)


def _score(sub, x, y, alvo=700, lim_frac=0.05, r=1):
    """Quanto os pads do recorte casam com os pinos, permitindo um deslocamento
    pequeno. Serve para comparar candidatos (rotacao, espelhamento) entre si."""
    g, k = _reduz(sub, alvo)
    m = _mask(k * np.asarray(x), k * np.asarray(y), g.shape, r)
    if m is None: return -1e9
    F = highpass(g)
    return _corr(np.fft.rfft2(F), g.shape, m, max(3, int(lim_frac * max(g.shape))))[2]


# variantes de orientacao de uma secao: a foto do XZZ traz a face de tras
# espelhada, e as vezes de cabeca pra baixo.
VARIANTES = ('', 'H', 'V', 'HV')


def _variante(sub, x, y, v):
    """Aplica a variante ao recorte E as coordenadas dos pinos dentro dele."""
    w, h = sub.size
    if 'H' in v:
        sub = sub.transpose(Image.FLIP_LEFT_RIGHT); x = (w - 1) - np.asarray(x)
    if 'V' in v:
        sub = sub.transpose(Image.FLIP_TOP_BOTTOM); y = (h - 1) - np.asarray(y)
    return sub, np.asarray(x), np.asarray(y)


def contraste(sub, x, y, alvo=None):
    """Nota do encaixe: quanto o pixel EM CIMA do pino e mais claro que a vizinhanca.
    A correlacao acha bem o deslocamento, mas nao distingue espelhamento (a nuvem de
    pinos e densa demais, casa parecido de qualquer lado); este contraste distingue,
    porque so a orientacao certa poe os pinos sobre metal."""
    g, k = _reduz(sub, alvo) if alvo else (np.asarray(sub.convert('L'), dtype=np.float64), 1.0)
    ih, iw = g.shape
    px = np.rint(k * np.asarray(x)).astype(int); py = np.rint(k * np.asarray(y)).astype(int)
    ok = (px >= 4) & (px < iw - 5) & (py >= 4) & (py < ih - 5)
    px, py = px[ok], py[ok]
    if len(px) < 30: return -1e9
    dentro = np.array([g[b-1:b+2, a-1:a+2].mean() for a, b in zip(px, py)])
    fora = np.array([g[b-4:b+5, a-4:a+5].mean() for a, b in zip(px, py)])
    return float((dentro - fora).mean())


def melhor_variante(sub, x, y):
    """Escolhe o espelhamento da secao pelo contraste dos pads.

    CUIDADO: medido nas placas deste acervo, NENHUM criterio automatico separa bem
    o espelhamento — correlacao, prominencia do pico e contraste dao praticamente a
    mesma nota para a secao certa e para a espelhada, porque a nuvem de pinos e densa
    e a placa tem cobre por toda parte. Por isso `refinar` NAO usa isto por padrao:
    o espelhamento vem da tabela conferida a olho no foto_viewer.py. Fica aqui para
    diagnostico e para quem quiser tentar um criterio melhor."""
    notas = {}
    for v in VARIANTES:
        s, xx, yy = _variante(sub, x, y, v)
        sx, sy, dx, dy, _g = medir_secao_px(s, list(zip(xx, yy)), rapido=True)
        cx, cy = xx.mean(), yy.mean()
        notas[v] = contraste(s, cx + sx * (xx - cx) + dx, cy + sy * (yy - cy) + dy)
    return max(notas, key=notas.get), notas


def pontuar(img, W, H, secoes):
    """Nota da foto inteira, para escolher a ROTACAO (a unica coisa que esta nota
    separa bem: com a rotacao errada os blobs nem casam com as ilhas)."""
    iw, ih = img.size
    total = 0.0
    for ib, pins in secoes:
        if len(pins) < 30: continue
        x0, y0, x1, y1 = _rect(ib, W, H, iw, ih)
        if x1 - x0 < 64 or y1 - y0 < 64: continue
        px, py = _pix(pins, W, H, iw, ih)
        total += _score(img.crop((x0, y0, x1, y1)), px - x0, py - y0)
    return total


def _rect(ib, W, H, iw, ih):
    """bbox da ilha (unidades) -> retangulo na imagem (viewer: Y invertido)."""
    x0 = int(max(0, np.floor(ib[0] / W * (iw - 1))))
    x1 = int(min(iw, np.ceil(ib[2] / W * (iw - 1)) + 1))
    y0 = int(max(0, np.floor((1 - ib[3] / H) * (ih - 1))))
    y1 = int(min(ih, np.ceil((1 - ib[1] / H) * (ih - 1)) + 1))
    return x0, y0, x1, y1


def refinar(img, W, H, secoes, log=print, minimo=1.0, variantes=False, rapido=False):
    """Corrige a foto secao por secao (escala X/Y + deslocamento).
    `secoes` = [(bbox_ilha_em_unidades, pinos)]. Com variantes=True tenta tambem
    descobrir o espelhamento — ver a ressalva em melhor_variante.
    Retorna (imagem corrigida, relatorio)."""
    iw, ih = img.size
    out = img.copy()
    rel = []
    for i, (ib, pins) in enumerate(secoes):
        if len(pins) < 30:
            rel.append((i, len(pins), None)); continue
        x0, y0, x1, y1 = _rect(ib, W, H, iw, ih)
        if x1 - x0 < 64 or y1 - y0 < 64:      # secao degenerada: nao da p/ correlacionar
            rel.append((i, len(pins), None)); continue
        sub = img.crop((x0, y0, x1, y1))
        px, py = _pix(pins, W, H, iw, ih)     # pinos da secao em pixels do recorte
        var = melhor_variante(sub, px - x0, py - y0)[0] if variantes else ''
        sub, vx, vy = _variante(sub, px - x0, py - y0, var)
        sx, sy, dx, dy, ganho = medir_secao_px(sub, list(zip(vx, vy)), rapido)
        rel.append((i, len(pins), (sx, sy, dx, dy, ganho, var)))
        cx, cy = float(np.mean(vx)), float(np.mean(vy))
        # out(p) = in(c + S*(p-c) + d)
        mat = (sx, 0, cx * (1 - sx) + dx, 0, sy, cy * (1 - sy) + dy)
        if abs(sx - 1) > 1e-4 or abs(sy - 1) > 1e-4 or max(abs(dx), abs(dy)) >= minimo:
            sub = sub.transform(sub.size, Image.AFFINE, mat, Image.BICUBIC)
        out.paste(sub, (x0, y0))
    for i, n, r in rel:
        if r is None:
            log(f'sec{i}: {n} pinos - pouco dado, mantida')
        else:
            log(f'sec{i}: {n} pinos  espelho={r[5] or "nenhum"}  escala ({r[0]:.4f},{r[1]:.4f})  '
                f'desloc ({r[2]:+.0f},{r[3]:+.0f})px  ganho {r[4]*100:+.0f}%')
    return out, rel


def medir_secao_px(sub, loc, rapido=False):
    """Escala X/Y + deslocamento que poem os pads sob os pinos (pinos em pixels do
    recorte). rapido=True para na resolucao media — serve p/ comparar variantes."""
    iw, ih = sub.size
    g = np.asarray(sub.convert('L'), dtype=np.float64)
    x = np.array([p[0] for p in loc]); y = np.array([p[1] for p in loc])
    cx, cy = x.mean(), y.mean()

    def passo(alvo, escalas, base, lim_frac, r):
        f = min(1.0, alvo / max(iw, ih))
        if f >= 1.0:
            gg, k = g, 1.0
        else:
            w2, h2 = max(8, int(iw * f)), max(8, int(ih * f))
            gg = np.asarray(sub.convert('L').resize((w2, h2), Image.LANCZOS), dtype=np.float64)
            k = w2 / iw
        F = highpass(gg); FT = np.fft.rfft2(F)
        lim = max(3, int(lim_frac * max(gg.shape)))
        melhor = None
        for sx in escalas:
            for sy in escalas:
                m = _mask(k * (cx + base[0] * sx * (x - cx)), k * (cy + base[1] * sy * (y - cy)),
                          gg.shape, r)
                if m is None: continue
                dx, dy, sc = _corr(FT, gg.shape, m, lim)
                if melhor is None or sc > melhor[0]:
                    melhor = (sc, base[0] * sx, base[1] * sy, dx / k, dy / k)
        return melhor

    c = passo(700, np.arange(-0.03, 0.0301, 0.0075) + 1.0, (1.0, 1.0), 0.05, 1)
    if c is None: return (1.0, 1.0, 0.0, 0.0, 0.0)
    c = passo(1400, np.arange(-0.008, 0.0081, 0.002) + 1.0, (c[1], c[2]), 0.02, 2) or c
    sx, sy = c[1], c[2]
    if rapido:
        return (sx, sy, float(c[3]), float(c[4]), 0.0)
    F = highpass(g); FT = np.fft.rfft2(F)
    m0 = _mask(x, y, g.shape, 2)
    base0 = _corr(FT, g.shape, m0, 0)[2] if m0 is not None else 0.0
    m = _mask(cx + sx * (x - cx), cy + sy * (y - cy), g.shape, 2)
    if m is None: return (sx, sy, 0.0, 0.0, 0.0)
    dx, dy, sc = _corr(FT, g.shape, m, max(4, int(0.02 * max(g.shape))))
    return (sx, sy, float(dx), float(dy), (sc - base0) / (abs(base0) + 1e-9))


def contraste_total(img, W, H, secoes):
    """Contraste pad-vizinhanca somado sobre todos os pinos da placa. E a nota que
    separa bem uma face espelhada de uma certa DEPOIS do refino."""
    iw, ih = img.size
    pins = [p for _, ps in secoes for p in ps]
    x, y = _pix(pins, W, H, iw, ih)
    return contraste(img, x, y)


def secoes_do_bvr(bvr):
    """(W, H, [(bbox_ilha, pinos)]) — mesma divisao em secoes do align_bvr."""
    segs, pins, _ = V.parse_bvr(bvr)
    tot = A.bbox([p for s in segs for p in s])
    W, H = tot[2] - tot[0], tot[3] - tot[1]
    axis, boxes = V.secoes_validas(segs, pins)
    if axis is None:
        return W, H, [(tot, pins)]
    return W, H, [(b, [p for p in pins if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]])
                  for b in boxes]


def residual_das_metades(sid):
    """Mede o que ainda sobra em cada metade ja gravada. Convergiu = escala 1.0000
    e deslocamento (0,0): nao ha correcao pequena disponivel. Isso NAO garante que
    a metade esta certa — atribuicao trocada e espelho errado sao minimos estaveis;
    para julgar isso, olhe o qc/<id>_qc.jpg."""
    import json
    import qc_align as Q
    man_path = os.path.join(DV, 'FOTO', sid + '_secoes.json')
    bvr = os.path.join(DV, 'DRONE', sid + '.bvr')
    if not (os.path.exists(man_path) and os.path.exists(bvr)):
        return None
    man = json.load(open(man_path, encoding='utf-8'))
    ilhas = Q.ilhas_e_pinos(bvr)
    out = []
    for i, sec in enumerate(man['secoes']):
        p = os.path.join(DV, 'FOTO', sec['img'])
        if not os.path.exists(p) or i >= len(ilhas): continue
        ib, pins = ilhas[i]
        im = Image.open(p).convert('RGB')
        x, y = Q._pix(pins, ib, im.width, im.height)
        out.append((len(pins),) + medir_secao_px(im, list(zip(x, y))))
    return out


if __name__ == '__main__':
    import glob as _glob
    ids = sys.argv[1:] or sorted(os.path.basename(f).replace('_secoes.json', '')
                                 for f in _glob.glob(os.path.join(DV, 'FOTO', '*_secoes.json')))
    for sid in ids:
        r = residual_das_metades(sid)
        if r is None:
            print(f'{sid}: sem metades geradas (rode o foto_viewer.py)'); continue
        print(f'{sid}')
        for i, (n, sx, sy, dx, dy, ganho) in enumerate(r):
            print(f'  s{i}: {n} pinos  escala ({sx:.4f},{sy:.4f})  '
                  f'desloc ({dx:+.0f},{dy:+.0f})px  ganho {ganho*100:+.0f}%')
