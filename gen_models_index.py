# Gera Boardview/boards/_models.js = window.MODELS { "<pasta modelo>": ["<base>", ...] }
# usado pelo viewer.html?model=<pasta> para abrir todas as placas do modelo lado a lado.
import os, re, json, glob
from paths import BV, DRONES

BOARDS = os.path.join(BV, 'boards')

models = {}
for folder in sorted(os.listdir(DRONES)):
    fdir = os.path.join(DRONES, folder)
    if not os.path.isdir(fdir) or '__MACOSX' in folder:
        continue
    names = []
    for pcb in sorted(glob.glob(os.path.join(fdir, '*.pcb'))):
        if os.path.basename(pcb).startswith('._'):
            continue
        base = re.sub(r'\.pcb$', '', os.path.basename(pcb))
        if os.path.exists(os.path.join(BOARDS, base + '.js')):
            names.append(base)
    if names:
        models[folder] = names

os.makedirs(BOARDS, exist_ok=True)
with open(os.path.join(BOARDS, '_models.js'), 'w', encoding='utf-8') as f:
    f.write('window.MODELS=' + json.dumps(models, ensure_ascii=False) + ';')
print(f"_models.js: {len(models)} modelos, {sum(len(v) for v in models.values())} placas")
for m, v in models.items():
    print(f"  {m}: {len(v)}")
