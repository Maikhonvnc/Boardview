// Malhas: identidade (malhaCanon), apelidos e tensao medida por malha (teclas V / Shift+V).
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)

// ===== Tensao MEDIDA pelo usuario (adaptacao local): salva por placa+malha e colore a malha =====
let boardKey = (function(){ if (window.__board) return window.__board;   // vem do preload
  let m = location.search.match(/board=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : 'mine2'; })();
let userVolts = {};
try { userVolts = JSON.parse(localStorage.getItem('uv_' + boardKey) || '{}'); } catch(e) {}

// Apelido de malha: build/malhas.json = {"<placa>": {"Net161": "BATERIA_ENTRADA"}},
// carregado no preload() do index.html. Sem o arquivo (ou noutra pagina, como o
// mine2_db.html) devolve o nome cru. CUIDADO ao escolher apelidos: o viewer deduz
// tensao do nome — "VBAT"/"VSYS" viram 4,2 V e "3P3"/"1V8" viram tensao.
// A tensao MEDIDA estava guardada pelo nome cru; ela migra para o apelido aqui,
// senao renomear a malha apagaria a medicao da tela.
// troca o nome exibido de todos os pinos de acordo com os apelidos atuais
function reaplicarApelidos() {
    if (typeof parts === 'undefined') return;
    for (const p of parts) for (const q of (p.pins || []))
        if (q.netOriginal) q.net = apelidoMalha(q.netOriginal);
    if (typeof renderBuffer === 'function') renderBuffer();
}

// Identidade da malha sem o prefixo de tensao. Alguns .bvr trazem a malha como
// "7P0_Net9" / "3P0Net18" / "VCC_3P2V_Net65"; os apelidos (malhas.json, anotacoes) e o
// cobre (.cobre.json) usam "Net9". Sem isto o apelido e o cobre dessas malhas nunca
// apareciam. O nome sem prefixo e unico em todas as placas (conferido em 11/2026).
function malhaCanon(n) {
    const m = /(Net\d+)$/.exec(n || '');
    return m ? m[1] : n;
}

function apelidoMalha(cru) {
    // o que foi renomeado na tela (tecla M, localStorage) vence o build/malhas.json
    if (apelidoMalha.locais === undefined) {
        try { apelidoMalha.locais = JSON.parse(localStorage.getItem('malhas_' + boardKey) || '{}'); }
        catch (e) { apelidoMalha.locais = {}; }
    }
    const m = window.__malhas && window.__malhas[boardKey];
    const can = malhaCanon(cru);
    const novo = apelidoMalha.locais[cru] || apelidoMalha.locais[can] || (m && (m[cru] || m[can])) || cru;
    if (novo !== cru && userVolts[cru] != null && userVolts[novo] == null) {
        userVolts[novo] = userVolts[cru];
        delete userVolts[cru];
        try { localStorage.setItem('uv_' + boardKey, JSON.stringify(userVolts)); } catch (e) {}
    }
    return novo;
}
function saveUserVolts(){ try { localStorage.setItem('uv_' + boardKey, JSON.stringify(userVolts)); } catch(e){} }
function parseVoltNum(s){ if (s == null) return null; let m = (''+s).replace(',','.').match(/(\d+(?:\.\d+)?)/);
  if (!m) return null; let v = parseFloat(m[1]); return (v >= 0 && v <= 60) ? v : null; }
function voltBandColor(v){
  const B = [[12,[220,38,38]],[8,[249,115,22]],[5,[34,197,94]],[3.3,[14,165,233]],[3.0,[20,184,166]],
             [2.8,[132,204,22]],[1.8,[168,85,247]],[1.2,[234,179,8]],[1.0,[236,72,153]],[0.8,[100,116,139]]];
  for (const [bv,c] of B) if (Math.abs(bv - v) <= 0.2) return c;
  let h = (((v*57+15)%360)+360)%360, s = 0.85, val = 0.95, c = val*s, x = c*(1-Math.abs((h/60)%2-1)), m = val-c;
  let seg = [[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][Math.floor(h/60)%6];
  return [Math.round((seg[0]+m)*255), Math.round((seg[1]+m)*255), Math.round((seg[2]+m)*255)];
}
// papel: 'reparo' (V, a placa da bancada) ou 'ref' (Shift+V, placa BOA). A copia local
// (userVolts) continua sendo o que a tela mostra; a leitura vai tambem para o caderno
// (medicoes.js), com o papel, o tecnico, a OS e a condicao.
// Tensao da placa BOA (Shift+V): copia separada, chaveada pela malha CRUA. Antes as duas
// dividiam o userVolts: o Shift+V vinha preenchido com o valor da placa com defeito, e
// apagar com V apagava a referencia so na tela.
let uvRef = {};
try { uvRef = JSON.parse(localStorage.getItem('uvref_' + boardKey) || '{}'); } catch (e) {}

function setNetVoltage(net, papel = 'reparo'){
  if (!net) { alert('Selecione um pad/malha primeiro (clique num pino).'); return; }
  if (net === 'GND') { alert('No GND não tem tensão para anotar.'); return; }
  // o nome do tecnico vem ANTES do valor: cancelar o nome cancela a leitura inteira
  if (typeof cadernoGarantirTecnico === 'function' && !cadernoGarantirTecnico()) return;
  const ref = papel === 'ref';
  const cru = typeof malhaCrua === 'function' ? malhaCrua(net) : net;
  let cur = ref ? (uvRef[cru] ?? '') : (userVolts[net] ?? '');
  const quem = ref ? 'REFERÊNCIA (placa boa)' : 'ESTA placa';
  let s = prompt('Tensão MEDIDA — ' + quem + '\nmalha ' + net +
                 '  (ex: 5, 3.3, 8, 1.8).  Vazio = apagar:', cur);
  if (s === null) return;
  let v = null;
  if (s.trim() !== '') {
    v = tensaoValida(s);
    if (v === null) { alert('Tensão precisa ser um número abaixo de 1000 (ex.: 3.3, 8 ou 1,8).'); return; }
  }
  if (ref) {
    if (v === null) delete uvRef[cru]; else uvRef[cru] = v;
    try { localStorage.setItem('uvref_' + boardKey, JSON.stringify(uvRef)); } catch (e) {}
  } else {
    if (v === null) delete userVolts[net]; else userVolts[net] = v;
    saveUserVolts();
  }
  if (typeof cadernoRegistrar === 'function') cadernoRegistrar({ tipo: 'tensao', papel, net, valor: v });
  if (typeof redraw === 'function') redraw();
}
