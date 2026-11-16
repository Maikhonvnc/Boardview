# Anotacoes por placa (modo Classificar do viewer): tipo/valor de cada peca, nomes de
# peca, apelidos de malha e sugestoes do sugerir_placas.py.
#
#   dados/anotacoes/<placa>.json = {"tipos": {...}, "nomes": {...}, "malhas": {...},
#                                   "sugestoes": {...}}
#
# Fica em dados/ (como o caderno), NAO na arvore do programa: atualizar o programa por
# pacote nao pode apagar o que os tecnicos marcaram. O que existir em
# digital_viewer/build/anotacoes/ (lugar antigo, e o que vem no pacote) serve so de
# SEMENTE: e copiado uma vez, quando a placa ainda nao tem arquivo em dados/.
#
# Este modulo so guarda e valida; a rede (bancada <-> central) fica no servidor.py.
# Quem usa: servidor.py, sugerir_placas.py, exportar_placa.py.
import os, re, json, shutil, tempfile, threading
from paths import BV
import medicoes_db as MDB

SECOES = ('tipos', 'nomes', 'malhas', 'sugestoes')   # sugestoes: sugerir_placas.py (aceitar = virar tipo)
TIPOS = {'cap', 'res', 'ind', 'xtal', 'diodo', 'trans', 'mosfet', 'ci', 'con', 'chave', 'pad', 'vazio'}
SEMENTE = os.path.join(BV, 'digital_viewer', 'build', 'anotacoes')
_trava = threading.RLock()


def pasta():
    return os.path.join(MDB.DADOS, 'anotacoes')


def _arq(placa):
    return os.path.join(pasta(), placa + '.json')


def _pend(placa):
    """Na bancada: mudancas ainda nao entregues ao central."""
    return os.path.join(MDB.DADOS, 'anotacoes-pendentes', placa + '.json')


def ler_json(caminho, padrao):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar(alvo, obj, bonito=True):
    """Grava inteiro num temporario e troca: quem le nunca ve meio arquivo."""
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(alvo), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1 if bonito else None, sort_keys=bonito)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, alvo)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def validar(m):
    """[secao, chave, valor] vindo do viewer -> (True, None) ou (False, motivo)."""
    if not (isinstance(m, list) and len(m) == 3 and m[0] in SECOES and isinstance(m[1], str)):
        return False, 'mudanca precisa ser [secao, chave, valor]'
    secao, chave, valor = m
    if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,60}', chave):
        return False, 'chave invalida'
    if valor is None:
        return True, None
    if secao == 'sugestoes':
        # o viewer so APAGA sugestao (ao aceitar/recusar); quem escreve e o sugerir_placas.py
        return False, 'sugestao so se apaga pelo viewer'
    if secao == 'tipos':
        def txt(x, n):
            return x is None or (isinstance(x, str) and len(x) <= n and not re.search(r'[\x00-\x1f\x7f]', x))
        # por = tecnico que marcou; em = quando (ISO). Dois tecnicos podem discordar:
        # fica o ultimo, mas sempre se sabe de quem e.
        if not (isinstance(valor, dict) and valor.get('t') in TIPOS
                and set(valor) <= {'t', 'v', 'por', 'em'}
                and txt(valor.get('v'), 20) and txt(valor.get('por'), 40) and txt(valor.get('em'), 30)):
            return False, 'tipo invalido'
        return True, None
    if not isinstance(valor, str) or not (0 < len(valor) <= 60) or re.search(r'[\x00-\x1f\x7f]', valor):
        return False, 'nome invalido'
    return True, None


def aplicar(atual, muds):
    """Aplica [[secao, chave, valor|None], ...] num dict de anotacoes (e o devolve)."""
    for s in SECOES:
        if not isinstance(atual.get(s), dict):
            atual[s] = {}
    for secao, chave, valor in muds:
        if valor is None:
            atual[secao].pop(chave, None)
        else:
            atual[secao][chave] = valor
    return atual


