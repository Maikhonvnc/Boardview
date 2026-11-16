# Indice por MODELO de drone para o digital_viewer.
#
# Cada pasta em DRONES e um modelo (DJI Mini3 Pro, DJI Mavic Air2, ...). Este script
# junta, por modelo: as placas que existem no viewer, os PDFs de referencia e as
# imagens da pasta. O viewer usa isso no menu do topo para pular entre as placas do
# MESMO drone e abrir os mapas/fotos dele sem passar pelo hub.
#
# Os arquivos ficam fora do repo, entao entram pela rota /_drones/ do servidor.py.
#
# Uso: python gen_modelos.py
import os, re, glob, json
from paths import DRONES, DV_BUILD
import foto_viewer as F

EXT_DOC = ('.pdf',)
EXT_IMG = ('.png', '.jpg', '.jpeg')


def url_drones(caminho):
    """Caminho absoluto dentro de DRONES -> URL servida pelo servidor.py."""
    rel = os.path.relpath(caminho, DRONES).replace(os.sep, '/')
    return '/_drones/' + '/'.join(re.sub(r'#', '%23', p).replace(' ', '%20')
                                  for p in rel.split('/'))


def placas_do_viewer():
    """assinatura do .bvr -> id da placa no viewer."""
    bj = os.path.join(DV_BUILD, 'boards.json')
    listados = {b['id']: b for b in json.load(open(bj, encoding='utf-8'))} \
        if os.path.exists(bj) else {}
    ofic = {}
    for b in sorted(glob.glob(os.path.join(DV_BUILD, 'DRONE', '*.bvr')), key=lambda p: len(p)):
        s = F.assinatura(b)
        if not s: continue
        sid = os.path.splitext(os.path.basename(b))[0]
        if s not in ofic or (sid in listados and ofic[s] not in listados):
            ofic[s] = sid
    return ofic, listados


def main():
    ofic, listados = placas_do_viewer()
    acervo = {os.path.splitext(os.path.basename(p))[0].lower(): p
              for p in glob.glob(os.path.join(F.DIGITALBOARD, 'boardview-bvr', '*.bvr'))}

    modelos = {}
    de_placa = {}          # id da placa -> modelo (p/ o viewer saber onde esta)
    for pasta in sorted(os.listdir(DRONES)):
        d = os.path.join(DRONES, pasta)
        if not os.path.isdir(d) or pasta.startswith('__') or pasta.startswith('.'):
            continue
        placas, arquivos = [], []
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if not os.path.isfile(p): continue
            ext = os.path.splitext(f)[1].lower()
            if ext == '.pcb':
                base = os.path.splitext(f)[0]
                if base.startswith('._'): continue
                bvr = acervo.get(base.lower())
                sid = ofic.get(F.assinatura(bvr)) if bvr else None
                placas.append({'nome': base, 'id': sid,
                               'foto': bool(F.foto_da_placa(p))})
                if sid: de_placa[sid] = pasta
            elif ext in EXT_DOC:
                arquivos.append({'nome': os.path.splitext(f)[0], 'tipo': 'pdf',
                                 'url': url_drones(p)})
            elif ext in EXT_IMG and not f.startswith('._'):
                arquivos.append({'nome': os.path.splitext(f)[0], 'tipo': 'img',
                                 'url': url_drones(p)})
        if placas or arquivos:
            modelos[pasta] = {'placas': placas, 'arquivos': arquivos}

    saida = {'modelos': modelos, 'de_placa': de_placa}
    destino = os.path.join(DV_BUILD, 'modelos.json')
    json.dump(saida, open(destino, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    n_p = sum(len(m['placas']) for m in modelos.values())
    n_a = sum(len(m['arquivos']) for m in modelos.values())
    print(f'{len(modelos)} modelos, {n_p} placas ({len(de_placa)} abrem no viewer), '
          f'{n_a} arquivos -> {destino}')


if __name__ == '__main__':
    main()
