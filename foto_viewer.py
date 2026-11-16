# Gera as fotos de fundo do digital_viewer — UMA IMAGEM POR METADE da placa.
#
# Por que por metade: nestes .bvr as duas faces da placa entram como duas ILHAS do
# mesmo contorno (todos os pinos sao lado T; nao existe lado B). E a foto do XZZ nao
# segue padrao: as vezes a face de cima esta na esquerda, as vezes na direita, as
# vezes empilhada. Juntar tudo numa imagem so obriga as duas metades a dividirem a
# mesma escala e o mesmo deslocamento — foi por isso que alinhar embaixo desalinhava
# em cima. Cada metade agora e um arquivo com a sua propria caixa, escala e ajuste.
#
# Para cada placa XZZ que tenha foto (o _bg.png ja composto pelo align_bg) e um
# .bvr correspondente no acervo DigitalBoard:
#   1. descobre a qual placa do viewer ela corresponde (assinatura dos pinos do
#      .bvr, nao o nome — o acervo guarda o mesmo boardview com varios nomes);
#   2. acha as ilhas do contorno e os blobs da foto;
#   3. decide rotacao, qual blob vai em qual ilha (inclusive trocado) e o
#      espelhamento de cada um, pela nota de contraste depois de refinar;
#   4. refina escala e deslocamento de cada metade separadamente;
#   5. grava build/FOTO/<id>_s<N>.jpg + <id>_secoes.json, um QC em qc/ e atualiza
#      build/boards.json.
#
# Uso: python foto_viewer.py [id-ou-parte-do-nome ...] [--sem-refino] [--qc-nao]
import os, re, sys, glob, json, shutil
from itertools import combinations, permutations
import numpy as np
from PIL import Image
from paths import BV, DRONES, DIGITALBOARD, DV_BUILD
import align_bvr as V
import align_bg as A
import refine_align as R
import medir_giro
import medir_afim

FOTO = os.path.join(DV_BUILD, 'FOTO')
DRONE = os.path.join(DV_BUILD, 'DRONE')
QC = os.path.join(BV, 'qc')
LADO_MAX = 2000                  # maior lado de cada imagem de metade
LIMIAR_GIRO = 0.05               # graus: abaixo disso girar so borra a imagem

# Numero de secoes decidido na bancada, quando a medida automatica discorda.
# O contraste e uma media sobre a placa toda e nao enxerga uma coisa que a pessoa
# enxerga: uma metade PERFEITA vale mais que um encaixe morno no conjunto, porque
# a outra metade se resolve na mao com o modo AJUSTE. O Mavic 3 Pro e esse caso —
# inteiro da +30,5 parelho, dividido da +52,3 e +0,9, e a media diz "inteiro".
SECOES_FORCADAS = {
    'mavic3pro': 2,
    'air3': 2,       # inteiro, as duas faces andavam juntas no AJUSTE
}

# Linha de corte entre as faces conferida a mao: (eixo, posicao) em unidades do .bvr
# (eixo 1 = y). No air3 o contorno tem uma falha em y=1404, DENTRO de uma face, e o
# corte automatico caia ali (metades 1401/1805 — uma foto saia achatada). O vale de
# pinos, que e a divisa real, fica em ~1605.
CORTE_FORCADO = {
    'air3': (1, 1605.0),
}

# Rotacao conferida a olho (lendo a serigrafia), so p/ poupar tentativa.
ROT_CONHECIDA = {
    'DJI Mini2-PP001950.03 PCB layer': 90,
    'Mavic PRO-P024422 PCB layer': 90,
    'DJI Mavic3 PP002022.10 PCB layer': 90,
    'DJI Mavic3 Pro-PP003253.03 PCB layer': 90,
}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', os.path.splitext(s)[0].lower()).strip('-')


