# Regra do consenso (consenso.py): maioria e a base, tecnico/OS normalizados.
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import consenso as C

_seq = [0]


def lin(valor, tec='Ana', os_='1', papel='ref', evento='medida', **kw):
    _seq[0] += 1
    num = None if valor == 'OL' else float(valor)
    return dict(uuid=f'u{_seq[0]}', seq=_seq[0], evento=evento, papel=papel, tecnico=tec, os=os_,
                valor=str(valor), valor_num=num, categoria='OL' if num is None else 'num', **kw)


class Regra(unittest.TestCase):
    def test_um_voto(self):
        self.assertEqual(C.calcular('tensao', [lin(3.3)])['estado'], 'nao_confirmado')

    def test_dez_contra_um(self):
        ls = [lin(3.3, tec=f't{i}', os_=str(i)) for i in range(10)] + [lin(1.8, tec='x', os_='99')]
        r = C.calcular('tensao', ls)
        self.assertEqual(r['estado'], 'validado')
        self.assertEqual(r['fora'], ['1.8'])

    def test_dez_contra_dois_maioria_e_a_base(self):
        ls = [lin(3.3, tec=f't{i}', os_=str(i)) for i in range(10)] + \
             [lin(1.8, tec='x', os_='98'), lin(1.8, tec='y', os_='99')]
        r = C.calcular('tensao', ls)
        self.assertEqual(r['estado'], 'validado')
        self.assertAlmostEqual(r['valor'], 3.3)
        self.assertEqual(sorted(r['fora']), ['1.8', '1.8'])

    def test_empate_e_divergente(self):
        ls = [lin(3.3, tec='a', os_='1'), lin(3.3, tec='b', os_='2'),
              lin(1.8, tec='c', os_='3'), lin(1.8, tec='d', os_='4')]
        r = C.calcular('tensao', ls)
        self.assertEqual(r['estado'], 'divergente')
        self.assertNotIn('valor', r)

    def test_validado_precisa_de_duas_os(self):
        ls = [lin(3.3, tec=t, os_='7') for t in 'abc']
        self.assertEqual(C.calcular('tensao', ls)['estado'], 'confirmado')

    def test_so_ref_com_os_e_sem_boot(self):
        ls = [lin(3.3, papel='reparo'), lin(3.3, os_=''), lin(3.3, momento='boot')]
        self.assertEqual(C.calcular('tensao', ls)['estado'], 'sem_dados')

    def test_retira_cancela(self):
        a = lin(3.3)
        b = dict(lin(0), evento='retira', cancela=a['uuid'])
        self.assertEqual(C.calcular('tensao', [a, b])['estado'], 'sem_dados')


class Normalizacao(unittest.TestCase):
    def test_mesma_pessoa_mesma_os_e_um_voto(self):
        ls = [lin(3.3, tec='João', os_='OS 123'), lin(3.3, tec='joao ', os_='123'),
              lin(3.3, tec='JOAO', os_='os-123')]
        r = C.calcular('tensao', ls)
        self.assertEqual((r['n_votos'], r['n_os'], r['estado']), (1, 1, 'nao_confirmado'))

    def test_chave_os(self):
        for entrada, esperado in [('OS 123', '123'), ('O.S. 77', '77'), ('OS nº 45A', '45a'),
                                  ('123A', '123a'), ('Osasco1', 'osasco1'), ('', '')]:
            self.assertEqual(C.chave_os(entrada), esperado, entrada)

    def test_chave_tecnico(self):
        self.assertEqual(C.chave_tecnico('  João   Silva '), 'joao silva')


if __name__ == '__main__':
    unittest.main(verbosity=2)
