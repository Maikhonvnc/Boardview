# Regra de consenso das medicoes ("validado por N") — fase 2 da plataforma.
#
# E o UNICO lugar da regra: o servidor, o viewer e o Grafana leem o que sai daqui.
# Decisoes do dono (PLATAFORMA.md):
#   - Voto = (tecnico, OS). O mesmo tecnico conta de novo numa placa de outro cliente
#     (outra OS); medir de novo a mesma placa substitui o voto anterior.
#   - So vota leitura de placa BOA (papel 'ref'), com OS, nao cancelada por 'retira'.
#     Tensao medida no 'boot' e so informativa: nao vota.
#   - Valores proximos formam um grupo (tolerancia abaixo). OL e um grupo proprio.
#   - Tecnico e OS entram no voto NORMALIZADOS (chave_tecnico/chave_os): "Joao" e
#     "joão", "OS 123" e "123" sao a mesma pessoa / a mesma placa. O banco guarda o
#     texto como foi digitado (append-only); so a chave do voto e normalizada.
#   - O grupo com MAIS votos e a base (decisao do dono, 2026-11-17): se 10 placas dao x
#     e uma dita "boa" da y, o mais provavel e a "boa" nao estar boa. A minoria aparece
#     em 'fora', nao derruba o ponto para divergente.
#   - Estados:
#       sem_dados       nenhum voto
#       nao_confirmado  1 voto
#       confirmado      grupo principal com >= 2 votos e MAIS votos que qualquer outro
#       validado        confirmado + >= 3 votos no grupo principal, em >= 2 OS
#       divergente      empate no primeiro lugar. Mostra os grupos, nunca uma media.
# Parametros no topo; testes em teste_consenso.py (scratchpad) cobrem cada estado.

TOL_DIODO = (0.025, 0.04)     # (absoluta em V, relativa) — o maior dos dois
TOL_TENSAO = (0.05, 0.03)
MIN_CONFIRMADO = 2
MIN_VALIDADO = 3
MIN_OS_VALIDADO = 2


def chave_tecnico(t):
    """'  João  Silva' -> 'joao silva' (sem acento, minusculo, espacos simples)."""
    import unicodedata
    t = unicodedata.normalize('NFKD', str(t or ''))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return ' '.join(t.casefold().split())


def chave_os(o):
    """'OS 123' / 'os-123' / '123' -> '123'. Tira o prefixo OS e a pontuacao; letras
    do meio ficam ('123A' != '123')."""
    import re
    o = chave_tecnico(o)
    o = re.sub(r'^o\.?s\.?(?![a-z])[\s.:#°-]*(no?(?![a-z])[\s.:#°-]*)?', '', o)   # "OS", "O.S.", "OS nº"
    return re.sub(r'[^0-9a-z]', '', o)


def _tol(tipo, v):
    absol, rel = TOL_DIODO if tipo == 'diodo' else TOL_TENSAO
    return max(absol, abs(v) * rel)


def votos(linhas):
    """Das linhas cruas de UM ponto (mesma placa/fp, alvo, tipo e condicao) para a lista
    de votos validos: [{tecnico, os, valor, valor_num, categoria, seq}].

    Ordem pelo seq (ordem de chegada no banco), nunca pelo relogio do PC."""
    linhas = sorted(linhas, key=lambda r: r['seq'])
    canceladas = {r['cancela'] for r in linhas if r['evento'] == 'retira' and r.get('cancela')}
    ultimo = {}
    for r in linhas:
        if r['evento'] != 'medida' or r['uuid'] in canceladas:
            continue
        if r['papel'] != 'ref' or not chave_os(r.get('os')):
            continue
        if r.get('momento') == 'boot':
            continue
        ultimo[(chave_tecnico(r['tecnico']), chave_os(r['os']))] = r   # a ultima do par vale
    return [{'tecnico': chave_tecnico(r['tecnico']), 'os': chave_os(r['os']), 'valor': r['valor'],
             'valor_num': r['valor_num'], 'categoria': r['categoria'], 'seq': r['seq']}
            for r in ultimo.values()]