def assinatura(bvr):
    """Identidade do boardview pelos DADOS (n de pinos + extensao), porque o
    acervo tem o mesmo arquivo salvo com bytes e nomes diferentes."""
    xs, ys = [], []
    for ln in open(bvr, encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s.startswith('PIN_ORIGIN'):
            t = s.split()
            try: xs.append(float(t[1])); ys.append(float(t[2]))
            except (ValueError, IndexError): pass
    if not xs: return None
    return (len(xs), round(max(xs) - min(xs)), round(max(ys) - min(ys)))


def foto_da_placa(pcb):
    """A foto ja composta pelo align_bg: a que o .conf aponta, ou o _bg ao lado."""
    d, b = os.path.dirname(pcb), os.path.splitext(os.path.basename(pcb))[0]
    conf = os.path.join(d, b + '.conf')
    if os.path.exists(conf):
        m = re.search(r'(?m)^TopImageFile\s*=\s*(.+)$',
                      open(conf, encoding='utf-8', errors='replace').read())
        if m:
            p = os.path.join(d, m.group(1).strip())
            if os.path.exists(p): return p
    for ext in ('_bg.png', '_bg.jpg'):
        if os.path.exists(os.path.join(d, b + ext)): return os.path.join(d, b + ext)
    return None


def pares():
    """[(pcb, foto, bvr_do_acervo)] — placas com foto E boardview no acervo."""
    acervo = {os.path.splitext(os.path.basename(p))[0].lower(): p
              for p in glob.glob(os.path.join(DIGITALBOARD, 'boardview-bvr', '*.bvr'))}
    out = []
    for pcb in sorted(glob.glob(DRONES + '/**/*.pcb', recursive=True)):
        if '__MACOSX' in pcb or os.path.basename(pcb).startswith('._'):
            continue
        base = os.path.splitext(os.path.basename(pcb))[0]
        f, b = foto_da_placa(pcb), acervo.get(base.lower())
        if f and b: out.append((pcb, f, b))
    return out


# --- geometria --------------------------------------------------------------

def ilhas_e_pinos(bvr, corte=None):
    """(W, H, [(eixo, ilhas), ...]) — as segmentacoes CANDIDATAS da placa.

    Sao ate duas: a do vale estrito (5% do pico) e a do vale afrouxado (15%), que
    so difere quando a estrita nao achou divisao nenhuma. Quem escolhe e o
    processar(), pela mesma medida de contraste que ja julga giro e espelho —
    aprendi na marra que afrouxar para todo mundo quebra alguem: dividir o air3
    derrubou de +23,8 inteiro para +7,7/+5,1."""
    segs, pins, _ = V.parse_bvr(bvr)
    tot = A.bbox([p for s in segs for p in s])
    W, H = tot[2] - tot[0], tot[3] - tot[1]

    def montar(fracs):
        antigo = os.environ.get('BOARDVIEW_VALE_FRACS')
        os.environ['BOARDVIEW_VALE_FRACS'] = fracs
        try:
            eixo, caixas = V.secoes_validas(segs, pins)
        finally:
            if antigo is None: os.environ.pop('BOARDVIEW_VALE_FRACS', None)
            else: os.environ['BOARDVIEW_VALE_FRACS'] = antigo
        if eixo is None:
            return None, [(tot, pins)]
        return eixo, [(b, [p for p in pins if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]])
                      for b in caixas]

    cands = [montar('0.05')]
    solto = montar('0.05,0.15')
    if len(solto[1]) != len(cands[0][1]):
        cands.append(solto)
    if corte:                                  # linha de corte conferida a mao (CORTE_FORCADO)
        eixo, pos = corte
        a, b = (list(tot), list(tot))
        a[2 if eixo == 0 else 3] = pos
        b[0 if eixo == 0 else 1] = pos
        cands.append((eixo, [(tuple(c), [p for p in pins if c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3]])
                             for c in (a, b)]))
    return W, H, cands


def proporcao(caixa):
    return (caixa[2] - caixa[0]) / max(1e-9, caixa[3] - caixa[1])


def blobs_da_foto(img, eixo, n_ilhas):
    """Pedacos de placa na foto. Sem eixo definido, tenta os dois e fica com o que
    achar mais pedacos (a foto quase sempre traz as duas faces)."""
    melhor, eixo_bom = [], eixo if eixo is not None else 0
    for e in ([eixo] if eixo is not None else [0, 1]):
        b = V.find_blobs(img, e)
        b.sort(key=lambda r: r[e])
        if len(b) > len(melhor): melhor, eixo_bom = b, e
    if not melhor:
        melhor = [(0, 0, img.width - 1, img.height - 1)]
    if len(melhor) == 1:
        # A divisoria entre as duas faces nem sempre e escura o bastante p/ quebrar o
        # blob. Corta na linha de menor conteudo perto do meio — cortar no meio exato,
        # como se fazia antes, deixava uma metade esticada sempre que as duas ilhas do
        # .bvr nao tem o mesmo tamanho (no Mini 2 diferem 3%).
        partes = cortar_em_dois(img, eixo_bom, melhor[0])
        if n_ilhas > 1:
            return partes
        # Com UMA ilha so, a foto ainda traz as duas faces e so uma delas cabe no
        # contorno: oferece a foto inteira e cada metade como candidatas, e deixa o
        # contraste escolher. Sem isto as duas faces eram espremidas numa placa so
        # (era o caso do Mini 1 e do RC Plus).
        return [melhor[0]] + partes
    return melhor


