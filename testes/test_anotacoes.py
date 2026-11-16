# Testes das anotacoes (classificacao/nomes) — armazenamento e sincronizacao.
#
#   python -m unittest discover testes -v
#
# NUNCA usam o dados/ real: BOARDVIEW_DADOS aponta para uma pasta temporaria ANTES de
# importar os modulos, e os servidores de teste sobem em portas proprias com dados
# temporarios tambem.
import os, sys, json, time, shutil, tempfile, unittest, subprocess, urllib.request, urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='bv_teste_')
os.environ['BOARDVIEW_DADOS'] = os.path.join(TMP, 'dados')
sys.path.insert(0, RAIZ)
import anotacoes as ANOT                                    # noqa: E402

PLACA = 'mine2'            # precisa existir em build/DRONE (o servidor confere)
P_CENTRAL, P_BANCADA = 8791, 8792


def req(porta, caminho, corpo=None):
    cab = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{porta}'} if corpo is not None else {}
    r = urllib.request.Request(f'http://127.0.0.1:{porta}{caminho}',
                               data=json.dumps(corpo).encode() if corpo is not None else None, headers=cab)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read())


class Armazenamento(unittest.TestCase):
    def setUp(self):
        self.semente_real = ANOT.SEMENTE
        ANOT.SEMENTE = os.path.join(TMP, 'semente')            # nao le o build/ real
        shutil.rmtree(os.environ['BOARDVIEW_DADOS'], ignore_errors=True)
        shutil.rmtree(ANOT.SEMENTE, ignore_errors=True)

    def tearDown(self):
        ANOT.SEMENTE = self.semente_real

    def test_validar(self):
        ok = lambda m: ANOT.validar(m)[0]
        self.assertTrue(ok(['tipos', 'N1', {'t': 'cap', 'v': '~1uF', 'por': 'Ana', 'em': '2026-11-16T10:00:00'}]))
        self.assertTrue(ok(['tipos', 'N1', None]))
        self.assertTrue(ok(['nomes', 'N1', 'H22 CPU']))
        self.assertTrue(ok(['malhas', '7P0_Net9', 'PMIC_VIN']))
        self.assertTrue(ok(['sugestoes', 'N1', None]))
        self.assertFalse(ok(['tipos', 'N1', {'t': 'batata'}]))
        self.assertFalse(ok(['tipos', 'N1', {'t': 'cap', 'extra': 1}]))
        self.assertFalse(ok(['sugestoes', 'N1', {'t': 'cap'}]))      # viewer nao escreve sugestao
        self.assertFalse(ok(['nomes', 'N1', '']))
        self.assertFalse(ok(['nomes', '../x', 'a']))
        self.assertFalse(ok(['outra', 'N1', 'a']))
        self.assertFalse(ok('lixo'))

    def test_gravar_ler_e_apagar(self):
        ANOT.gravar('p', [['tipos', 'N1', {'t': 'cap'}], ['nomes', 'N1', 'C1']])
        ANOT.gravar('p', [['tipos', 'N2', {'t': 'res'}], ['nomes', 'N1', None]])
        d = ANOT.ler('p')
        self.assertEqual(set(d['tipos']), {'N1', 'N2'})
        self.assertEqual(d['nomes'], {})
        self.assertEqual(set(d), set(ANOT.SECOES))
        self.assertTrue(os.path.exists(os.path.join(ANOT.pasta(), 'anteriores', 'p.json')))

    def test_semente_copiada_uma_vez(self):
        os.makedirs(ANOT.SEMENTE)
        with open(os.path.join(ANOT.SEMENTE, 'p.json'), 'w') as f:
            json.dump({'tipos': {'N1': {'t': 'cap'}}}, f)
        self.assertEqual(ANOT.ler('p')['tipos'], {'N1': {'t': 'cap'}})
        ANOT.gravar('p', [['tipos', 'N1', {'t': 'res'}]])
        # semente nova (pacote atualizado) NAO passa por cima do que esta em dados/
        with open(os.path.join(ANOT.SEMENTE, 'p.json'), 'w') as f:
            json.dump({'tipos': {'N1': {'t': 'ind'}}}, f)
        self.assertEqual(ANOT.ler('p')['tipos']['N1']['t'], 'res')

    def test_primeiro_contato_so_manda_o_que_o_central_nao_tem(self):
        ANOT.gravar('p', [['tipos', 'N1', {'t': 'cap'}], ['nomes', 'N1', 'C1'], ['malhas', 'Net9', 'VIN'],
                          ['tipos', 'N5', {'t': 'res', 'em': '2026-10-01T00:00:00'}],     # mais velho que o central
                          ['tipos', 'N6', {'t': 'res', 'em': '2026-11-10T00:00:00'}],     # mais novo que o central
                          ['nomes', 'N5', 'nome velho'],
                          ['sugestoes', 'N2', {'t': 'res', 'motivo': 'x'}]])
        ANOT.enfileirar('p', [['tipos', 'N3', {'t': 'ind'}]])
        central = {'tipos': {'N5': {'t': 'ind', 'em': '2026-11-01T00:00:00'},
                             'N6': {'t': 'ind', 'em': '2026-11-01T00:00:00'}},
                   'nomes': {'N5': 'nome do central'}, 'malhas': {}}
        self.assertTrue(ANOT.falta_primeiro_contato('p'))
        ANOT.primeiro_contato('p', central)
        chaves = [(m[0], m[1]) for m in ANOT.pendentes('p')]
        self.assertIn(('tipos', 'N1'), chaves)            # so existe aqui
        self.assertIn(('malhas', 'Net9'), chaves)
        self.assertIn(('tipos', 'N6'), chaves)            # aqui e mais recente
        self.assertNotIn(('tipos', 'N5'), chaves)         # o central e mais recente: nao passa por cima
        self.assertNotIn(('nomes', 'N5'), chaves)         # nome que ja existe la: o central vence
        self.assertNotIn(('sugestoes', 'N2'), chaves)
        self.assertEqual(chaves[-1], ('tipos', 'N3'))     # o que ja estava na fila vai por ultimo
        self.assertFalse(ANOT.falta_primeiro_contato('p'))
        self.assertEqual(ANOT.primeiro_contato('p', {}), 0)   # so uma vez


