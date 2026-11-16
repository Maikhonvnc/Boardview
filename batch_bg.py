# Lote: alinha a foto do PDF como background image de cada boardview XZZ.
# Uso: python batch_bg.py <raiz Drones> [--apply]
# Classes: A) n_blobs==n_ilhas -> composito por secao (Top=Bottom)
#          B) 2 blobs, 1 ilha  -> Top=blob1, Bottom=blob2 (cada um fitado no bbox)
#          C) 1 blob, 1 ilha   -> Top=Bottom=blob fitado
# Salvaguardas: PDFFilePath deve existir no .conf; aspect blob vs ilha < 12%;
# erros de parse (ex.: YiDianTong nao-XZZ) sao reportados e pulados.
import os, re, sys, subprocess, tempfile
from PIL import Image
from align_bg import (parse_outline_segments, connected_components, bbox,
                      group_islands, find_image_blobs, update_conf)

APPLY = '--apply' in sys.argv

def extract_pdf_image(pdf_path, tmpdir):
    subprocess.run(['pdfimages', '-j', '-png', pdf_path, os.path.join(tmpdir, 'im')],
                   check=True, capture_output=True)
    files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
    files = [(os.path.getsize(f), f) for f in files]
    if not files: raise RuntimeError('PDF sem imagens')
    files.sort(reverse=True)
    imgs = [f for sz, f in files if sz > files[0][0] * 0.2]  # descarta logos pequenos
    return sorted(imgs)

def aspect_ok(bl, ib, tol=0.12):
    ab = (bl[2]-bl[0]) / max(1, bl[3]-bl[1])
    ai = (ib[2]-ib[0]) / max(1, ib[3]-ib[1])
    return abs(ab - ai) / ai < tol

def fit_crop(src, bl, ib, W_u, H_u, ppu):
    cw, ch = int(round(W_u*ppu)), int(round(H_u*ppu))
    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    crop = src.crop((bl[0], bl[1], bl[2]+1, bl[3]+1))
    tw = max(1, int(round((ib[2]-ib[0])*ppu))); th = max(1, int(round((ib[3]-ib[1])*ppu)))
    canvas.paste(crop.resize((tw, th), Image.LANCZOS),
                 (int(round(ib[0]*ppu)), int(round((H_u-ib[3])*ppu))))
    return canvas

def side_keys(P, fname, sx, sy):
    return {f'{P}ImageFile': fname, f'{P}ImageOffsetX': 0, f'{P}ImageOffsetY': 0,
            f'{P}ImageScalingX': f"{sx:.6f}", f'{P}ImageScalingY': f"{sy:.6f}",
            f'{P}ImageMirrorX': 'false', f'{P}ImageMirrorY': 'false',
            f'{P}ImageTransparency': '0.000000'}

def process(pcb):
    folder = os.path.dirname(pcb)
    conf = re.sub(r'\.pcb$', '.conf', pcb, flags=re.I)
    if not os.path.exists(conf): return 'sem .conf'
    text = open(conf, encoding='utf-8', errors='replace').read()
    m = re.search(r'(?m)^PDFFilePath\s*=\s*(.+)$', text)
    if not m: return 'sem PDFFilePath'
    if re.search(r'(?m)^TopImageFile\s*=', text): return 'ja tem imagem (pulado)'
    pdf = os.path.join(folder, m.group(1).strip())
    if not os.path.exists(pdf): return 'PDF nao existe'

    segs = parse_outline_segments(pcb)
    comps = connected_components(segs)
    total = bbox([p for s in segs for p in s])
    W_u, H_u = total[2]-total[0], total[3]-total[1]

    with tempfile.TemporaryDirectory() as td:
        imgs = extract_pdf_image(pdf, td)
        # blobs: um por imagem embutida se houver varias; senao detecta na unica
        if len(imgs) == 1:
            img = Image.open(imgs[0]).convert('RGBA')
            blobs = sorted(find_image_blobs(img), key=lambda b: b[0])
            srcs = [(img, b) for b in blobs]
        else:
            srcs = []
            for f in imgs[:2]:
                im = Image.open(f).convert('RGBA')
                bs = find_image_blobs(im)
                if len(bs) != 1: return f'{len(imgs)} imagens, blobs ambiguos'
                srcs.append((im, bs[0]))

        islands = group_islands(comps, len(srcs))
        n_isl = len(islands) if islands else 1
        base = os.path.basename(re.sub(r'\.pcb$', '_bg', pcb, flags=re.I))

        if islands and len(srcs) == n_isl:  # classe A/C: composito por secao
            pairs = list(zip(sorted(islands, key=lambda i: bbox(i)[0]), srcs))
            for isl, (im, bl) in pairs:
                if not aspect_ok(bl, bbox(isl)): return 'aspecto nao confere (foto != placa?)'
            ppus = [v for isl, (im, bl) in pairs for v in
                    ((bl[2]-bl[0])/(bbox(isl)[2]-bbox(isl)[0]), (bl[3]-bl[1])/(bbox(isl)[3]-bbox(isl)[1]))]
            ppu = sum(ppus)/len(ppus)
            if not APPLY: return f'OK classe A/C ({n_isl} secao/oes, ppu {ppu:.2f})'
            cw, ch = int(round(W_u*ppu)), int(round(H_u*ppu))
            canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
            for isl, (im, bl) in pairs:
                ib = bbox(isl)
                crop = im.crop((bl[0], bl[1], bl[2]+1, bl[3]+1))
                tw = max(1, int(round((ib[2]-ib[0])*ppu))); th = max(1, int(round((ib[3]-ib[1])*ppu)))
                canvas.paste(crop.resize((tw, th), Image.LANCZOS),
                             (int(round(ib[0]*ppu)), int(round((H_u-ib[3])*ppu))))
            fname = base + '.png'
            canvas.save(os.path.join(folder, fname))
            sx, sy = W_u/canvas.width, H_u/canvas.height
            kv = {**side_keys('Top', fname, sx, sy), **side_keys('Bottom', fname, sx, sy)}
            update_conf(conf, kv)
            return f'APLICADO A/C: {fname} {canvas.width}x{canvas.height}px'

        if len(srcs) == 2 and n_isl == 1:  # classe B: top/bottom separados
            isl = bbox([p for s in segs for p in s])
            for im, bl in srcs:
                if not aspect_ok(bl, isl): return 'aspecto nao confere (foto != placa?)'
            if not APPLY: return 'OK classe B (top/bottom separados)'
            kv = {}
            for P, (im, bl) in zip(('Top', 'Bottom'), srcs):
                ppu = ((bl[2]-bl[0])/(isl[2]-isl[0]) + (bl[3]-bl[1])/(isl[3]-isl[1])) / 2
                canvas = fit_crop(im, bl, isl, W_u, H_u, ppu)
                fname = f'{base}_{P.lower()}.png'
                canvas.save(os.path.join(folder, fname))
                kv.update(side_keys(P, fname, W_u/canvas.width, H_u/canvas.height))
            update_conf(conf, kv)
            return 'APLICADO B: top/bottom separados'

        return f'sem casamento: {len(srcs)} foto(s) x {n_isl} ilha(s)'

def main():
    root = sys.argv[1]
    for dirpath, dirs, files in os.walk(root):
        if '__MACOSX' in dirpath: continue
        for f in sorted(files):
            if f.lower().endswith('.pcb') and not f.startswith('._'):
                pcb = os.path.join(dirpath, f)
                try:
                    r = process(pcb)
                except Exception as e:
                    r = f'ERRO: {type(e).__name__}: {e}'
                print(f'{f}  ->  {r}')

if __name__ == '__main__':
    main()
