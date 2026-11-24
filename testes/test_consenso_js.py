# consenso.py e consenso_nuvem.js tem que dar a MESMA resposta (leituras sorteadas).
import os, sys, json, random, shutil, subprocess, unittest
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import consenso as C


@unittest.skipUnless(shutil.which('node'), 'sem node')
class Paridade(unittest.TestCase):
    def test_mesma_resposta(self):
        rnd = random.Random(7)
        ls = []
        for i in range(4000):
            tipo = rnd.choice(['tensao', 'diodo'])
            v = rnd.choice([None, 0.5, 0.51, 0.55, 1.8] if tipo == 'diodo' else [1.8, 1.82, 3.3, 3.39, 8.0])
            r = dict(uuid=f'u{i}', seq=i, evento='medida', fp=rnd.choice('ab'), alvo=f'Net{rnd.randrange(40)}',
                     tipo=tipo, papel=rnd.choice(['ref', 'ref', 'reparo']),
                     tecnico=rnd.choice(['João', 'joao ', 'Ana', 'Zé  Silva', 'ze silva']),
                     os=rnd.choice(['OS 1', '1', 'os-2', 'O.S. 3', 'OS nº 4', '4A', 'Osasco', None]),
                     valor='OL' if v is None else str(v), valor_num=v, categoria='OL' if v is None else 'num',
                     momento=rnd.choice(['estavel', 'estavel', 'boot']),
                     alimentacao=rnd.choice(['fonte', 'bateria']), cancela=None)
            if ls and rnd.random() < .1:
                r.update(evento='retira', cancela=rnd.choice(ls)['uuid'])
            ls.append(r)
        js = ("const C=require('./consenso_nuvem.js');let s='';process.stdin.setEncoding('utf8');"
              "process.stdin.on('data',d=>s+=d).on('end',()=>console.log(JSON.stringify(C.porPlaca(JSON.parse(s)))))")
        out = subprocess.run(['node', '-e', js], input=json.dumps(ls), capture_output=True, text=True,
                             encoding='utf-8', cwd=RAIZ, check=True).stdout
        self.assertEqual(json.loads(out), json.loads(json.dumps(C.por_placa(ls))))


if __name__ == '__main__':
    unittest.main()
