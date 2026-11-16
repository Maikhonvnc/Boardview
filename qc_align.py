# QC do alinhamento foto x pads no digital_viewer: desenha os PIN_ORIGIN do .bvr
# sobre cada metade (build/FOTO/<id>_s<N>.jpg) usando EXATAMENTE o mapeamento do
# viewer, e da uma nota objetiva por metade.
#
# A nota e o contraste do pad sob o pino contra a vizinhanca imediata. CUIDADO: ela
# so vale para comparar orientacoes DA MESMA metade — entre placas nao da, porque
# depende de quao claros os pads sao naquela foto (ha placa bem alinhada com nota
# +1 e outra igualmente boa com +20). Para julgar uma placa, olhe o qc/<id>_qc.jpg.
#
# Uso: python qc_align.py [id ...]        (sem args = todas as placas com foto)
import os, sys, glob, json
import numpy as np
from PIL import Image, ImageDraw
from paths import BV
import align_bvr as V, align_bg as A
import refine_align as R

DV = os.path.join(BV, 'digital_viewer', 'build')
OUT = os.path.join(BV, 'qc')


def ilhas_e_pinos(bvr):
    """[(caixa, pinos_dentro)] por secao. A fonte da verdade e o <placa>_secoes.json
    que o foto_viewer gravou: ele ESCOLHE entre segmentacoes candidatas (inteira x
    dividida) pela medida, e recalcular aqui daria outra resposta nas placas em que
    a escolha nao e a padrao (mavic3pro, air2s) — o QC desenharia meia placa
    esticada sobre a foto inteira. Sem o arquivo, recalcula como antes."""
    segs, pins, _ = V.parse_bvr(bvr)
    dentro = lambda b: [p for p in pins if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]]
    sid = os.path.splitext(os.path.basename(bvr))[0]
    man_path = os.path.join(DV, 'FOTO', sid + '_secoes.json')
    if os.path.exists(man_path):
        secoes = json.load(open(man_path, encoding='utf-8'))['secoes']
        return [(sec['box'], dentro(sec['box'])) for sec in secoes]
    tot = A.bbox([p for s in segs for p in s])
    eixo, caixas = V.secoes_validas(segs, pins)
    if eixo is None:
        return [(tot, pins)]
    return [(b, dentro(b)) for b in caixas]


def run(sid):
    """Gera qc/<id>_qc.jpg e devolve [(n_pinos, contraste)] por metade."""
    bvr = os.path.join(DV, 'DRONE', sid + '.bvr')
    man_path = os.path.join(DV, 'FOTO', sid + '_secoes.json')
    if not (os.path.exists(bvr) and os.path.exists(man_path)):
        return None
    man = json.load(open(man_path, encoding='utf-8'))
    ilhas = ilhas_e_pinos(bvr)
    os.makedirs(OUT, exist_ok=True)

    notas, tiras = [], []
    for i, sec in enumerate(man['secoes']):
        p = os.path.join(DV, 'FOTO', sec['img'])
        if not os.path.exists(p) or i >= len(ilhas): continue
        ib, pins = ilhas[i]
        im = Image.open(p).convert('RGB')
        x, y = _pix(pins, ib, im.width, im.height)
        notas.append((len(pins), R.contraste(im, x, y)))
        d = ImageDraw.Draw(im)
        for px, py in zip(x, y):
            d.ellipse([px - 2, py - 2, px + 2, py + 2], outline=(0, 255, 255))
        tiras.append(im)

    if tiras:                                  # metades lado a lado num arquivo so
        h = max(t.height for t in tiras)
        w = sum(t.width for t in tiras) + 8 * (len(tiras) - 1)
        folha = Image.new('RGB', (w, h), (20, 25, 35))
        cx = 0
        for t in tiras:
            folha.paste(t, (cx, 0)); cx += t.width + 8
        folha.save(os.path.join(OUT, sid + '_qc.jpg'), quality=88)
    return notas


def _pix(pins, ib, w, h):
    iw = max(1e-9, ib[2] - ib[0]); ih = max(1e-9, ib[3] - ib[1])
    x = (np.array([p[0] for p in pins]) - ib[0]) / iw * (w - 1)
    y = (1 - (np.array([p[1] for p in pins]) - ib[1]) / ih) * (h - 1)
    return x, y


if __name__ == '__main__':
    ids = sys.argv[1:] or sorted(os.path.basename(f).replace('_secoes.json', '')
                                 for f in glob.glob(os.path.join(DV, 'FOTO', '*_secoes.json')))
    for sid in ids:
        r = run(sid)
        if r is None:
            print(f'{sid:44} (sem par bvr/foto)')
        else:
            print(f'{sid:44} ' + '   '.join(f's{i}: {n} pinos contraste {c:+6.2f}'
                                            for i, (n, c) in enumerate(r)))
