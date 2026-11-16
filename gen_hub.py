# Gera Boardview/HUB.html: SPA por MODELO. Landing = grade de modelos; clicar
# um modelo mostra todas as suas placas com foto + PDFs (mapas) + links (abrir no
# OBV, netlist, malhas, caderno). Placas abrem no OBV por associacao .pcb.
import os, re, json, glob, html
from paths import BV, DRONES

NET, CAD, MAL = (os.path.join(BV, d) for d in ('Netlists', 'Cadernos', 'Malhas'))

def conf(pcb):
    c = re.sub(r'\.pcb$', '.conf', pcb, flags=re.I)
    return open(c, encoding='utf-8', errors='replace').read() if os.path.exists(c) else ''

def cval(t, key):
    m = re.search(r'(?m)^%s\s*=\s*(.+)$' % key, t)
    return m.group(1).strip() if m else None

def furl(p):
    """URL relativa servida pelo servidor local (servidor.py mapeia /_drones/)."""
    if not p or not os.path.exists(p): return None
    q = os.path.abspath(p).replace(chr(92), '/')
    dr = DRONES.replace(chr(92), '/').rstrip('/')
    bv = BV.replace(chr(92), '/').rstrip('/')
    if q.lower().startswith(dr.lower() + '/'):   rel = '_drones/' + q[len(dr)+1:]
    elif q.lower().startswith(bv.lower() + '/'): rel = q[len(bv)+1:]
    else: return None
    return rel.replace('#', '%23').replace(' ', '%20')

def obv_url(pcb):
    # protocolo customizado -> abre no OpenBoardView (registrado em HKCU)
    return 'obvboard:///' + pcb.replace('\\', '/').replace('#', '%23').replace(' ', '%20')

def exists(*a):
    p = os.path.join(*a)
    return p if os.path.exists(p) else None

# mapa placa->json online (Digital Board no R2); cresce conforme a galera sobe
ONLINE = {}
_om = os.path.join(BV, 'online_maps.json')
if os.path.exists(_om):
    ONLINE = json.load(open(_om, encoding='utf-8'))
VIEWER = 'https://server515.github.io/01/2.html?file=https://pub-108997d22bd848ec9f92cfe6ca1ddec2.r2.dev/drone/'
def online_link(pcb_basename):
    jn = ONLINE.get(pcb_basename)
    return (VIEWER + jn.replace(' ', '%20') + '.json') if jn else None

MODEL_CAT = [('Controles / Rádio', ['rc ']), ('Drones', [''])]
def catof(folder):
    fl = folder.lower()
    if fl.startswith('dji rc') or ' rc ' in fl or fl.endswith(' rc'):
        return 'Controles / Rádio'
    return 'Drones'

# --- miniatura leve (gen_thumbs.py) ---
def _slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
def thumb_de(folder):
    f = os.path.join(BV, 'thumbs', _slug(folder) + '.jpg')
    return 'thumbs/' + _slug(folder) + '.jpg' if os.path.exists(f) else None

# --- DigitalBoard: viewer local + material do acervo, por modelo ---
DBDIR = os.path.join(BV, 'DigitalBoard')
_DBV = []
_bj = os.path.join(BV, 'digital_viewer', 'build', 'boards.json')
if os.path.exists(_bj):
    _DBV = json.load(open(_bj, encoding='utf-8'))
def _norm(s): return re.sub(r'[^a-z0-9]', '', s.lower())
def db_de(folder):
    """Casa a pasta do modelo com o viewer local do DigitalBoard e o material dele."""
    k = _norm(folder.replace('DJI', '').replace('Mavic Air', 'air').replace('Mavic', ''))
    achou = []
    for b in _DBV:
        if _norm(b['name']).find(k) >= 0 or (k and k in _norm(b['id'])):
            achou.append({'id': b['id'], 'name': b['name'],
                          'url': 'digital_viewer/index.html?board=' + b['id']})
    # image-ref / esquematico do acervo
    pdfs = []
    for q in sorted(glob.glob(os.path.join(DBDIR, 'pdf', '*.pdf'))):
        if k and k[:6] in _norm(os.path.basename(q)):
            pdfs.append({'nome': os.path.basename(q), 'url': furl(q)})
    return {'viewers': achou[:4], 'pdfs': pdfs[:6]} if (achou or pdfs) else None

