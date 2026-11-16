# Bancada -> central: leitura que o central RECUSA nao pode passar por "central em dia".
import os, sys, tempfile, unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('BOARDVIEW_DADOS', tempfile.mkdtemp(prefix='bv_sync_'))
sys.path.insert(0, RAIZ)
import servidor as S                                        # noqa: E402


class Recusa(unittest.TestCase):
    def setUp(self):
        self.orig = (S._central, S.MDB.pendentes_sync, S.MDB.marcar_sync)
        self.marcado = []
        self.lotes = [[(1, {'uuid': 'a'}), (2, {'uuid': 'b'}), (3, {'uuid': 'c'})], []]
        S.MDB.pendentes_sync = lambda: self.lotes.pop(0)
        S.MDB.marcar_sync = self.marcado.append
        S._sync.update(recusadas=0, recusa_motivo=None)

    def tearDown(self):
        S._central, S.MDB.pendentes_sync, S.MDB.marcar_sync = self.orig

    def test_recusa_aparece_no_status(self):
        S._central = lambda *a, **k: {'aceitas': ['a'], 'rejeitadas': [
            {'uuid': 'b', 'motivo': 'fp desconhecido para esta placa'},
            {'uuid': 'c', 'motivo': 'fp desconhecido para esta placa'}]}
        self.assertEqual(S.sincronizar(), 3)
        self.assertEqual(self.marcado, [3])                 # o ponteiro anda (a fila nao trava)...
        self.assertEqual(S._sync['recusadas'], 2)           # ...mas a bancada sabe e mostra
        self.assertEqual(S._sync['recusa_motivo'], 'fp desconhecido para esta placa')

    def test_tudo_aceito_nao_acusa(self):
        S._central = lambda *a, **k: {'aceitas': ['a', 'b', 'c'], 'rejeitadas': []}
        S.sincronizar()
        self.assertEqual(S._sync['recusadas'], 0)

    def test_resposta_que_nao_confere_nao_anda(self):
        S._central = lambda *a, **k: {'aceitas': ['a'], 'rejeitadas': []}
        with self.assertRaises(ValueError):
            S.sincronizar()
        self.assertEqual(self.marcado, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
