# Gera "<Modelo> - JUNTO.brd" em cada pasta de drone com >1 placa (todas lado a
# lado, abre no OBV). Nomeia tags automaticas. Escreve tambem legenda .txt.
import os, sys, glob, subprocess, re
from paths import BV, DRONES

MERGE = os.path.join(BV, 'merge_boards.py')

for folder in sorted(os.listdir(DRONES)):
    fdir = os.path.join(DRONES, folder)
    if not os.path.isdir(fdir) or '__MACOSX' in folder:
        continue
    pcbs = sorted(p for p in glob.glob(os.path.join(fdir, '*.pcb'))
                  if not os.path.basename(p).startswith('._')
                  and 'yidiantong' not in os.path.basename(p).lower())  # dedup views alternativas
    if len(pcbs) < 2:
        continue
    out = os.path.join(fdir, folder + ' - JUNTO.brd')
    r = subprocess.run([sys.executable, MERGE, out] + pcbs, capture_output=True, text=True)
    print(r.stdout.strip().split('\n')[0] if r.stdout else ('ERRO ' + folder + ': ' + r.stderr[:200]))