models = {}
for folder in sorted(os.listdir(DRONES)):
    fdir = os.path.join(DRONES, folder)
    if not os.path.isdir(fdir) or '__MACOSX' in folder:
        continue
    boards = []
    for pcb in sorted(glob.glob(os.path.join(fdir, '*.pcb'))):
        if os.path.basename(pcb).startswith('._'):
            continue
        base = re.sub(r'\.pcb$', '', os.path.basename(pcb))
        t = conf(pcb)
        bg = cval(t, 'TopImageFile')
        bgp = os.path.join(fdir, bg) if bg else None
        bridge = cval(t, 'PDFFilePath')
        brp = os.path.join(fdir, bridge) if bridge else None
        brn = (bridge or '').upper()
        boards.append({
            'name': base,
            'pcb': obv_url(pcb),
            'pcbfile': furl(pcb),
            'photo': furl(bgp) if bgp and os.path.exists(bgp) else None,
            'maps': furl(brp) if brp and os.path.exists(brp) else None,
            'mapsIsDigital': 'DIGITALBOARD' in brn,
            'net': furl(exists(NET, base + ' - netlist.csv')),
            'mal': furl(exists(MAL, base + ' - malhas.html')),
            'cad': furl(exists(CAD, base + ' - caderno.csv')),
            'online': online_link(os.path.basename(pcb)),
            'view': ('viewer.html?board=' + base.replace('#', '%23').replace(' ', '%20')) if exists(BV, 'boards', base + '.js') else None,
        })
    if boards:
        junto = os.path.join(fdir, folder + ' - JUNTO.brd')
        models.setdefault(catof(folder), []).append({
            'model': folder, 'boards': boards,
            'thumb': thumb_de(folder),
            'db': db_de(folder),
            'junto': obv_url(junto) if os.path.exists(junto) else None})

data = {'cats': []}
nb = 0
for cat in ['Drones', 'Controles / Rádio']:
    if cat in models:
        data['cats'].append({'cat': cat, 'models': sorted(models[cat], key=lambda m: m['model'])})
        nb += sum(len(m['boards']) for m in models[cat])

