# Orientacao automatica por vista: casa cada blob da foto com sua ilha do outline
# testando flips (V/H) e troca de atribuicao, pelo perfil de vao (span) da silhueta.
# Uso: python auto_orient.py <pcb> [--apply]   (le PDFFilePath do .conf)
import os, re, sys, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw
from align_bg import (parse_outline_segments, connected_components, bbox,
                      group_islands, find_image_blobs, update_conf)

N = 96  # resolucao dos perfis

def island_mask(segs, ib):
    # rasteriza os segmentos da ilha num canvas N x N (bbox normalizado)
    im = Image.new('L', (N, N), 0)
    dr = ImageDraw.Draw(im)
    w = max(1, ib[2]-ib[0]); h = max(1, ib[3]-ib[1])
    for a, b in segs:
        pa = ((a[0]-ib[0])/w*(N-1), (N-1) - (a[1]-ib[1])/h*(N-1))
        pb = ((b[0]-ib[0])/w*(N-1), (N-1) - (b[1]-ib[1])/h*(N-1))
        dr.line([pa, pb], fill=255, width=1)
    return np.asarray(im) > 0

def span_profiles(mask):
    # para cada linha/coluna: extensao entre o primeiro e o ultimo pixel ativo
    def spans(m):
        out = np.zeros(m.shape[0])
        for i in range(m.shape[0]):
            idx = np.where(m[i])[0]
            if len(idx): out[i] = idx[-1] - idx[0]
        return out / (m.shape[1] - 1)
    return spans(mask), spans(mask.T)  # (por linha, por coluna)

def blob_mask_of(img_rgb, bl):
    a = np.asarray(img_rgb).astype(int)
    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    m = np.abs(a - bg).sum(axis=2) > 60
    sub = m[bl[1]:bl[3]+1, bl[0]:bl[2]+1]
    im = Image.fromarray((sub*255).astype(np.uint8)).resize((N, N), Image.BILINEAR)
    return np.asarray(im) > 127

def orient_error(isl_prof, blob_mask, flipH, flipV):
    m = blob_mask
    if flipH: m = m[:, ::-1]
    if flipV: m = m[::-1, :]
    r, c = span_profiles(m)
    return float(np.abs(r - isl_prof[0]).mean() + np.abs(c - isl_prof[1]).mean())

def main():
    pcb = sys.argv[1]
    apply_ = '--apply' in sys.argv
    folder = os.path.dirname(pcb)
    conf = re.sub(r'\.pcb$', '.conf', pcb, flags=re.I)
    text = open(conf, encoding='utf-8', errors='replace').read()
    pdf = os.path.join(folder, re.search(r'(?m)^PDFFilePath\s*=\s*(.+)$', text).group(1).strip())

    segs = parse_outline_segments(pcb)
    comps = connected_components(segs)
    total = bbox([p for s in segs for p in s])
    W_u, H_u = total[2]-total[0], total[3]-total[1]

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(['pdfimages', '-j', '-png', pdf, os.path.join(td, 'im')],
                       check=True, capture_output=True)
        files = [(os.path.getsize(os.path.join(td, f)), os.path.join(td, f)) for f in os.listdir(td)]
        img = Image.open(sorted(files, reverse=True)[0][1]).convert('RGBA')
        img.load()
    blobs = sorted(find_image_blobs(img), key=lambda b: b[0])
    islands = group_islands(comps, len(blobs)) or [[p for s in segs for p in s]]
    islands.sort(key=lambda i: bbox(i)[0])
    if len(islands) != len(blobs):
        sys.exit(f"{len(blobs)} blobs x {len(islands)} ilhas — nao tratado")

    # segmentos por ilha (pelo ponto medio) e perfis
    iprofs = []
    for isl in islands:
        ib = bbox(isl)
        mysegs = [s for s in segs
                  if ib[0]-2 <= (s[0][0]+s[1][0])/2 <= ib[2]+2 and ib[1]-2 <= (s[0][1]+s[1][1])/2 <= ib[3]+2]
        iprofs.append(span_profiles(island_mask(mysegs, ib)))

    img_rgb = img.convert('RGB')
    bmasks = [blob_mask_of(img_rgb, bl) for bl in blobs]

    import itertools
    best = None
    for perm in itertools.permutations(range(len(blobs))):
        tot, combo = 0.0, []
        for i_isl, i_blob in enumerate(perm):
            errs = {(fh, fv): orient_error(iprofs[i_isl], bmasks[i_blob], fh, fv)
                    for fh in (False, True) for fv in (False, True)}
            (fh, fv), e = min(errs.items(), key=lambda kv: kv[1])
            tot += e; combo.append((i_blob, fh, fv, e))
        if best is None or tot < best[0]:
            best = (tot, combo)
    tot, combo = best
    # erro da configuracao identidade (blob i -> ilha i, sem flips) para comparar
    ident = sum(orient_error(iprofs[i], bmasks[i], False, False) for i in range(len(blobs)))
    is_ident = all(i_blob == i and not fh and not fv for i, (i_blob, fh, fv, _) in enumerate(combo))
    for i_isl, (i_blob, fh, fv, e) in enumerate(combo):
        print(f"ilha {i_isl} <- blob {i_blob}  flipH={fh} flipV={fv}  erro={e:.4f}")
    print(f"erro total: {tot:.4f}  identidade: {ident:.4f}  " +
          ("JA OTIMO" if is_ident else f"melhora: {ident-tot:.4f}"))
    if not is_ident and ident - tot < 0.01:
        print("margem pequena — mantendo como esta")
        return
    if not apply_:
        return

    ppus = []
    for i_isl, (i_blob, fh, fv, e) in enumerate(combo):
        ib = bbox(islands[i_isl]); bl = blobs[i_blob]
        ppus += [(bl[2]-bl[0])/(ib[2]-ib[0]), (bl[3]-bl[1])/(ib[3]-ib[1])]
    ppu = sum(ppus)/len(ppus)
    cw, ch = int(round(W_u*ppu)), int(round(H_u*ppu))
    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    for i_isl, (i_blob, fh, fv, e) in enumerate(combo):
        ib = bbox(islands[i_isl]); bl = blobs[i_blob]
        crop = img.crop((bl[0], bl[1], bl[2]+1, bl[3]+1))
        if fh: crop = crop.transpose(Image.FLIP_LEFT_RIGHT)
        if fv: crop = crop.transpose(Image.FLIP_TOP_BOTTOM)
        tw = max(1, int(round((ib[2]-ib[0])*ppu))); th = max(1, int(round((ib[3]-ib[1])*ppu)))
        canvas.paste(crop.resize((tw, th), Image.LANCZOS),
                     (int(round(ib[0]*ppu)), int(round((H_u-ib[3])*ppu))))
    out_name = os.path.basename(re.sub(r'\.pcb$', '_bg.png', pcb, flags=re.I))
    canvas.save(os.path.join(folder, out_name))
    sx, sy = W_u/canvas.width, H_u/canvas.height
    kv = {}
    for P in ('Top', 'Bottom'):
        kv.update({f'{P}ImageFile': out_name, f'{P}ImageOffsetX': 0, f'{P}ImageOffsetY': 0,
                   f'{P}ImageScalingX': f"{sx:.6f}", f'{P}ImageScalingY': f"{sy:.6f}",
                   f'{P}ImageMirrorX': 'false', f'{P}ImageMirrorY': 'false',
                   f'{P}ImageTransparency': '0.000000'})
    update_conf(conf, kv)
    print(f"APLICADO: {out_name} {canvas.width}x{canvas.height}px")

if __name__ == '__main__':
    main()
