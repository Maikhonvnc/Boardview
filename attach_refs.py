# Junta PDFs de referencia DigitalBoard (voltage/RF/layout/schematic/charger) por
# placa e aponta o PDF bridge (PDFFilePath) do .conf. Foto continua como fundo.
import os, re, subprocess
from paths import BV, DRONES, REFERENCIAS

REF = REFERENCIAS

# (pasta, .pcb alvo, tag saida, [refs ordenadas sem .pdf])
JOBS = [
    ('DJI Mini3 Pro', 'DJI mini3 Pro-PP002663 PCB layer.pcb', 'MINI3PRO',
     ['MINI3PRO-VOLTAGE','MINI3PRO-2.4GHZ','MINI3PRO-5.8GHZ','MINI3PRO-LAYOUT',
      'MINI3PRO-USB_C','MINI3PRO-SD_CARD','MINI3PRO-eMMC']),
    ('DJI Mini3', 'Mini3-PP003401.01 PCB layer.pcb', 'MINI3', ['MINI3-5.8GHZ']),
    ('DJI Mavic Air2', 'DJI Air2 PP002106.01 PCB layer.pcb', 'AIR2',
     ['AIR2-2.4GHZ','AIR2-5GHZ','AIR2-LAYOUT','AIR2-OPT3101','AIR2-ACT8846QM',
      'AIR2-EMMC','AIR2-SD-CARD','AIR2-USB-C','DJI-air2']),
    ('DJI Mavic Air2S', 'Air 2S-PP002283 PCB Layer.pcb', 'AIR2S', ['DJI_AIR_2s']),
    ('DJI Mini1', 'DJI Mini1 PP001324.05 PCB layer.pcb', 'MINI1', ['DJI_MINI_1']),
    ('DJI Mavic Air3S', 'Air3S-PP004417.06 PCB layer.pcb', 'AIR3S',
     ['AIR3S_ANT_DB_compressed','AIR3S_FPC_J8_compressed','AIR3S_SD_CARD_compressed','DJIAIR3S_SCH']),
    ('DJI RC Plus', 'RC Plus-PP001927.07 PCB layer.pcb', 'RCPLUS',
     ['DJI_RCPlusRepair_Training','DJI_D12000I-GUIDE','DJI_D12000I-INFO','DJI_D12000I_DIAGRAM_BLOCK']),
    ('DJI RC Pro', 'RC Pro-PP002433.06 PCB layer.pcb', 'RCPRO',
     ['DJI_D12000I-GUIDE','DJI_D12000I-INFO','DJI_D12000I_DIAGRAM_BLOCK']),
]

def set_pdf(conf, fname):
    text = open(conf, encoding='utf-8', errors='replace').read() if os.path.exists(conf) else ''
    line = f'PDFFilePath = {fname}'
    if re.search(r'(?m)^PDFFilePath\s*=.*$', text):
        text = re.sub(r'(?m)^PDFFilePath\s*=.*$', line, text)
    else:
        text = line + '\n' + text
    open(conf, 'w', encoding='utf-8', newline='\n').write(text)

for folder, pcb, tag, refs in JOBS:
    fdir = os.path.join(DRONES, folder)
    if not os.path.isdir(fdir):
        print(f'{tag}: pasta ausente {folder}'); continue
    parts = [os.path.join(REF, r + '.pdf') for r in refs]
    parts = [p for p in parts if os.path.exists(p)]
    if not parts:
        print(f'{tag}: nenhum ref encontrado'); continue
    out_name = f'{tag} - DigitalBoard (tensao+RF+esquematico).pdf'
    out_path = os.path.join(fdir, out_name)
    if len(parts) == 1:
        subprocess.run(['cp', parts[0], out_path], check=True)
    else:
        subprocess.run(['pdfunite'] + parts + [out_path], check=True)
    conf = os.path.join(fdir, re.sub(r'\.pcb$', '.conf', pcb, flags=re.I))
    set_pdf(conf, out_name)
    npg = subprocess.run(['pdfinfo', out_path], capture_output=True, text=True).stdout
    m = re.search(r'Pages:\s+(\d+)', npg)
    print(f'{tag}: {len(parts)} refs -> {m.group(1) if m else "?"} pg -> {out_name}')
