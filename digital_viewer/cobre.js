// Cobre real da placa: trilhas e vias da malha selecionada, por camada.
//
// Vem de build/COBRE/<placa>.cobre.json (gerado por importar_cobre.py a partir dos
// JSON "skilbypm" do DigitalBoard), ja nas coordenadas do .bvr. So existe para as
// placas que tem esse arquivo; nas outras nada muda.
//
// Carregado por fetch (NUNCA no preload: um load que falha trava o p5 1.6 inteiro).
// Tecla L liga/desliga (C ja e o cursor cruzado do modo de ajuste); Shift+L mostra
// uma camada por vez (todas -> 1 -> ... -> fundo). Cada camada tem uma cor propria:
// topo laranja, fundo azul. Vias = circulos brancos.

let cobreDados = null;
let cobreLigado = true;
let linhasVerdesLigadas = true;   // K: liga/desliga as linhas verdes que ligam os pinos da malha

function cobreIniciar() {
    if (typeof boardKey === 'undefined') return;
    fetch('build/COBRE/' + encodeURIComponent(boardKey) + '.cobre.json', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(j => { if (j && j.malhas) { cobreDados = j; if (typeof redraw === 'function') redraw(); } })
        .catch(() => {});
    window.addEventListener('keydown', (e) => {
        if (/input|textarea|select/i.test(e.target.tagName || '')) return;
        if ((e.key === 'k' || e.key === 'K') && !e.ctrlKey && !e.metaKey && !e.altKey) {
            linhasVerdesLigadas = !linhasVerdesLigadas;
            if (typeof ajusteAviso === 'function') ajusteAviso('linhas verdes ' + (linhasVerdesLigadas ? 'ligadas' : 'desligadas'));
            if (typeof redraw === 'function') redraw();
            return;
        }
        if ((e.key === 'l' || e.key === 'L') && !e.ctrlKey && !e.metaKey && !e.altKey && cobreDados) {
            if (e.shiftKey) { cobreLigado = true; cobreProximaCamada(); return; }
            cobreLigado = !cobreLigado;
            if (typeof ajusteAviso === 'function') ajusteAviso('cobre ' + (cobreLigado ? 'ligado' : 'desligado'));
        }
    });
}

// uma cor bem distinta por camada (topo laranja, fundo azul, internas cada uma de um tom)
const COBRE_PALETA = [[255, 140, 30], [255, 60, 60], [255, 220, 40], [80, 230, 90], [40, 220, 220],
                      [200, 90, 255], [255, 110, 200], [170, 255, 60], [255, 180, 140], [140, 170, 255],
                      [230, 230, 230]];
let cobreCamada = 0;   // 0 = todas; senao, so esta camada (Shift+L troca)

// o .cobre.json usa "Net9"; o .bvr pode trazer "7P0_Net9" (ver malhaCanon no SCRIPT3.js)
function cobreMalha(cru) {
    return cobreDados.malhas[cru] ||
        (typeof malhaCanon === 'function' ? cobreDados.malhas[malhaCanon(cru)] : undefined);
}

function cobreCor(camada) {
    const cs = (cobreDados && cobreDados.camadas) || [];
    if (camada === cs[cs.length - 1]) return [60, 150, 255];          // fundo
    const i = Math.max(0, cs.indexOf(camada));
    return COBRE_PALETA[i % COBRE_PALETA.length];
}

function cobreNomeCamada(c) {
    const cs = (cobreDados && cobreDados.camadas) || [];
    return c === cs[0] ? 'camada 1 (topo)' : c === cs[cs.length - 1] ? `camada ${c} (fundo)` : `camada ${c} (interna)`;
}

// Shift+L: todas -> camada 1 -> ... -> fundo -> todas; diz quantos trechos a malha tem nela
function cobreProximaCamada() {
    const cs = cobreDados.camadas;
    const i = cs.indexOf(cobreCamada);
    cobreCamada = i < 0 ? cs[0] : (i + 1 < cs.length ? cs[i + 1] : 0);
    let txt = cobreCamada ? cobreNomeCamada(cobreCamada) : 'todas as camadas';
    const cru = typeof currentNet !== 'undefined' && currentNet && typeof malhaCrua === 'function' ? malhaCrua(currentNet) : null;
    const m = cru && cobreMalha(cru);
    if (m) {
        const por = {};
        for (const t of m.t) por[t[0]] = (por[t[0]] || 0) + 1;
        txt += cobreCamada ? ` — ${por[cobreCamada] || 0} trecho(s) desta malha`
                           : ' — ' + cs.filter(c => por[c]).map(c => `${c}:${por[c]}`).join(' ');
    }
    if (typeof ajusteAviso === 'function') ajusteAviso('cobre: ' + txt);
}

// chamado dentro do draw(), com a transformacao do mundo ja aplicada
function desenharCobre() {
    if (!cobreDados || !cobreLigado || typeof currentNet === 'undefined' || !currentNet) return;
    if (currentNet === 'GND') return;                      // o plano de terra cobre a placa inteira
    const cru = typeof malhaCrua === 'function' ? malhaCrua(currentNet) : currentNet;
    const m = cobreMalha(cru);
    if (!m) return;
    push();
    noFill();
    const piscar = (frameCount % 60) < 45 ? 230 : 150;
    // internas primeiro, topo/fundo por cima
    const ts = m.t.slice().sort((a, b) => (a[0] === 1 || a[0] >= 16) - (b[0] === 1 || b[0] >= 16));
    for (const [cam, x1, y1, x2, y2, w] of ts) {
        if (cobreCamada && cam !== cobreCamada) continue;
        const c = cobreCor(cam);
        stroke(c[0], c[1], c[2], piscar);
        strokeWeight(Math.max(w, 1.2 / scaleFactor));
        line(x1, y1, x2, y2);
    }
    stroke(255, 255, 255, 220);
    strokeWeight(1 / scaleFactor);
    fill(0, 0, 0, 120);
    for (const [x, y, d, ca, cb] of m.v) {
        if (cobreCamada && cobreCamada !== ca && cobreCamada !== cb) continue;   // via que toca a camada
        ellipse(x, y, Math.max(d, 3 / scaleFactor));
    }
    pop();
}
