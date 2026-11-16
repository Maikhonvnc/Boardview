# Mede a transformacao AFIM completa que ainda falta entre a foto e os pads.
#
# O medir_giro.py ajusta so giro + escala uniforme. Se a foto foi tirada um pouco
# de lado, sobra CISALHAMENTO: as fileiras de pad, que sao perfeitamente horizontais
# no boardview, saem inclinadas na foto de um jeito que giro nenhum conserta —
# alinha-se um extremo e o outro sobe. Aqui o campo de deslocamentos dos blocos e
# ajustado por uma matriz 2x2 inteira, que separa escala, giro e cisalhamento.
#
# Uso: python medir_afim.py [id ...]
import os, sys, glob, json
import numpy as np
from PIL import Image
from paths import BV
import refine_align as R
import qc_align as Q
import medir_giro as G

DV = G.DV


def amostrar(im, x, y, blocos, min_pinos):
    """Deslocamento local medido em cada bloco de um tabuleiro blocos x blocos."""
    amostras = []
    iw, ih = im.size
    for bi in range(blocos):
        for bj in range(blocos):
            x0, x1 = bi * iw // blocos, (bi + 1) * iw // blocos
            y0, y1 = bj * ih // blocos, (bj + 1) * ih // blocos
            dentro = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
            if dentro.sum() < min_pinos: continue
            sub = im.crop((x0, y0, x1, y1))
            gg = np.asarray(sub.convert('L'), dtype=np.float64)
            F = R.highpass(gg)
            m = R._mask(x[dentro] - x0, y[dentro] - y0, gg.shape, 2)
            if m is None: continue
            dx, dy, _ = R._corr(np.fft.rfft2(F), gg.shape, m,
                                max(6, int(0.04 * max(gg.shape))))
            amostras.append(((x0 + x1) / 2, (y0 + y1) / 2, dx, dy))
    return amostras


def afim_da_metade(im, x, y):
    """Matriz 2x2 (mais o resto) que explica os deslocamentos locais.
    Devolve escala X/Y, giro e cisalhamento em graus, e o residuo que sobra.

    A grade se adapta ao tamanho da placa: com 4x4 e 40 pinos por bloco, uma placa
    pequena (o 4P IMU tem 343 pinos numa metade) nao juntava blocos suficientes e
    ficava SEM correcao afim nenhuma. Tenta grades menores antes de desistir."""
    amostras = []
    for blocos, min_pinos in ((G.BLOCOS, G.MIN_PINOS), (3, 20), (2, 10)):
        amostras = amostrar(im, x, y, blocos, min_pinos)
        if len(amostras) >= 4:      # 4 blocos = 8 equacoes p/ 6 incognitas
            break
    if len(amostras) < 4:
        return None
    a = np.array(amostras, dtype=float)
    px, py = a[:, 0] - a[:, 0].mean(), a[:, 1] - a[:, 1].mean()
    A = np.column_stack([px, py, np.ones(len(a))])
    solx, *_ = np.linalg.lstsq(A, a[:, 2], rcond=None)
    soly, *_ = np.linalg.lstsq(A, a[:, 3], rcond=None)
    # deslocamento = M @ p + t, com M = I + [[a11,a12],[a21,a22]]
    M = np.array([[1 + solx[0], solx[1]], [soly[0], 1 + soly[1]]])
    res = np.hstack([a[:, 2] - A @ solx, a[:, 3] - A @ soly])
    # decompoe M em giro * (escala + cisalhamento)  (QR)
    Q_, Rr = np.linalg.qr(M)
    if Rr[0, 0] < 0: Q_[:, 0] *= -1; Rr[0, :] *= -1
    if Rr[1, 1] < 0: Q_[:, 1] *= -1; Rr[1, :] *= -1
    return {
        'M': M, 't': np.array([solx[2], soly[2]]),
        'centro': np.array([a[:, 0].mean(), a[:, 1].mean()]),
        'giro': float(np.degrees(np.arctan2(Q_[1, 0], Q_[0, 0]))),
        'escala_x': float(Rr[0, 0]), 'escala_y': float(Rr[1, 1]),
        'cisalha': float(np.degrees(np.arctan2(Rr[0, 1], Rr[1, 1]))),
        'residuo_px': float(np.sqrt((res ** 2).mean())),
        'desloc_px': float(np.sqrt((a[:, 2] ** 2 + a[:, 3] ** 2).mean())),
        'blocos': len(a),
    }


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
        out.append((i, len(pins), afim_da_metade(im, x, y)))
    return out


if __name__ == '__main__':
    ids = sys.argv[1:] or sorted(os.path.basename(f).replace('_secoes.json', '')
                                 for f in glob.glob(os.path.join(DV, 'FOTO', '*_secoes.json')))
    for sid in ids:
        r = medir(sid)
        if not r:
            print(f'{sid}: sem metades geradas'); continue
        for i, n, a in r:
            if a is None:
                print(f'{sid:30} s{i}: poucos blocos')
            else:
                print(f'{sid:30} s{i}: giro {a["giro"]:+.3f} graus  '
                      f'CISALHA {a["cisalha"]:+.3f} graus  '
                      f'escala {a["escala_x"]:.4f}x{a["escala_y"]:.4f}  '
                      f'sobra {a["desloc_px"]:.1f}px  residuo {a["residuo_px"]:.1f}px')