def _grupos(tipo, vs):
    """Agrupa votos: OL junto; numeros ordenados, corte onde o vizinho passa da tolerancia."""
    grupos = []
    ol = [v for v in vs if v['categoria'] == 'OL']
    if ol:
        grupos.append({'tipo': 'OL', 'votos': ol})
    nums = sorted((v for v in vs if v['categoria'] == 'num'), key=lambda v: v['valor_num'])
    atual = []
    for v in nums:
        if atual and v['valor_num'] - atual[-1]['valor_num'] > _tol(tipo, atual[-1]['valor_num']):
            grupos.append({'tipo': 'num', 'votos': atual})
            atual = []
        atual.append(v)
    if atual:
        grupos.append({'tipo': 'num', 'votos': atual})
    for g in grupos:
        xs = sorted(v['valor_num'] for v in g['votos'] if v['valor_num'] is not None)
        g['n'] = len(g['votos'])
        g['os'] = sorted({v['os'] for v in g['votos']})
        g['tecnicos'] = sorted({v['tecnico'] for v in g['votos']})
        if xs:
            meio = len(xs) // 2
            g['mediana'] = xs[meio] if len(xs) % 2 else (xs[meio - 1] + xs[meio]) / 2
            g['min'], g['max'] = xs[0], xs[-1]
        else:
            g['mediana'] = g['min'] = g['max'] = None
    grupos.sort(key=lambda g: -g['n'])
    return grupos


def calcular(tipo, linhas):
    """Consenso de um ponto. Devolve {estado, valor, faixa, n_votos, n_os, grupos, fora}."""
    vs = votos(linhas)
    if not vs:
        return {'estado': 'sem_dados', 'n_votos': 0, 'n_os': 0, 'grupos': []}
    grupos = _grupos(tipo, vs)
    total = len(vs)
    principal = grupos[0]
    outros = grupos[1:]
    empate = bool(outros) and outros[0]['n'] == principal['n']

    if total == 1:
        estado = 'nao_confirmado'
    elif empate:
        estado = 'divergente'
    elif principal['n'] >= MIN_CONFIRMADO:
        estado = 'confirmado'
        if principal['n'] >= MIN_VALIDADO and len(principal['os']) >= MIN_OS_VALIDADO:
            estado = 'validado'
    else:
        estado = 'nao_confirmado'

    def resumo(g):
        return {'valor': 'OL' if g['tipo'] == 'OL' else g['mediana'], 'n': g['n'],
                'min': g['min'], 'max': g['max'], 'os': g['os'], 'tecnicos': g['tecnicos']}

    r = {'estado': estado, 'n_votos': total, 'n_os': len({v['os'] for v in vs}),
         'grupos': [resumo(g) for g in grupos]}
    if estado in ('confirmado', 'validado', 'nao_confirmado'):
        r['valor'] = 'OL' if principal['tipo'] == 'OL' else principal['mediana']
        r['faixa'] = [principal['min'], principal['max']]
        r['fora'] = [v['valor'] for g in outros for v in g['votos']]
    return r


def condicao(linha):
    """Chave da condicao de medida: tensao separa fonte x bateria (o 'boot' nao vota)."""
    return (linha.get('alimentacao') or '') if linha['tipo'] == 'tensao' else ''


def por_placa(linhas):
    """Consenso de todos os pontos de uma placa: {fp: {alvo: {tipo: {condicao: resultado}}}}.
    'linhas' = todas as leituras da placa (de qualquer papel; votos() filtra)."""
    pontos = {}
    for r in linhas:
        pontos.setdefault((r['fp'], r['alvo'], r['tipo'], condicao(r)), []).append(r)
    saida = {}
    for (fp, alvo, tipo, cond), ls in pontos.items():
        c = calcular(tipo, ls)
        if c['estado'] == 'sem_dados':
            continue
        saida.setdefault(fp, {}).setdefault(alvo, {}).setdefault(tipo, {})[cond] = c
    return saida
