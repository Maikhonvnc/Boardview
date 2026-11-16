# Exporta UMA placa num JSON so, legivel por outra ferramenta (animacao, IA, planilha):
# componentes com nome dado, tipo, valor, posicao e pinos (malha crua + apelido), e as
# malhas com apelido e tensao medida (caderno). Junta o que esta espalhado em:
#   build/DRONE/<placa>.bvr            pecas, pinos, malhas (fonte)
#   build/nomes.json, build/malhas.json  nomes/apelidos antigos
#   dados/anotacoes/<placa>.json       classificacao, nomes e apelidos (modo Q) — vence
#   dados/medicoes.sqlite3             tensoes/diodos medidos (so leitura)
#
#   python exportar_placa.py mine2            -> exportados/mine2.json
import os, re, sys, json, sqlite3
from paths import BV
import anotacoes as ANOT
import bvr as BVR

VIEW = os.path.join(BV, 'digital_viewer', 'build')


def achar(d, malha):
    return d.get(malha) or d.get(BVR.canon(malha))


def ler(caminho, padrao):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def pecas_bvr(placa):
    return [{'id': p['id'], 'lado': p['lado'],
             'pinos': [{'pino': q['pino'], 'x': q['x'], 'y': q['y'], 'malha': q['malha'] or None}
                       for q in p['pinos'] if q['x'] is not None]}
            for p in BVR.pecas(placa)]


def main():
    placa = sys.argv[1] if len(sys.argv) > 1 else 'mine2'
    anot = ANOT.ler(placa)
    nomes = dict(ler(os.path.join(VIEW, 'nomes.json'), {}).get(placa, {}), **anot.get('nomes', {}))
    apel = dict(ler(os.path.join(VIEW, 'malhas.json'), {}).get(placa, {}), **anot.get('malhas', {}))
    tipos = anot.get('tipos', {})

    tensoes = {}
    banco = os.path.join(BV, 'dados', 'medicoes.sqlite3')
    if os.path.exists(banco):
        c = sqlite3.connect('file:' + banco.replace('\\', '/') + '?mode=ro', uri=True)
        canceladas = {u for (u,) in c.execute("select cancela from leitura where placa=? and evento='retira'", (placa,))}
        for uuid, alvo, tipo, papel, valor in c.execute(
                "select uuid, alvo, tipo, papel, valor from leitura where placa=? and evento='medida' order by seq", (placa,)):
            if uuid not in canceladas:
                tensoes.setdefault(alvo, {})[f'{tipo}_{papel}'] = valor   # a mais recente vence

    comps, malhas = [], {}
    for p in pecas_bvr(placa):
        xs = [q['x'] for q in p['pinos']] or [0]
        ys = [q['y'] for q in p['pinos']] or [0]
        t = tipos.get(p['id'], {})
        comps.append({
            'id': p['id'], 'nome': nomes.get(p['id'], p['id']),
            'tipo': t.get('t'), 'valor': t.get('v'), 'marcado_por': t.get('por'),
            'lado': p.get('lado'),
            'centro': [round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2)],
            'caixa': [min(xs), min(ys), max(xs), max(ys)],
            'pinos': [{'pino': q['pino'], 'x': q['x'], 'y': q['y'], 'malha': q.get('malha'),
                       'apelido': achar(apel, q.get('malha'))} for q in p['pinos']],
        })
        for q in p['pinos']:
            m = q.get('malha')
            if m and m not in ('GND', 'NC', 'UNCONNECTED'):
                malhas.setdefault(m, {'malha': m, 'apelido': achar(apel, m), 'medido': achar(tensoes, m), 'pecas': set()})
                malhas[m]['pecas'].add(nomes.get(p['id'], p['id']))
    for m in malhas.values():
        m['pecas'] = sorted(m['pecas'])

    saida = {'placa': placa, 'unidade_coordenadas': 'unidades do .bvr (mesmas do viewer)',
             'legenda_tipos': {'cap': 'capacitor', 'res': 'resistor', 'ind': 'indutor', 'xtal': 'cristal/oscilador',
                               'diodo': 'diodo', 'trans': 'transistor', 'mosfet': 'MOSFET', 'ci': 'CI',
                               'con': 'conector', 'chave': 'chave/botao', 'pad': 'pad de teste',
                               'vazio': 'posicao sem componente', 'null': 'nao conferido'},
             'componentes': comps,
             'malhas': sorted(malhas.values(), key=lambda m: -len(m['pecas']))}
    pasta = os.path.join(BV, 'exportados')
    os.makedirs(pasta, exist_ok=True)
    alvo = os.path.join(pasta, placa + '.json')
    with open(alvo, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    nomeados = sum(1 for c in comps if c['nome'] != c['id'])
    print(f'{alvo}\n  {len(comps)} componentes ({nomeados} com nome, {sum(1 for c in comps if c["tipo"])} com tipo), '
          f'{len(malhas)} malhas ({sum(1 for m in malhas.values() if m["apelido"])} com apelido, '
          f'{sum(1 for m in malhas.values() if m["medido"])} medidas)')


if __name__ == '__main__':
    main()
