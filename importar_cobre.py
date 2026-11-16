# Importa o layout de cobre (trilhas, vias, contorno) dos JSON exportados do
# DigitalBoard / visualizador server515 (formato "skilbypm"), que ficam em
# digital_viewer/build/COBRE/<MODELO>.json (baixados de .../r2.dev/drone/<MODELO>.json).
#
# Para cada arquivo: acha a placa .bvr com os mesmos componentes, ajusta a
# transformacao afim (minimos quadrados sobre TODOS os pinos casados por
# componente+pino) e grava digital_viewer/build/COBRE/<placa>.cobre.json ja em
# coordenadas do .bvr, enxuto (sem a imagem embutida):
#   {placa, origem, erro_medio, camadas:[...], contorno:[[x1,y1,x2,y2],...],
#    malhas: {Net25: {t:[[camada,x1,y1,x2,y2,larg],...], v:[[x,y,diam,cA,cB],...]}}}
# Uso: python importar_cobre.py
import os, json, glob
import numpy as np
from paths import BV

DRONE = os.path.join(BV, 'digital_viewer', 'build', 'DRONE')
COBRE = os.path.join(BV, 'digital_viewer', 'build', 'COBRE')


def pinos_bvr(caminho):
    """{(PECA, PINO): (x, y)} do .bvr."""
    out, peca, pino = {}, None, None
    for ln in open(caminho, encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s.startswith('PART_NAME '):
            peca = s.split(None, 1)[1]
        elif s.startswith('PIN_NUMBER '):
            pino = s.split(None, 1)[1]
        elif s.startswith('PIN_ORIGIN') and peca and pino is not None:
            x, y = map(float, s.split()[1:3])
            out[(peca, pino)] = (x, y)
    return out


def main():
    bvrs = {os.path.basename(f)[:-4]: pinos_bvr(f) for f in glob.glob(os.path.join(DRONE, '*.bvr'))}
    pecas = {k: {pc for pc, _ in v} for k, v in bvrs.items()}
    melhor = {}                       # placa -> pinos no ajuste do arquivo ja gravado
    for f in sorted(glob.glob(os.path.join(COBRE, '*.json'))):
        if f.endswith('.cobre.json'):
            continue
        d = json.load(open(f, encoding='utf-8'))
        comps = {c['name'] for c in d['components']}
        placa = max(pecas, key=lambda k: len(comps & pecas[k]))
        frac = len(comps & pecas[placa]) / max(1, len(comps | pecas[placa]))
        if frac < 0.8:
            print(f'{os.path.basename(f)}: nenhuma placa .bvr casa (melhor {placa}, {frac:.0%}) — pulado')
            continue
        alvo = bvrs[placa]
        src, dst = [], []
        for c in d['components']:
            for p in c['pins']:
                q = alvo.get((c['name'], str(p['name'])))
                if q:
                    src.append((p['x'], p['y'])); dst.append(q)
        # ajuste robusto: alguns pinos tem numeracao diferente entre os dois arquivos
        # (casam o nome errado); refaz so com os que ficam a menos de 2 unidades
        A = np.hstack([np.array(src), np.ones((len(src), 1))])
        B = np.array(dst)
        usar = np.ones(len(src), bool)
        for _ in range(6):
            M, *_ = np.linalg.lstsq(A[usar], B[usar], rcond=None)   # 3x2
            e = np.linalg.norm(A @ M - B, axis=1)
            usar = e < 2
        erro = float(e[usar].mean())
        if erro > 0.5 or usar.sum() <= melhor.get(placa, 0):
            print(f'{os.path.basename(f)} -> {placa}: {usar.sum()} pinos no ajuste, erro {erro:.3f} — '
                  + ('encaixe ruim' if erro > 0.5 else 'outra revisao encaixa melhor') + ', pulado')
            continue
        melhor[placa] = int(usar.sum())
        escala = float(np.sqrt(abs(np.linalg.det(M[:2]))))
        tf = lambda x, y: (round(x * M[0, 0] + y * M[1, 0] + M[2, 0], 2),
                           round(x * M[0, 1] + y * M[1, 1] + M[2, 1], 2))

        malhas = {}
        for s in d['segments']:
            n = s.get('netName')
            if not n or s['layer'] > 16:
                continue
            a, b = tf(s['x1'], s['y1']), tf(s['x2'], s['y2'])
            malhas.setdefault(n, {'t': [], 'v': []})['t'].append(
                [s['layer'], *a, *b, round(s.get('width', 1) * escala, 2)])
        for v in d['vias']:
            n = v.get('netName')
            if not n:
                continue
            x, y = tf(v['x'], v['y'])
            malhas.setdefault(n, {'t': [], 'v': []})['v'].append(
                [x, y, round(v.get('diameter', 1) * escala, 2), v.get('layerA'), v.get('layerB')])
        contorno = [[*tf(s['x1'], s['y1']), *tf(s['x2'], s['y2'])] for s in d.get('outline', [])]
        contorno += [[*tf(s['x1'], s['y1']), *tf(s['x2'], s['y2'])] for s in d['segments'] if s['layer'] == 28]
        camadas = sorted({s['layer'] for s in d['segments'] if s['layer'] <= 16})
        saida = {'placa': placa, 'origem': os.path.basename(f), 'erro_medio': round(erro, 3),
                 'pinos_casados': len(src), 'camadas': camadas, 'contorno': contorno, 'malhas': malhas}
        destino = os.path.join(COBRE, placa + '.cobre.json')
        with open(destino, 'w', encoding='utf-8') as g:
            json.dump(saida, g, separators=(',', ':'))
        print(f'{os.path.basename(f)} -> {placa}: {len(src)} pinos casados, erro medio {erro:.3f}, '
              f'{len(malhas)} malhas, camadas {camadas}, {os.path.getsize(destino)/1e6:.1f} MB')


if __name__ == '__main__':
    main()