def cortar_em_dois(img, eixo, blob):
    """Divide um blob em dois no eixo DADO, no vale de conteudo mais proximo do meio.

    Ja tentei procurar o vale nos dois eixos e em qualquer posicao (10-90%): resolvia
    um caso e regredia a Mini 3 de +32/+48 para +12/+23, porque escolhia um vao que
    nao era o das faces. O eixo vem de quem chama — que o tira da divisao do contorno,
    informacao mais confiavel que o perfil da foto."""
    x0, y0, x1, y1 = blob
    a = np.asarray(img.convert('RGB').crop((x0, y0, x1 + 1, y1 + 1))).astype(int)
    borda = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    mask = np.abs(a - np.median(borda, axis=0)).sum(axis=2) > 60
    e = eixo if eixo is not None else 0
    perfil = mask.sum(axis=0 if e == 0 else 1).astype(float)
    n = len(perfil)
    lo, hi = int(n * 0.35), int(n * 0.65)
    corte = n // 2 if hi - lo < 3 else lo + int(np.argmin(perfil[lo:hi]))
    if e == 0:
        return [(x0, y0, x0 + corte, y1), (x0 + corte + 1, y0, x1, y1)]
    return [(x0, y0, x1, y0 + corte), (x0, y0 + corte + 1, x1, y1)]


def pinos_no_recorte(pins, ib, w, h):
    """Pinos da ilha -> pixels da imagem da metade (linha 0 = topo, y do .bvr sobe)."""
    iw_u = max(1e-9, ib[2] - ib[0]); ih_u = max(1e-9, ib[3] - ib[1])
    x = (np.array([p[0] for p in pins]) - ib[0]) / iw_u * (w - 1)
    y = (1 - (np.array([p[1] for p in pins]) - ib[1]) / ih_u) * (h - 1)
    return x, y


def tamanho_da_metade(ib, lado=None):
    """Resolucao da imagem da metade, proporcional a ilha, limitada por `lado`."""
    w_u, h_u = ib[2] - ib[0], ib[3] - ib[1]
    k = (lado or LADO_MAX) / max(w_u, h_u)
    return max(8, int(round(w_u * k))), max(8, int(round(h_u * k)))


def recorte_orientado(img, blob, var):
    """Recorte do pedaco com o espelhamento aplicado, ainda na resolucao da foto."""
    c = img.crop((blob[0], blob[1], blob[2] + 1, blob[3] + 1)).convert('RGB')
    if 'H' in var: c = c.transpose(Image.FLIP_LEFT_RIGHT)
    if 'V' in var: c = c.transpose(Image.FLIP_TOP_BOTTOM)
    return c


def metade(img, blob, ib, var, lado=None, giro=0.0):
    """Recorta o blob da foto, aplica orientacao e giro fino, e estica na proporcao
    da ilha. O giro entra AQUI, na resolucao da foto, e nao na imagem ja pronta:
    girar o resultado final custaria uma segunda reamostragem e borraria os pads
    (medido: girar no fim derrubou o contraste de 5,5 para 2,1; girar na origem
    subiu para 17,8)."""
    c = img.crop((blob[0], blob[1], blob[2] + 1, blob[3] + 1)).convert('RGB')
    if 'H' in var: c = c.transpose(Image.FLIP_LEFT_RIGHT)
    if 'V' in var: c = c.transpose(Image.FLIP_TOP_BOTTOM)
    if giro: c = c.rotate(giro, resample=Image.BICUBIC)
    return c.resize(tamanho_da_metade(ib, lado), Image.LANCZOS)