doc = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hub Boardview DJI</title><style>
*{box-sizing:border-box}body{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0e1116;color:#e6edf3}
header{padding:18px 26px;background:linear-gradient(135deg,#1a2332,#0e1116);border-bottom:1px solid #263041;display:flex;align-items:center;gap:14px}
.pdfbtn{text-decoration:none;color:#fbbf24;background:#211c10;border:1px solid #7a5f1a;padding:8px 14px;border-radius:9px;font-weight:600;font-size:14px;white-space:nowrap}
.pdfbtn:hover{background:#2a2413}
h1{margin:0;font-size:20px;cursor:pointer}.sub{color:#9aa7b8;font-size:13px}
.wrap{padding:22px 26px;max-width:1500px;margin:0 auto}
.back{background:#182030;border:1px solid #2b3a52;color:#7aa2f7;border-radius:7px;padding:5px 12px;cursor:pointer;font-size:13px}
h2{margin:22px 0 12px;font-size:15px;color:#cdd9e5;border-bottom:1px solid #263041;padding-bottom:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.mcard{background:#161b22;border:1px solid #263041;border-radius:12px;overflow:hidden;cursor:pointer;transition:.15s}
.mcard:hover{border-color:#3d5170;transform:translateY(-2px)}
.mcard .thumb{height:150px;background:#0a0d11 center/contain no-repeat;border-bottom:1px solid #263041}
.mcard .mt{padding:11px 13px;font-weight:600}
.mcard .ms{padding:0 13px 12px;color:#7d8ba0;font-size:12px}
.boards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.bcard{background:#161b22;border:1px solid #263041;border-radius:12px;overflow:hidden}
.bcard .photo{height:230px;background:#0a0d11 center/contain no-repeat;border-bottom:1px solid #263041;position:relative}
.bcard .photo .tag{position:absolute;top:8px;right:8px;background:#122019;border:1px solid #1f6f43;color:#4ade80;font-size:11px;padding:2px 8px;border-radius:6px}
.bcard .bt{padding:11px 13px 4px;font-weight:600;font-size:14px}
.badges{display:flex;flex-wrap:wrap;gap:4px;padding:4px 13px 8px}
.b{font-size:11px;padding:2px 7px;border-radius:6px;border:1px solid}
.b.g{background:#132a1e;border-color:#1f6f43;color:#4ade80}.b.v{background:#2a2413;border-color:#7a5f1a;color:#fbbf24}
.b.r{background:#2a1320;border-color:#7a1f45;color:#f472b6}.b.n{background:#132a2a;border-color:#1a6f6f;color:#4dd6d6}
.b.m{background:#241a2f;border-color:#5a3a7a;color:#c084fc}
.dbbox{background:#1a1608;border:1px solid #5d4a15;border-radius:11px;padding:11px 14px;margin:0 0 16px}
.dbt{color:#fbbf24;font-weight:600;font-size:13px;margin-bottom:8px}
.dblinks{display:flex;flex-wrap:wrap;gap:7px}
.dblinks a{font-size:12.5px;text-decoration:none;padding:5px 11px;border-radius:7px;border:1px solid}
.dblinks a.dbv{color:#fde68a;background:#2a2109;border-color:#7a5f1a}
.dblinks a.dbv:hover{background:#3a2d0c}
.dblinks a.dbp{color:#93c5fd;background:#111c2e;border-color:#2b4a7a}
.dblinks a.dbp:hover{background:#16263f}
.links{display:flex;flex-wrap:wrap;gap:6px;padding:0 13px 13px}
.links a{font-size:12px;text-decoration:none;color:#7aa2f7;background:#182030;border:1px solid #2b3a52;padding:4px 10px;border-radius:6px}
.links a:hover{background:#1f2b40}.links a.open{color:#4ade80;border-color:#1f6f43;background:#122019}
.links a.maps{color:#fbbf24;border-color:#7a5f1a;background:#211c10}
.links a.online{color:#f472b6;border-color:#7a1f45;background:#2a1320}
.links a.view{color:#4dd6d6;border-color:#1a6f6f;background:#0f2222}
h2 a.ws{font-size:13px;text-decoration:none;color:#4dd6d6;background:#0f2222;border:1px solid #1a6f6f;padding:4px 11px;border-radius:7px;margin-left:8px;font-weight:600}
h2 a.ws:hover{background:#123030}
h2 a.junto{font-size:13px;text-decoration:none;color:#4ade80;background:#122019;border:1px solid #1f6f43;padding:4px 11px;border-radius:7px;margin-left:10px;font-weight:600}
h2 a.junto:hover{background:#16321f}
.tip{background:#161b22;border:1px solid #263041;border-radius:8px;padding:10px 14px;margin:0 0 16px;color:#9aa7b8;font-size:13px}
kbd{background:#263041;border-radius:4px;padding:1px 5px;font-size:12px}
#detail{display:none}
</style></head><body>
<header><div style="flex:1"><h1 id="home">🛠️ Hub Boardview DJI</h1><div class="sub" id="subt"></div></div>__PDFBTN__</header>
<div class="wrap">
<div id="landing"></div>
<div id="detail"><button class="back" id="back">← Voltar aos modelos</button><div id="detailBody"></div></div>
</div>
<script>
const DATA=__DATA__;
const NB=__NB__;
document.getElementById('subt').textContent=NB+' placas · foto sob os pads + mapa de tensão/2.4/5.8/carga no visor lateral · malhas nomeáveis';
const landing=document.getElementById('landing'),detail=document.getElementById('detail'),
 detailBody=document.getElementById('detailBody');
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function badge(on,l,c){return on?`<span class="b ${c}">${l}</span>`:''}
function renderLanding(){
 let h='<div class="tip">Selecione um <b>modelo</b> para ver todas as suas placas. Clique <b>▶ Abrir no OBV</b> para abrir direto no OpenBoardView '+
  '(na 1ª vez o navegador pergunta se pode abrir o app — marque <b>sempre permitir</b>). No OBV: clique num pino para acender a malha, '+
  'e o mapa de tensão/RF navega com <kbd>PgDn</kbd> no visor lateral. <b>👁️ Prévia</b> = espiada rápida no navegador (sem todas as funções).</div>';
 for(const c of DATA.cats){h+=`<h2>${esc(c.cat)}</h2><div class="grid">`;
  for(const m of c.models){
   const nv=m.boards.filter(b=>b.mapsIsDigital).length;
   h+=`<div class="mcard" data-cat="${esc(c.cat)}" data-model="${esc(m.model)}">
    <div class="thumb" style="${m.thumb?`background-image:url('${m.thumb}')`:''}"></div>
    <div class="mt">${esc(m.model)}</div>
    <div class="ms">${m.boards.length} placa(s)${nv?` · ${nv} com mapa DigitalBoard`:''}</div></div>`;}
  h+='</div>';}
 landing.innerHTML=h;
 document.querySelectorAll('.mcard').forEach(el=>el.onclick=()=>openModel(el.dataset.cat,el.dataset.model));
}
function openModel(cat,model){
 const m=DATA.cats.find(c=>c.cat===cat).models.find(x=>x.model===model);
 const wsurl='viewer.html?model='+encodeURIComponent(model);
 let h=`<h2>${esc(model)} <span style="color:#7d8ba0;font-weight:400">— ${m.boards.length} placa(s)</span>`+
   (m.junto?` <a class="junto" href="${m.junto}">🔗 Abrir junto no OBV</a>`:'')+
   `</h2>`;
 if(m.db && (m.db.viewers.length||m.db.pdfs.length)){
   h+=`<div class="dbbox"><div class="dbt">🟡 DigitalBoard</div><div class="dblinks">`+
      m.db.viewers.map(v=>`<a class="dbv" href="${v.url}">👁️ ${esc(v.name)}</a>`).join('')+
      m.db.pdfs.map(p=>`<a class="dbp" href="${p.url}" target="_blank">📄 ${esc(p.nome.replace(/\.pdf$/i,''))}</a>`).join('')+
      `</div></div>`;
 }
 h+=`<div class="boards">`;
 for(const b of m.boards){
  h+=`<div class="bcard"><div class="photo" style="${b.photo?`background-image:url('${b.photo}')`:''}">${b.mapsIsDigital?'<span class="tag">⚡ mapa</span>':''}</div>
   <div class="bt">${esc(b.name)}</div>
   <div class="badges">${badge(!!b.photo,'📷 Foto','g')}${badge(b.mapsIsDigital,'⚡ Tensão','v')}${badge(b.mapsIsDigital,'📡 2.4/5.8','r')}${badge(!!b.net,'📋 Netlist','n')}${badge(!!b.mal,'🕸️ Malhas','m')}</div>
   <div class="links">${b.pcb?`<a class="open" href="${b.pcb}">▶ Abrir no OBV</a>`:''}${b.maps?`<a class="maps" href="${b.maps}" target="_blank">🗺️ Mapas/PDF</a>`:''}${b.online?`<a class="online" href="${b.online}" target="_blank">🔴 Online</a>`:''}${b.mal?`<a href="${b.mal}" target="_blank">🕸️ Malhas</a>`:''}${b.net?`<a href="${b.net}">📋 Netlist</a>`:''}${b.cad?`<a href="${b.cad}">✏️ Caderno</a>`:''}</div></div>`;}
 h+='</div>';
 detailBody.innerHTML=h;landing.style.display='none';detail.style.display='block';window.scrollTo(0,0);
}
function goHome(){detail.style.display='none';landing.style.display='block';}
document.getElementById('back').onclick=goHome;
document.getElementById('home').onclick=goHome;
renderLanding();
</script></body></html>'''
pdfdir = os.path.join(BV, 'PDFs-Drone')
npdf = len(glob.glob(os.path.join(pdfdir, '*.pdf'))) if os.path.isdir(pdfdir) else 0
pdfbtn = (f'<a class="pdfbtn" href="{furl(pdfdir)}" target="_blank">📄 PDFs de drone ({npdf})</a>'
          if npdf else '')
doc = doc.replace('__DATA__', json.dumps(data, ensure_ascii=False)).replace('__NB__', str(nb)).replace('__PDFBTN__', pdfbtn)
open(os.path.join(BV, 'HUB.html'), 'w', encoding='utf-8').write(doc)
print(f'HUB.html: {sum(len(m["boards"]) for c in data["cats"] for m in c["models"])} placas em {sum(len(c["models"]) for c in data["cats"])} modelos')
