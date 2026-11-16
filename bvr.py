# Leitor UNICO do .bvr para os scripts em Python (pecas, pinos, malhas).
#
# Antes havia uma copia deste laco em importar_cobre.py, exportar_placa.py e
# sugerir_placas.py, cada uma lendo um subconjunto dos campos. O viewer (SCRIPT3.js /
# js/bvr.js) tem o leitor dele, em JavaScript, e o pipeline de fotos usa
# align_bvr.parse_bvr, que le outra coisa (os segmentos do contorno) — esses dois
# continuam separados de proposito.
#
#   pecas(caminho) -> [{'id': 'N70752', 'lado': 'T',
#                       'pinos': [{'pino': '1', 'x': 10.0, 'y': 20.0, 'raio': 8.0,
#                                  'malha': 'Net9'}, ...]}, ...]
#
# 'malha' e o nome CRU do arquivo (pode vir com prefixo de tensao, "7P0_Net9");
# canon() devolve a identidade sem o prefixo ("Net9"), que e a usada em malhas.json,
# nas anotacoes e nos .cobre.json.
import os, re
from paths import BV

DRONE = os.path.join(BV, 'digital_viewer', 'build', 'DRONE')
SEM_MALHA = {'GND', 'NC', 'UNCONNECTED', ''}       # nao sao malhas de sinal


def caminho(placa):
    return os.path.join(DRONE, placa + '.bvr')


def placas():
    return sorted(f[:-4] for f in os.listdir(DRONE) if f.endswith('.bvr'))


def canon(malha):
    """"7P0_Net9" / "3P0Net18" / "VCC_3P2V_Net65" -> "Net9" / "Net18" / "Net65"."""
    m = re.search(r'(Net\d+)$', malha or '')
    return m.group(1) if m else malha


def pecas(arquivo):
    """Todas as pecas do .bvr, na ordem do arquivo. Aceita o caminho ou o nome da placa."""
    if not os.path.exists(arquivo) and os.path.exists(caminho(arquivo)):
        arquivo = caminho(arquivo)
    out, peca, pino = [], None, None
    with open(arquivo, encoding='utf-8', errors='replace') as f:
        for ln in f:
            s = ln.split()
            if not s:
                continue
            c = s[0]
            if c == 'PART_NAME':
                peca = {'id': s[1] if len(s) > 1 else '', 'lado': None, 'pinos': []}
                pino = None
                out.append(peca)
            elif peca is None:
                continue
            elif c == 'PART_SIDE':
                peca['lado'] = s[1]
            elif c == 'PIN_ID':
                pino = {'pino': None, 'x': None, 'y': None, 'raio': None, 'malha': ''}
                peca['pinos'].append(pino)
            elif pino is None:
                continue
            elif c == 'PIN_NUMBER':
                pino['pino'] = s[1]
            elif c == 'PIN_ORIGIN':
                pino['x'], pino['y'] = float(s[1]), float(s[2])
            elif c == 'PIN_RADIUS':
                pino['raio'] = float(s[1])
            elif c == 'PIN_NET':
                pino['malha'] = ' '.join(s[1:])
    return out


def malhas(arquivo):
    """Conjunto das malhas cruas do arquivo."""
    return {q['malha'] for p in pecas(arquivo) for q in p['pinos']}