def avaliar(img, blob, ib, pins, var, rapido=True, lado=None, giro=0.0):
    """Nota (contraste) e ajuste fino de uma metade numa dada orientacao.
    `lado` menor = mesma conta numa resolucao menor, p/ comparar variantes barato."""
    m = metade(img, blob, ib, var, lado, giro)
    x, y = pinos_no_recorte(pins, ib, m.width, m.height)
    sx, sy, dx, dy, _g = R.medir_secao_px(m, list(zip(x, y)), rapido=rapido)
    cx, cy = x.mean(), y.mean()
    nota = R.contraste(m, cx + sx * (x - cx) + dx, cy + sy * (y - cy) + dy)
    return nota, (sx, sy, dx, dy), m


def avaliar_afim(img, blob, ib, pins, var):
    """Refino em duas etapas, mas UMA reamostragem so.

    Etapa 1 acha escala e deslocamento (correlacao FFT). Etapa 2 mede, no campo de
    deslocamentos por bloco, a matriz 2x2 inteira — que cobre giro E CISALHAMENTO.
    O cisalhamento e o que sobrava: com foto tirada um pouco de lado, a fileira de
    pads que e horizontal no boardview sai inclinada, e alinhar uma ponta levanta a
    outra. Um ajuste so-de-giro nao ve isso — pior, absorve o cisalhamento num giro
    quase zero (a Mini 3 Pro media 0,00 graus tendo +0,27 de giro e +0,35 de
    cisalhamento).

    As duas etapas sao COMPOSTAS numa matriz unica antes de tocar nos pixels: aplicar
    uma depois da outra reamostraria a imagem duas vezes e borraria os pads.
    """
    m0 = metade(img, blob, ib, var)
    x, y = pinos_no_recorte(pins, ib, m0.width, m0.height)
    sx, sy, dx, dy, _ = R.medir_secao_px(m0, list(zip(x, y)), rapido=False)
    m1 = aplicar(m0, x, y, (sx, sy, dx, dy))          # descartavel: so p/ medir a etapa 2

    af = medir_afim.afim_da_metade(m1, x, y)
    c = np.array([float(np.mean(x)), float(np.mean(y))])
    S = np.diag([sx, sy])
    d = np.array([dx, dy])
    M = af['M'] if af else np.eye(2)
    t = af['t'] if af else np.zeros(2)

    # etapa 1:  q = c + S(p - c) + d          (escala + deslocamento)
    # etapa 2:  p' = c + M(p - c) + t         (giro + cisalhamento + escala fina)
    A = S @ M
    b = c + S @ (M @ (-c) + c + t - c) + d

    # Renderiza a metade final DIRETO do recorte da foto, com as duas etapas e o
    # redimensionamento numa transformacao so: cada reamostragem extra borra os pads
    # (girar a imagem ja pronta chegou a derrubar o contraste de 5,5 para 2,1).
    cr = recorte_orientado(img, blob, var)
    tw, th = m0.size
    K = np.diag([cr.width / tw, cr.height / th])
    AK, bK = K @ A, K @ b
    m2 = cr.transform((tw, th), Image.AFFINE,
                      (AK[0, 0], AK[0, 1], bK[0], AK[1, 0], AK[1, 1], bK[1]),
                      Image.BICUBIC)

    # A medida da etapa 2 pode sair ruim (placa pequena, poucos blocos, correlacao
    # fraca) e ai a afim PIORA muito — foi o caso de uma placa que caiu de +24 para
    # +7. Mas o contraste e ruidoso na faixa baixa, e comparar 7,9 com 7,3 nao diz
    # nada: com esse criterio apertado a guarda descartava a afim e deixava 0,5 grau
    # de cisalhamento no lugar. Entao so rejeita PERDA GRANDE (>20%); no resto vale a
    # geometria, que e o que a afim corrige e o que se mede igual entre placas.
    n1, n2 = R.contraste(m1, x, y), R.contraste(m2, x, y)
    if n2 >= 0.8 * n1:
        return n2, (A, b), m2
    return n1, (S, c + d - S @ c), m1


def aplicar(m, x, y, aj):
    """Grava o ajuste (escala + deslocamento) nos pixels da metade."""
    sx, sy, dx, dy = aj
    if abs(sx - 1) < 1e-4 and abs(sy - 1) < 1e-4 and max(abs(dx), abs(dy)) < 1:
        return m
    cx, cy = float(np.mean(x)), float(np.mean(y))
    mat = (sx, 0, cx * (1 - sx) + dx, 0, sy, cy * (1 - sy) + dy)
    return m.transform(m.size, Image.AFFINE, mat, Image.BICUBIC)


# --- processamento de uma placa ---------------------------------------------

