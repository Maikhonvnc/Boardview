// Leitura de MODO DIODO por malha — o teste que achou a esfera 72 aberta do S1.
//
// Convencao: ponteira VERMELHA no GND, PRETA no ponto. Nessa polaridade a corrente
// entra pelo diodo de protecao do proprio pino, entao esfera aberta da OL. Na outra
// (vermelha no ponto) o caminho pode dar a volta por um pull-up e mascarar a falha.
//
// Dois valores por malha:
//   med — ESTA placa, a que esta na bancada (tecla D)
//   ref — a placa BOA, de referencia     (Shift+D)
// O localStorage e por MODELO (boardKey), nao por placa fisica: ao trocar de placa
// do mesmo modelo, as 'med' anteriores continuam la ate serem sobrescritas.
//
// Chave = nome CRU da malha (pin.netOriginal): renomear a malha (tecla M) nao perde
// a anotacao.

function diodosCarregar() {
    try { return JSON.parse(localStorage.getItem('dd_' + boardKey) || '{}'); }
    catch (e) { return {}; }
}

function diodosSalvar(d) {
    try { localStorage.setItem('dd_' + boardKey, JSON.stringify(d)); } catch (e) {}
}

// nome exibido -> nome cru
function malhaCrua(net) {
    if (!net || typeof parts === 'undefined') return net;
    for (const p of parts) for (const q of (p.pins || []))
        if (q.net === net) return q.netOriginal || net;
    return net;
}

function diodoDe(net) {
    if (!net) return null;
    return diodosCarregar()[chaveDiodo(net)] || null;
}

// 'OL' contra numero, ou numeros que diferem mais de 0,05 V
function diodoDiverge(d) {
    if (!d || d.med == null || d.ref == null) return false;
    const n = (s) => parseFloat(String(s).replace(',', '.'));
    const a = n(d.med), b = n(d.ref);
    if (isNaN(a) || isNaN(b)) return String(d.med).toUpperCase() !== String(d.ref).toUpperCase();
    return Math.abs(a - b) > 0.05;
}

// texto curto: "0.550 · ref 0.550"
function textoDiodo(net) {
    const d = diodoDe(net);
    if (!d) return '';
    const partes = [];
    if (d.med != null) partes.push(d.med);
    if (d.ref != null) partes.push('ref ' + d.ref);
    return partes.join(' · ');
}

// chave da leitura: a malha crua; pino sem malha (NC) vira PECA.PINO (todos os NC
// caiam na mesma chave 'NC', e um diodo anotado num aparecia em todos)
function chaveDiodo(net) {
    const cru = malhaCrua(net);
    return (cru === 'NC' && typeof alvoMedicao === 'function') ? alvoMedicao(net) : cru;
}

function anotarDiodo(net, qual) {
    if (!net) { alert('Clique num pino da malha primeiro.'); return; }
    if (net === 'GND') { alert('No GND nao tem leitura de diodo.'); return; }
    // o nome do tecnico vem ANTES do valor: cancelar o nome cancela a leitura inteira
    if (typeof cadernoGarantirTecnico === 'function' && !cadernoGarantirTecnico()) return;
    const cru = chaveDiodo(net);
    if (!cru) { alert('Clique no pino de novo: não consegui identificar este pino.'); return; }
    const d = diodosCarregar();
    const atual = (d[cru] && d[cru][qual]) || '';
    const s = prompt(`Modo DIODO — ${qual === 'ref' ? 'REFERENCIA (placa boa)' : 'ESTA placa'}\n` +
                     `malha ${net}\nponteira VERMELHA no GND, PRETA no ponto\n` +
                     `(ex: 0.550 ou OL — vazio = apagar):`, atual);
    if (s === null) return;
    const v = s.trim().replace(',', '.').toUpperCase();
    // so numero ou OL: e o que o multimetro mostra, e o que a plataforma vai somar
    if (v && v !== 'OL' && !/^\d+(\.\d+)?$/.test(v)) {
        alert('Leitura de diodo precisa ser um número (ex.: 0.550) ou OL.');
        return;
    }
    d[cru] = d[cru] || {};
    if (v) d[cru][qual] = v; else delete d[cru][qual];
    if (!Object.keys(d[cru]).length) delete d[cru];
    diodosSalvar(d);
    // vai tambem para o caderno de bancada (medicoes.js): 'med' e a placa da bancada
    if (typeof cadernoRegistrar === 'function')
        cadernoRegistrar({ tipo: 'diodo', papel: qual === 'ref' ? 'ref' : 'reparo', net, valor: v || null });
    if (typeof ajusteAviso === 'function') {
        const fim = d[cru] ? textoDiodo(net) : 'apagado';
        ajusteAviso(`diodo ${net}: ${fim}` + (diodoDiverge(d[cru]) ? '  — DIVERGE da referencia' : ''));
    }
    if (typeof updateComponentInfo === 'function' && typeof parteNoPainel !== 'undefined' && parteNoPainel)
        updateComponentInfo(parteNoPainel, typeof selectedPin !== 'undefined' ? selectedPin : null);
}

function diodoIniciar() {
    window.addEventListener('keydown', (e) => {
        if (/input|textarea/i.test((e.target.tagName || ''))) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (e.key === 'd' || e.key === 'D') {
            e.preventDefault();
            const net = (typeof malhaSelecionada === 'function') ? malhaSelecionada() : null;
            anotarDiodo(net, e.shiftKey ? 'ref' : 'med');
        }
    });
}
