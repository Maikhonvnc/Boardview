# Mede se a foto de uma metade esta GIRADA em relacao aos pads.
#
# O refino corrige escala e deslocamento, mas um giro de 1-2 graus ele nao ve: ele
# acha o melhor deslocamento MEDIO, e a placa fica "de lado". Para enxergar isso,
# divide a metade num tabuleiro, mede o deslocamento LOCAL de cada bloco e olha o
# padrao: se os deslocamentos giram em torno do centro, e rotacao — e o angulo sai
# do ajuste de minimos quadrados sobre esse campo.
#
# Uso: python medir_giro.py [id ...]
import os, sys, glob, json
import numpy as np
from PIL import Image
from paths import BV
import refine_align as R
import qc_align as Q

DV = os.path.join(BV, 'digital_viewer', 'build')
BLOCOS = 4          # tabuleiro BLOCOS x BLOCOS
MIN_PINOS = 40      # bloco com menos que isso nao da medida confiavel


def giro_da_metade(im, x, y):
    """Angulo (graus) e escala que melhor explicam os deslocamentos locais.
    Positivo = a foto esta girada no sentido anti-horario em relacao aos pads."""
    iw, ih = im.size
    g = np.asarray(im.convert('L'), dtype=np.float64)
    amostras = []
    for bi in range(BLOCOS):
        for bj in range(BLOCOS):
            x0, x1 = bi * iw // BLOCOS, (bi + 1) * iw // BLOCOS
            y0, y1 = bj * ih // BLOCOS, (bj + 1) * ih // BLOCOS
            dentro = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
            if dentro.sum() < MIN_PINOS: continue
            sub = im.crop((x0, y0, x1, y1))
            gg = np.asarray(sub.convert('L'), dtype=np.float64)
            F = R.highpass(gg)
            m = R._mask(x[dentro] - x0, y[dentro] - y0, gg.shape, 2)
            if m is None: continue
            dx, dy, _ = R._corr(np.fft.rfft2(F), gg.shape, m, max(6, int(0.04 * max(gg.shape))))
            amostras.append(((x0 + x1) / 2, (y0 + y1) / 2, dx, dy))
    if len(amostras) < 4:
        return None
    a = np.array(amostras, dtype=float)
    cx, cy = a[:, 0].mean(), a[:, 1].mean()
    px, py = a[:, 0] - cx, a[:, 1] - cy
    dx, dy = a[:, 2], a[:, 3]
    # dx = s*px - t*py ; dy = t*px + s*py   (s = escala extra, t = angulo em rad)
    A = np.vstack([np.concatenate([px, py]), np.concatenate([-py, px])]).T
    b = np.concatenate([dx, dy])
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    s, t = sol
    resid = b - A @ sol
    return {'graus': float(np.degrees(t)), 'escala_extra': float(s),
            'blocos': len(a), 'residuo_px': float(np.sqrt((resid ** 2).mean())),
            'desloc_px': float(np.sqrt((dx ** 2 + dy ** 2).mean()))}


def medir(sid):
    man = os.path.join(DV, 'FOTO', sid + '_secoes.json')
    bvr = os.path.join(DV, 'DRONE', sid + '.bvr')
    if not (os.path.exists(man) and os.path.exists(bvr)): return None
    ilhas = Q.ilhas_e_pinos(bvr)
    out = []
    for i, sec in enumerate(json.load(open(man, encoding='utf-8'))['secoes']):
        p = os.path.join(DV, 'FOTO', sec['img'])
        if not os.path.exists(p) or i >= len(ilhas): continue
        ib, pins = ilhas[i]
        im = Image.open(p).convert('RGB')
        x, y = Q._pix(pins, ib, im.width, im.height)
        out.append((i, len(pins), giro_da_metade(im, x, y)))
    return out


if __name__ == '__main__':
    ids = sys.argv[1:] or sorted(os.path.basename(f).replace('_secoes.json', '')
                                 for f in glob.glob(os.path.join(DV, 'FOTO', '*_secoes.json')))
    for sid in ids:
        r = medir(sid)
        if not r:
            print(f'{sid}: sem metades geradas'); continue
        for i, n, g in r:
            if g is None:
                print(f'{sid:34} s{i}: poucos blocos com pino')
            else:
                print(f'{sid:34} s{i}: giro {g["graus"]:+.2f} graus  '
                      f'escala extra {g["escala_extra"]*100:+.2f}%  '
                      f'desloc medio {g["desloc_px"]:.1f}px  '
                      f'residuo {g["residuo_px"]:.1f}px  ({g["blocos"]} blocos)')
