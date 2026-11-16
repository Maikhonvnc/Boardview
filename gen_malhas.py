# Por placa gera:
#  1) <base> - malhas.html : busca net -> componentes (nomes amigaveis se houver
#     alias). Abre no navegador; digite "botao"/"N66732"/"GND" e ve tudo da malha.
#  2) <base> - malhas.csv  : template De;Componentes;Para p/ renomear (rename_nets.py).
# Aliases atuais vem do proprio .pcb (nomes ja renomeados aparecem como estao).
# Uso: python gen_malhas.py <arquivo.pcb> <outdir_html> <outdir_csv>
import sys, os, re, json, csv, html
from collections import defaultdict
from xzz_parts import load_parts

def build(pcb, outhtml, outcsv):
    nets, parts = load_parts(pcb)
    base = re.sub(r'\.pcb$', '', os.path.basename(pcb))
    net_comps = defaultdict(set)
    for pname, pins in parts:
        for pinname, net, x, y in pins:
            net_comps[net].add(pname)
    rows = sorted(((net, sorted(comps)) for net, comps in net_comps.items()),
                  key=lambda r: (-len(r[1]), r[0]))
    # CSV template (De;Componentes;Para)
    with open(os.path.join(outcsv, base + ' - malhas.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['De', 'Componentes', 'Para'])
        for net, comps in rows:
            w.writerow([net, ' '.join(comps), ''])
    # HTML busca
    data = [{'n': net, 'c': comps} for net, comps in rows]
    doc = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Malhas — __B__</title>
<style>*{box-sizing:border-box}body{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0e1116;color:#e6edf3}
header{padding:16px 22px;background:#161b22;border-bottom:1px solid #263041;position:sticky;top:0}
h1{margin:0;font-size:17px}.sub{color:#9aa7b8;font-size:13px}
#q{width:100%;margin-top:10px;padding:9px 12px;font-size:15px;background:#0e1116;border:1px solid #2b3a52;border-radius:8px;color:#e6edf3}
.wrap{padding:14px 22px;max-width:1100px;margin:0 auto}
.row{background:#161b22;border:1px solid #263041;border-radius:8px;padding:10px 13px;margin-bottom:8px}
.net{font-weight:600;color:#7aa2f7;font-size:15px}.net.named{color:#4ade80}
.cnt{color:#7d8ba0;font-size:12px;margin-left:8px}
.comps{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
.cm{font-size:12px;background:#1a2130;border:1px solid #2b3a52;border-radius:5px;padding:1px 7px;color:#cdd9e5}
.hint{color:#7d8ba0;font-size:12px;margin:8px 0}
mark{background:#7a5f1a;color:#fbbf24;border-radius:3px}
</style></head><body>
<header><h1>🕸️ Malhas — __B__</h1><div class="sub">__N__ malhas · clique no OBV acende a net; aqui você acha todos os componentes dela</div>
<input id="q" placeholder="buscar malha ou componente: botão, GND, N66732, VBAT…" autofocus></header>
<div class="wrap"><div class="hint">Malhas com <b>nome amigável</b> (renomeadas) aparecem em verde. Rails (mais componentes) primeiro.</div><div id="list"></div></div>
<script>
const DATA=__DATA__;
const GEN=/^(GND|A?S?Net\\d+|NC|UNCONNECTED)$/i;
const list=document.getElementById('list'), q=document.getElementById('q');
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function hl(s,t){if(!t)return esc(s);const i=s.toLowerCase().indexOf(t);if(i<0)return esc(s);
 return esc(s.slice(0,i))+'<mark>'+esc(s.slice(i,i+t.length))+'</mark>'+esc(s.slice(i+t.length))}
function render(t){t=t.trim().toLowerCase();let out=[],n=0;
 for(const d of DATA){const nn=d.n.toLowerCase();
  const inNet=nn.includes(t);const hitC=t&&d.c.filter(c=>c.toLowerCase().includes(t));
  if(t&&!inNet&&(!hitC||!hitC.length))continue;
  if(++n>400){out.push('<div class=hint>… refine a busca (mais de 400)</div>');break}
  const named=!GEN.test(d.n);
  out.push('<div class=row><span class="net'+(named?' named':'')+'">'+hl(d.n,inNet?t:'')+
   '</span><span class=cnt>'+d.c.length+' comp</span><div class=comps>'+
   d.c.map(c=>'<span class=cm>'+hl(c,(hitC&&hitC.includes(c))?t:'')+'</span>').join('')+'</div></div>');}
 list.innerHTML=out.join('')||'<div class=hint>nada encontrado</div>';}
q.oninput=()=>render(q.value);render('');
</script></body></html>'''
    doc = (doc.replace('__B__', html.escape(base)).replace('__N__', str(len(rows)))
           .replace('__DATA__', json.dumps(data, ensure_ascii=False)))
    open(os.path.join(outhtml, base + ' - malhas.html'), 'w', encoding='utf-8').write(doc)
    return len(rows)

if __name__ == '__main__':
    pcb, outhtml, outcsv = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(outhtml, exist_ok=True); os.makedirs(outcsv, exist_ok=True)
    print(f"{os.path.basename(pcb)}: {build(pcb, outhtml, outcsv)} malhas")
