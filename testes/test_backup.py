# Backup do central: banco + anotacoes. So pastas temporarias.
import os, sys, json, shutil, tempfile, unittest, zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import medicoes_db as MDB                                   # noqa: E402


class Backup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='bv_bkp_')
        self.dados, self.dest = os.path.join(self.tmp, 'dados'), os.path.join(self.tmp, 'bkp')
        os.makedirs(os.path.join(self.dados, 'anotacoes', 'anteriores'))
        with open(os.path.join(self.dados, 'anotacoes', 'p.json'), 'w', encoding='utf-8') as f:
            json.dump({'tipos': {'N1': {'t': 'cap'}}, 'nomes': {'N1': 'Botão'}}, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_banco_e_anotacoes(self):
        arq, r = MDB.backup(self.dest, 30, self.dados)
        self.assertTrue(os.path.exists(arq))
        self.assertEqual(r['anotacoes'], 1)
        zips = [f for f in os.listdir(self.dest) if f.startswith('anotacoes-')]
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(os.path.join(self.dest, zips[0])) as z:
            self.assertEqual(z.namelist(), ['p.json'])          # so os .json, sem subpastas
            self.assertEqual(json.loads(z.read('p.json').decode('utf-8'))['nomes']['N1'], 'Botão')

    def test_json_quebrado_nao_vira_backup(self):
        with open(os.path.join(self.dados, 'anotacoes', 'ruim.json'), 'w') as f:
            f.write('{quebrado')
        with self.assertRaises(ValueError):
            MDB.backup(self.dest, 30, self.dados)
        self.assertEqual([f for f in os.listdir(self.dest) if f.startswith('anotacoes-')], [])

    def test_sem_anotacoes_nao_falha(self):
        shutil.rmtree(os.path.join(self.dados, 'anotacoes'))
        _, r = MDB.backup(self.dest, 30, self.dados)
        self.assertEqual(r['anotacoes'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