def ler(placa):
    """Anotacoes da placa. Na primeira vez copia a semente (lugar antigo / pacote)."""
    with _trava:
        if not os.path.exists(_arq(placa)):
            semente = os.path.join(SEMENTE, placa + '.json')
            if os.path.exists(semente):
                os.makedirs(pasta(), exist_ok=True)
                shutil.copy2(semente, _arq(placa))
        dado = ler_json(_arq(placa), {})
        if not isinstance(dado, dict):
            dado = {}
        dado.pop('origem', None)
        return aplicar(dado, [])


def _guardar_anterior(placa):
    if os.path.exists(_arq(placa)):
        ant = os.path.join(pasta(), 'anteriores')
        os.makedirs(ant, exist_ok=True)
        shutil.copy2(_arq(placa), os.path.join(ant, placa + '.json'))


def gravar(placa, muds):
    """Aplica as mudancas no arquivo da placa (guardando a versao anterior)."""
    with _trava:
        atual = aplicar(ler(placa), muds)
        _guardar_anterior(placa)
        _gravar(_arq(placa), atual)
        return atual


def substituir(placa, dado):
    """Troca o arquivo inteiro (bancada guardando a copia do central)."""
    with _trava:
        limpo = aplicar({s: dict(dado[s]) for s in SECOES if isinstance(dado.get(s), dict)}, [])
        if limpo != ler(placa):
            _guardar_anterior(placa)
            _gravar(_arq(placa), limpo)
        return limpo


def placas():
    """Placas com anotacoes, em dados/ ou ainda so na semente."""
    nomes = set()
    for d in (pasta(), SEMENTE):
        if os.path.isdir(d):
            nomes.update(f[:-5] for f in os.listdir(d)
                         if f.endswith('.json') and not f.startswith('recusadas-'))
    return sorted(nomes)


# --- fila da bancada -----------------------------------------------------------------
def pendentes(placa):
    p = ler_json(_pend(placa), [])
    return p if isinstance(p, list) else []


def enfileirar(placa, muds):
    with _trava:
        _gravar(_pend(placa), pendentes(placa) + list(muds), bonito=False)


def entregues(placa, n):
    """Tira da fila as n primeiras (as que o central confirmou ou recusou)."""
    with _trava:
        _gravar(_pend(placa), pendentes(placa)[n:], bonito=False)


def placas_pendentes():
    d = os.path.dirname(_pend('x'))
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json')) if os.path.isdir(d) else []


def falta_primeiro_contato(placa):
    return not os.path.exists(os.path.join(pasta(), '.central-' + placa))


def primeiro_contato(placa, central):
    """Primeiro contato desta bancada com o central, JA com a resposta dele em maos.

    O que foi marcado AQUI antes de existir central nunca passou pela fila, e a copia do
    central nao pode apaga-lo. Mas mandar tudo tambem estaria errado: um PC instalado com
    dados velhos passaria por cima de correcao mais nova do central. Entao entra na fila so
    o que o central NAO tem; onde os dois tem a mesma peca (tipos), vale a marcacao mais
    recente (campo "em"); em nomes e apelidos que ja existem la, o central vence.
    Sugestoes ficam de fora (o central nao as aceita pela rede; refazem-se com o
    sugerir_placas.py). Acontece uma vez so (marca dados/anotacoes/.central-<placa>)."""
    with _trava:
        if not falta_primeiro_contato(placa):
            return 0
        local = ler(placa)
        muds = []
        for s in ('tipos', 'nomes', 'malhas'):
            la = central.get(s) if isinstance(central.get(s), dict) else {}
            for k, v in local[s].items():
                if k not in la:
                    muds.append([s, k, v])
                elif (s == 'tipos' and v != la[k] and isinstance(la[k], dict)
                      and str(v.get('em') or '') > str(la[k].get('em') or '')):
                    muds.append([s, k, v])
        if muds:
            _gravar(_pend(placa), muds + pendentes(placa), bonito=False)   # antes do que ja estava na fila
        os.makedirs(pasta(), exist_ok=True)
        open(os.path.join(pasta(), '.central-' + placa), 'w').close()
        return len(muds)


def recusar(placa, mud, motivo):
    """Mudanca que o central recusou: sai da fila mas fica registrada."""
    with _trava:
        arq = os.path.join(pasta(), 'recusadas-' + placa + '.json')
        _gravar(arq, (ler_json(arq, []) + [{'mudanca': mud, 'motivo': str(motivo)[:200]}])[-2000:])
