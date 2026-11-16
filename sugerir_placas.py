# Sugere o tipo (e nome) das pecas de TODAS as placas pela topologia do .bvr — a mesma
# analise feita a mao no Mini 2. Nao e conferencia: vai para a secao "sugestoes" de
# dados/anotacoes/<placa>.json (anotacoes.py), que o modo Q (classificar.js) mostra como palpite com o
# motivo, e o tecnico aceita (Enter / a letra do tipo) ou corrige. Nao mexe no que ja
# foi conferido (tipos) nem nos nomes.
#
# Regras (cada sugestao leva o motivo):
#   indutor   2 pinos grandes, sem GND: um lado e no de chaveamento (poucos pinos, vai
#             num CI), o outro e um trilho (muitos pinos). O CI do lado de chaveamento
#             e o conversor (buck); se ele chaveia 3+ indutores, e o PMIC.
#   shunt     2 pinos grandes, sem GND, os dois lados no MESMO CI (medida de corrente)
#   MOSFET    5-10 pinos com 3+ pinos na mesma malha (dreno/fonte)
#   chave     4 pinos: 2 no GND e 2 na mesma malha (botao)
#   CPU       a peca com mais pinos
#   memoria   pecas iguais (mesmo n. de pinos, 60+) ligadas a um trilho do CPU
#
#   python sugerir_placas.py            todas as placas de build/DRONE
#   python sugerir_placas.py mine2      so uma
import os, sys, glob, math, collections
from paths import BV
import anotacoes as ANOT
import bvr as BVR

DRONE = os.path.join(BV, 'digital_viewer', 'build', 'DRONE')
FORA = {'GND', 'NC', 'UNCONNECTED', ''}


def pecas(caminho):
    """[{'id', 'p': [[x, y, malha], ...]}] — o formato enxuto que as regras abaixo usam."""
    return [{'id': p['id'], 'p': [[q['x'], q['y'], q['malha']] for q in p['pinos'] if q['x'] is not None]}
            for p in BVR.pecas(caminho)]


def sugerir(caminho):
    P = [p for p in pecas(caminho) if p['p']]
    grau = collections.Counter(q[2] for p in P for q in p['p'])
    donos = collections.defaultdict(set)                     # malha -> pecas
    for p in P:
        for q in p['p']:
            donos[q[2]].add(p['id'])
    npin = {p['id']: len(p['p']) for p in P}
    ci_na = lambda net, minimo=5: [d for d in donos[net] if npin[d] >= minimo]
    passos = sorted(math.dist(p['p'][0][:2], p['p'][1][:2]) for p in P if len(p['p']) == 2)
    if not passos:
        return {}
    grande = passos[int(len(passos) * 0.97)]                 # 2 pinos "grande" = 3% maiores

    sug, chaveia = {}, collections.defaultdict(list)          # ci -> [trilho]
    for p in P:
        ps, nets = p['p'], [q[2] for q in p['p']]
        n = len(ps)
        if n == 2 and 'GND' not in nets:
            if math.dist(ps[0][:2], ps[1][:2]) < grande:
                continue
            a, b = nets
            for sw, trilho in ((a, b), (b, a)):
                cis = ci_na(sw)
                if grau[sw] <= 6 and cis and grau[trilho] >= 10 and sw not in FORA and trilho not in FORA:
                    ci = max(cis, key=lambda d: npin[d])
                    sug[p['id']] = {'t': 'ind', 'nome': f'L {trilho}',
                                    'motivo': f'2 pinos grandes: chaveamento {sw} (no {ci}) -> trilho {trilho}'}
                    chaveia[ci].append(trilho)
                    break
            else:
                comum = set(ci_na(a, 10)) & set(ci_na(b, 10))
                if comum and a not in FORA and b not in FORA:
                    sug[p['id']] = {'t': 'res', 'v': 'shunt?',
                                    'motivo': f'2 pinos grandes entre {a} e {b}, os dois no CI {sorted(comum)[0]} (medida de corrente)'}
        elif 5 <= n <= 10:
            rep = collections.Counter(x for x in nets if x not in FORA).most_common(1)
            if rep and rep[0][1] >= 3:
                sug[p['id']] = {'t': 'mosfet', 'motivo': f'{n} pinos, {rep[0][1]} na malha {rep[0][0]}'}
        elif n == 4 and nets.count('GND') == 2:
            outros = [x for x in nets if x != 'GND']
            if outros[0] == outros[1] and outros[0] not in FORA:
                sug[p['id']] = {'t': 'chave', 'motivo': f'4 pinos: 2 no GND e 2 em {outros[0]} (botão)'}

    # botao e coisa de 1-3 por placa; dezenas com o mesmo padrao sao outra peca de 4 pinos
    chaves = [k for k, v in sug.items() if v['t'] == 'chave']
    if len(chaves) > 3:
        for k in chaves:
            del sug[k]

    for ci, trilhos in chaveia.items():
        if len(trilhos) >= 3:
            sug[ci] = {'t': 'ci', 'nome': 'PMIC?', 'motivo': f'chaveia {len(trilhos)} indutores: ' + ', '.join(trilhos)}
        else:
            sug[ci] = {'t': 'ci', 'nome': ('BUCK ' + '/'.join(trilhos))[:60],
                       'motivo': f'conversor: chaveia o indutor de {", ".join(trilhos)}'}

    cpu = max(P, key=lambda p: len(p['p']))
    if len(cpu['p']) >= 100:
        sug[cpu['id']] = {'t': 'ci', 'nome': 'CPU?', 'motivo': f'a peça com mais pinos ({len(cpu["p"])})'}
        trilhos_cpu = {q[2] for q in cpu['p'] if q[2] not in FORA and grau[q[2]] >= 20}
        iguais = collections.defaultdict(list)
        for p in P:
            if p is not cpu and len(p['p']) >= 60 and p['id'] not in sug:
                iguais[len(p['p'])].append(p)
        k = 0
        for qtd, grupo in iguais.items():
            if 2 <= len(grupo) <= 4 and all(trilhos_cpu & {q[2] for q in g['p']} for g in grupo):
                for g in grupo:
                    k += 1
                    sug[g['id']] = {'t': 'ci', 'nome': f'memória? {k}',
                                    'motivo': f'{len(grupo)} peças iguais de {qtd} pinos no trilho do CPU'}
    for v in sug.values():
        v['motivo'] = v['motivo'][:200]
    return sug


def main():
    alvos = sys.argv[1:] or [os.path.basename(f)[:-4] for f in sorted(glob.glob(os.path.join(DRONE, '*.bvr')))]
    for placa in alvos:
        sug = sugerir(os.path.join(DRONE, placa + '.bvr'))
        atual = ANOT.ler(placa)
        sug = {k: v for k, v in sug.items() if k not in atual['tipos']}           # ja conferido: nao sugere
        ANOT.gravar(placa, [['sugestoes', k, None] for k in atual['sugestoes']] +
                    [['sugestoes', k, v] for k, v in sug.items()])
        c = collections.Counter(v['t'] for v in sug.values())
        print(f'{placa:40} {len(sug):4} sugestões  ' + ' '.join(f'{t}:{n}' for t, n in c.most_common()))


if __name__ == '__main__':
    main()