def processar(pcb, foto, bvr, sid, refinar=True, qc=True):
    W, H, candidatos = ilhas_e_pinos(bvr, CORTE_FORCADO.get(sid))
    if sid in CORTE_FORCADO:                   # o corte conferido manda: so ele concorre
        candidatos = candidatos[-1:]
    base = os.path.splitext(os.path.basename(pcb))[0]
    rot_fixa = ROT_CONHECIDA.get(base)

    # 'forcado' so vale se de fato filtrou: se nenhum candidato tem o numero pedido
    # (o .bvr mudou, a divisao sumiu), avisa alto em vez de o log fingir que valeu
    forcado = SECOES_FORCADAS.get(sid)
    if forcado:
        so = [c for c in candidatos if len(c[1]) == forcado]
        if so:
            candidatos = so
        else:
            print(f'  AVISO {sid}: SECOES_FORCADAS={forcado} IGNORADO — '
                  f'nenhuma segmentacao candidata tem {forcado} secao(oes)')
            forcado = None

    def atribuicoes(blobs, ilhas):
        """Que pedaco da foto vai em que ilha. Com 2 ilhas, ordem natural e trocada
        (a foto do XZZ nao segue padrao). Com 1 ilha, cada candidato sozinho."""
        if len(ilhas) == 1:
            return [(i,) for i in range(len(blobs))]
        return list(permutations(range(len(blobs)), len(ilhas)))

    # Rotacao, atribuicao e espelho saem TODOS da mesma medida: o contraste depois
    # de refinar (numa resolucao menor, p/ caber no tempo). Ja tentei uma triagem
    # barata antes disso e ela escolhia configuracao que a medida final desmentia —
    # nao vale o tempo que economiza.
    # Basta rot 0 e 90: 180 e 270 sao essas mesmas com o espelho HV, que ja e testado.
    # A nota e a media do contraste PONDERADA POR PINOS. Somar as secoes favoreceria
    # dividir so por haver mais parcelas; ponderando por pinos, 1 e 2 secoes ficam na
    # mesma escala (cobrem os mesmos pinos) e a ordem DENTRO de um mesmo numero de
    # secoes nao muda — continua sendo como rotacao e espelho ja eram escolhidos.
    escolha = None
    # As 4 rotacoes, nao so 0 e 90: eu supus que 180/270 fossem essas mais o espelho
    # HV, mas a DETECCAO DE BLOB acontece na imagem ja girada — margens e posicao do
    # corte saem diferentes. Cortar para 0/90 regrediu a Mini 3, cuja melhor config
    # era rot=180.
    for eixo, ilhas in candidatos:
      for rot in ([rot_fixa] if rot_fixa is not None else (0, 90, 180, 270)):
        img = Image.open(foto)
        if rot: img = img.rotate(-rot, expand=True)
        blobs = blobs_da_foto(img, eixo, len(ilhas))
        for atr in atribuicoes(blobs, ilhas):
            soma, peso, vs = 0.0, 0, []
            for (ib, pins), bi in zip(ilhas, atr):
                if len(pins) < 30:
                    vs.append(''); continue
                # na MESMA resolucao final: o contraste nao e invariante a escala
                # (a 700px os pads borram e a ordem dos candidatos muda), entao
                # escolher numa resolucao e julgar noutra da resultado incoerente
                n, v = max(((avaliar(img, blobs[bi], ib, pins, v)[0], v)
                            for v in R.VARIANTES), key=lambda t: t[0])
                soma += n * len(pins); peso += len(pins); vs.append(v)
            nota = soma / peso if peso else 0.0
            if escolha is None or nota > escolha[0]:
                escolha = (nota, rot, atr, vs, blobs, img, eixo, ilhas)
    if escolha is None:
        print(f'  {sid}: nao consegui achar as metades na foto'); return False
    nota, rot, atr, vs, blobs, img, eixo, ilhas = escolha
    print(f'  {sid}: rot={rot}  {len(ilhas)} metade(s)  candidatos={len(blobs)}  '
          f'atribuicao={list(atr)}  espelho={[v or "-" for v in vs]}  nota {nota:+.1f}'
          f'{"  (secoes forcadas)" if forcado else ""}')

    os.makedirs(FOTO, exist_ok=True)
    man = {'w': round(W, 3), 'h': round(H, 3), 'secoes': []}
    for i, ((ib, pins), bi) in enumerate(zip(ilhas, atr)):
        var = vs[i]
        m = metade(img, blobs[bi], ib, var)
        x, y = pinos_no_recorte(pins, ib, m.width, m.height)
        if refinar and len(pins) >= 30:
            # A caixa do pedaco tambem e candidata: a do detector costuma vir com
            # margem de fundo (a sombra em volta da placa passa do limiar), e a
            # apertada as vezes corta placa. Mede as duas e fica com a melhor.
            # O refino e AFIM: cobre escala, deslocamento, giro e cisalhamento de
            # uma vez — corrigir so giro deixava a fileira de pads subindo na ponta.
            nota_i, _tr, m = avaliar_afim(img, blobs[bi], ib, pins, var)
            af = medir_afim.afim_da_metade(m, *pinos_no_recorte(pins, ib, m.width, m.height))
            resta = (f'  resta giro {af["giro"]:+.2f} cisalha {af["cisalha"]:+.2f}'
                     if af else '')
            print(f'    s{i}: {len(pins)} pinos  blob {bi}  espelho={var or "nenhum"}'
                  f'  contraste {nota_i:+.1f}{resta}')
        nome = f'{sid}_s{i}.jpg'
        m.save(os.path.join(FOTO, nome), quality=88)
        man['secoes'].append({'img': nome, 'box': [round(v, 3) for v in ib]})
    json.dump(man, open(os.path.join(FOTO, sid + '_secoes.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)

    if qc:
        os.makedirs(QC, exist_ok=True)
        import qc_align
        qc_align.run(sid)
    return True


def main():
    alvos = [a.lower() for a in sys.argv[1:] if not a.startswith('--')]
    refinar = '--sem-refino' not in sys.argv
    qc = '--qc-nao' not in sys.argv

    # o mesmo boardview aparece em DRONE/ com nomes diferentes; prefere o id que
    # ja esta no boards.json (e, empatando, o nome mais curto = o oficial).
    bj = os.path.join(DV_BUILD, 'boards.json')
    listados = {b['id'] for b in json.load(open(bj, encoding='utf-8'))} if os.path.exists(bj) else set()
    oficiais = {}
    for b in sorted(glob.glob(os.path.join(DRONE, '*.bvr')), key=lambda p: len(p)):
        s = assinatura(b)
        if not s: continue
        sid = os.path.splitext(os.path.basename(b))[0]
        if s not in oficiais or (sid in listados and oficiais[s] not in listados):
            oficiais[s] = sid

    feitos = {}
    for pcb, foto, bvr_ac in pares():
        base = os.path.splitext(os.path.basename(pcb))[0]
        sid = oficiais.get(assinatura(bvr_ac))
        novo = sid is None
        if novo:                       # placa que o acervo tem mas o viewer nao listava
            sid = slug(base)
            shutil.copy(bvr_ac, os.path.join(DRONE, sid + '.bvr'))
        if alvos and not any(a in sid.lower() or a in base.lower() for a in alvos):
            continue
        print(f'{base}  ->  {sid}{"  (nova no viewer)" if novo else ""}')
        if processar(pcb, foto, os.path.join(DRONE, sid + '.bvr'), sid, refinar, qc):
            feitos[sid] = f'{os.path.basename(os.path.dirname(pcb))}  |  {base}'

    # boards.json: marca quem tem foto e inclui as placas novas
    lista = json.load(open(bj, encoding='utf-8')) if os.path.exists(bj) else []
    # tira do dropdown a placa cujo .bvr sumiu (senao o viewer abre e nao carrega nada)
    lista = [b for b in lista if os.path.exists(os.path.join(DRONE, b['id'] + '.bvr'))]
    ids = {b['id'] for b in lista}
    for b in lista:
        b['foto'] = os.path.exists(os.path.join(FOTO, b['id'] + '_secoes.json'))
        b['borda'] = os.path.exists(os.path.join(DV_BUILD, 'SM', b['id'] + '_borda.jpg'))
    for sid, nome in feitos.items():
        if sid not in ids:
            lista.append({'id': sid, 'name': nome, 'borda': False, 'foto': True})
    lista.sort(key=lambda b: b['name'])
    json.dump(lista, open(bj, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'\n{len(feitos)} placas processadas; {sum(b["foto"] for b in lista)}/{len(lista)} '
          f'com foto -> {bj}')


if __name__ == '__main__':
    main()