class BancadaCentral(unittest.TestCase):
    """Dois servidores de verdade: a bancada tem marcacoes de ANTES de conhecer o central."""

    @classmethod
    def setUpClass(cls):
        cls.dc, cls.db = os.path.join(TMP, 'central'), os.path.join(TMP, 'bancada')
        # a bancada ja tinha trabalho local; o central tem outra marcacao
        for pasta, tipos in ((cls.db, {'N70752': {'t': 'mosfet', 'por': 'Bancada'},
                                       'N70744': {'t': 'res', 'por': 'Bancada', 'em': '2026-10-01T00:00:00'}}),
                             (cls.dc, {'N71497': {'t': 'res', 'v': 'R010', 'por': 'Central'},
                                       'N70744': {'t': 'ind', 'por': 'Central', 'em': '2026-11-01T00:00:00'}})):
            os.makedirs(os.path.join(pasta, 'anotacoes'))
            with open(os.path.join(pasta, 'anotacoes', PLACA + '.json'), 'w') as f:
                json.dump({'tipos': tipos, 'nomes': {}, 'malhas': {}, 'sugestoes': {}}, f)
        base = dict(os.environ)
        base.pop('BOARDVIEW_CENTRAL', None)
        cls.procs = [
            subprocess.Popen([sys.executable, 'servidor.py', str(P_CENTRAL)], cwd=RAIZ,
                             env=dict(base, BOARDVIEW_DADOS=cls.dc),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            subprocess.Popen([sys.executable, 'servidor.py', str(P_BANCADA)], cwd=RAIZ,
                             env=dict(base, BOARDVIEW_DADOS=cls.db,
                                      BOARDVIEW_CENTRAL=f'http://127.0.0.1:{P_CENTRAL}'),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
        for porta in (P_CENTRAL, P_BANCADA):
            for _ in range(50):
                try:
                    req(porta, '/api/sync'); break
                except Exception:
                    time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.kill(); p.wait()

    def esperar(self, cond, seg=40):
        fim = time.time() + seg
        while time.time() < fim:
            if cond():
                return True
            time.sleep(0.5)
        return False

    def test_1_trabalho_local_antigo_sobe_e_nada_se_perde(self):
        b = req(P_BANCADA, f'/api/anotacoes/{PLACA}')
        self.assertEqual(b['origem'], 'central')
        self.assertIn('N70752', b['tipos'])            # o que a bancada ja tinha continua la
        self.assertIn('N71497', b['tipos'])            # e ela passou a ver o do central
        self.assertEqual(b['tipos']['N70744']['t'], 'ind')   # a correcao mais nova do central vale aqui
        self.assertTrue(self.esperar(lambda: 'N70752' in req(P_CENTRAL, f'/api/anotacoes/{PLACA}')['tipos']),
                        'a marcacao antiga da bancada nao chegou ao central')
        # o dado VELHO da bancada nao passou por cima da correcao do central
        self.assertEqual(req(P_CENTRAL, f'/api/anotacoes/{PLACA}')['tipos']['N70744']['t'], 'ind')

    def test_2_marcacao_nova_na_bancada_chega_ao_central(self):
        r = req(P_BANCADA, f'/api/anotacoes/{PLACA}',
                {'mudancas': [['tipos', 'N70739', {'t': 'ind', 'por': 'Bancada'}], ['nomes', 'N70739', 'L1']]})
        self.assertEqual((r['gravadas'], r['recusadas']), (2, []))
        self.assertTrue(self.esperar(lambda: req(P_CENTRAL, f'/api/anotacoes/{PLACA}')['nomes'].get('N70739') == 'L1'))

    def test_3_mudanca_invalida_nao_trava_as_boas(self):
        r = req(P_CENTRAL, f'/api/anotacoes/{PLACA}',
                {'mudancas': [['tipos', 'N70740', {'t': 'batata'}], ['tipos', 'N70741', {'t': 'ind'}]]})
        self.assertEqual(r['gravadas'], 1)
        self.assertEqual([x['i'] for x in r['recusadas']], [0])
        self.assertIn('N70741', req(P_CENTRAL, f'/api/anotacoes/{PLACA}')['tipos'])

    def test_4_placa_desconhecida_e_recusada(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            req(P_CENTRAL, '/api/anotacoes/nao-existe', {'mudancas': []})
        self.assertEqual(e.exception.code, 404)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
