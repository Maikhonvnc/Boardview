// Foto de fundo por METADE da placa, com ajuste manual de cada uma.
//
// Nestes .bvr as duas faces da placa sao duas ILHAS do mesmo contorno (todos os
// pinos sao lado T — nao existe lado B, entao os botoes TOP/BOTTOM nao separam as
// faces). E a foto do XZZ nao segue padrao: as vezes a face de cima esta na
// esquerda, as vezes na direita, as vezes empilhada.
//
// Por isso o fundo nao e uma imagem so: o foto_viewer.py grava uma imagem por
// metade (<placa>_s0.jpg, _s1.jpg) mais um <placa>_secoes.json com a caixa de cada
// uma em unidades do .bvr. Cada metade e desenhada na sua caixa e tem o seu proprio
// ajuste — mexer numa nao desalinha a outra, que era o problema de antes.
//
// Onde fica salvo: localStorage do navegador. A tecla E baixa um ajustes.json para
// guardar em digital_viewer/build/ — esse arquivo vale como padrao em qualquer
// navegador e o localStorage tem prioridade.

const AJUSTE_ZERO = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, fh: false, fv: false };
let modoAjuste = false;      // pega e arrasta direto, sem segurar Ctrl
let ajustes = {};            // "<placa>|<metade>" -> ajuste
let secoesFoto = [];         // [{box:[x0,y0,x1,y1], img, nome}]
let trocarMetades = false;   // troca qual imagem vai em qual caixa
let secaoAtiva = 0;          // metade que as teclas mexem (a ultima tocada)
let ajusteMsg = '';
let ajusteMsgAte = 0;

// --- estado -----------------------------------------------------------------

function ajusteChave(i) {
    return `${typeof boardKey !== 'undefined' ? boardKey : '?'}|${i}`;
}

function ajusteDe(i) {
    const k = ajusteChave(i);
    if (!ajustes[k]) ajustes[k] = Object.assign({}, AJUSTE_ZERO);
    return ajustes[k];
}

function ajusteAtual() { return ajusteDe(secaoAtiva); }

function ajusteSalvar() {
    ajusteMexeu = true;
    try {
        const tudo = Object.assign({}, ajustes);
        if (typeof boardKey !== 'undefined') tudo['troca|' + boardKey] = trocarMetades;
        localStorage.setItem('ajusteFundo', JSON.stringify(tudo));
    } catch (e) { /* navegador sem storage: vale so nesta sessao */ }
}

function ajusteCarregar() {
    const aplicar = (o) => {
        for (const k in o) {
            if (k.startsWith('troca|')) {
                if (k === 'troca|' + boardKey) trocarMetades = !!o[k];
            } else {
                ajustes[k] = Object.assign({}, AJUSTE_ZERO, o[k]);
            }
        }
    };
    try { aplicar(JSON.parse(localStorage.getItem('ajusteFundo') || '{}')); } catch (e) {}
    // O arquivo POR PLACA (gravado pelo servidor ao soltar o mouse) manda: e ele que
    // vale em qualquer navegador e sobrevive a regerar as fotos.
    const v = '?v=' + Date.now();
    fetch('build/ajustes/' + boardKey + '.json' + v)
        .then(r => r.ok ? r.json() : null)
        .then(o => { if (o) aplicar(o); })
        .catch(() => {});
    fetch('build/ajustes.json' + v).then(r => r.ok ? r.json() : {})
        .then(base => { for (const k in base) if (!(k in ajustes)) aplicar({ [k]: base[k] }); })
        .catch(() => {});
}

// --- carga das metades ------------------------------------------------------

function carregarSecoes() {
    const v = '?v=' + Date.now();      // sempre a versao nova apos regerar
    fetch('build/FOTO/' + boardKey + '_secoes.json' + v)
        .then(r => r.ok ? r.json() : null)
        .then(man => {
            if (!man || !man.secoes) return;
            secoesFoto = man.secoes.map(s => ({
                box: s.box, nome: s.img,
                img: loadImage('build/FOTO/' + s.img + v, () => {}, () => {})
            }));
            if (secoesFoto.length) {         // tem foto: comeca mostrando ela
                bgMode = 1; showBg = true;
                const tb = document.getElementById('toggleBgBtn');
                if (tb) rotular(tb, 'FOTO');
            }
        })
        .catch(() => {});
}

function imagemDaSecao(i) {
    if (!secoesFoto.length) return null;
    const j = (trocarMetades && secoesFoto.length === 2) ? (1 - i) : i;
    const s = secoesFoto[j];
    return (s && s.img && s.img.width) ? s.img : null;
}

// --- desenho ----------------------------------------------------------------

// Desenha as metades nas suas caixas. `bbox` e a bbox do contorno (do viewer).
function desenharSecoesFoto(bbox) {
    if (!secoesFoto.length) return false;
    // em face unica so entra a metade da face mostrada, e ela vai na caixa da ilha A
    const so = (typeof faceUnica !== 'undefined' && faceUnica) ? secaoDaFace() : null;
    for (let i = 0; i < secoesFoto.length; i++) {
        if (so !== null && i !== so) continue;
        const img = imagemDaSecao(i);
        if (!img || !img.width) continue;
        let b = secoesFoto[i].box; const a = ajusteDe(i);
        if (so !== null && window.__geoFaces) b = window.__geoFaces.caixaA;
        const dobrada = so === 1 && window.__geoFaces;   // a face B entra espelhada
        const w0 = b[2] - b[0], h0 = b[3] - b[1];
        const w = w0 * a.sx, h = h0 * a.sy;
        const x = b[0] + a.dx - (w - w0) / 2;
        // dentro do scale(1,-1) o y local vira -y na tela: a linha 0 da imagem
        // (o topo da foto) tem que cair no topo da caixa, b[3].
        const y = -b[3] - a.dy - (h - h0) / 2;
        push();
        scale(1, -1);
        const eh = (a.fh ? -1 : 1) * (dobrada && window.__geoFaces.eixo === 0 ? -1 : 1);
        const ev = (a.fv ? -1 : 1) * (dobrada && window.__geoFaces.eixo === 1 ? -1 : 1);
        if (a.rot) {                       // gira em torno do centro da propria metade
            translate(x + w / 2, y + h / 2);
            rotate(-a.rot);                // -: dentro do scale(1,-1) o sentido inverte
            translate(-(x + w / 2), -(y + h / 2));
        }
        if (eh < 0 || ev < 0) {
            translate(x + w / 2, y + h / 2);
            scale(eh, ev);
            translate(-(x + w / 2), -(y + h / 2));
        }
        image(img, x, y, w, h);
        pop();
    }
    return true;
}

// --- cursor cruzado: o mesmo ponto fisico na outra face ---------------------
//
// As duas metades sao a MESMA placa vista dos dois lados, ambas de frente. Entao o
// ponto correspondente na outra face e o espelho no eixo em que a placa esta
// dividida (medido nos contornos: divididas lado a lado casam espelhando em X,
// empilhadas casam espelhando em Y).
//
// Ressalva: leva PERTO, nao exato. As caixas das duas ilhas diferem 1-4% em
// proporcao, entao o alvo tem uma incerteza — por isso o marcador e um circulo, e
// nao um ponto: o ponto certo esta dentro dele, nao necessariamente no centro.

let cursorCruzado = false;

function eixoDaDivisao() {
    if (secoesFoto.length !== 2) return null;
    const a = secoesFoto[0].box, b = secoesFoto[1].box;
    return Math.abs(a[0] - b[0]) > Math.abs(a[1] - b[1]) ? 0 : 1;
}

function pontoNaOutraFace(wx, wy) {
    const eixo = eixoDaDivisao();
    if (eixo === null) return null;
    const i = secaoNoPonto(wx, wy), j = 1 - i;
    const a = secoesFoto[i].box, b = secoesFoto[j].box;
    let u = (wx - a[0]) / (a[2] - a[0]);
    let v = (wy - a[1]) / (a[3] - a[1]);
    if (u < -0.05 || u > 1.05 || v < -0.05 || v > 1.05) return null;  // fora da placa
    if (eixo === 0) u = 1 - u; else v = 1 - v;
    return { x: b[0] + u * (b[2] - b[0]), y: b[1] + v * (b[3] - b[1]), face: j };
}

function desenharCursorCruzado() {
    if (!cursorCruzado || secoesFoto.length !== 2) return;
    const w = screenToWorld(mouseX, mouseY);
    const alvo = pontoNaOutraFace(w.x, w.y);
    if (!alvo) return;
    const b = secoesFoto[alvo.face].box;
    const raio = 0.03 * Math.min(b[2] - b[0], b[3] - b[1]);   // a incerteza do espelho
    push();
    noFill();
    stroke(255, 0, 255);
    strokeWeight(2 / scaleFactor);
    ellipse(alvo.x, alvo.y, raio * 2, raio * 2);
    line(alvo.x - raio * 1.4, alvo.y, alvo.x + raio * 1.4, alvo.y);
    line(alvo.x, alvo.y - raio * 1.4, alvo.x, alvo.y + raio * 1.4);
    pop();
}

// --- qual metade o mouse esta tocando ---------------------------------------

function secaoNoPonto(wx, wy) {
    for (let i = 0; i < secoesFoto.length; i++) {
        const b = secoesFoto[i].box;
        if (wx >= b[0] && wx <= b[2] && wy >= b[1] && wy <= b[3]) return i;
    }
    // fora de todas: a mais proxima pelo centro
    let melhor = secaoAtiva, dmin = Infinity;
    for (let i = 0; i < secoesFoto.length; i++) {
        const b = secoesFoto[i].box;
        const d = Math.hypot(wx - (b[0] + b[2]) / 2, wy - (b[1] + b[3]) / 2);
        if (d < dmin) { dmin = d; melhor = i; }
    }
    return melhor;
}

function ajusteApontar(mx, my) {
    // em face unica so uma metade esta na tela: e nela que as teclas mexem
    if (typeof faceUnica !== 'undefined' && faceUnica) { secaoAtiva = secaoDaFace(); return secaoAtiva; }
    if (secoesFoto.length < 2) { secaoAtiva = 0; return 0; }
    const w = screenToWorld(mx, my);
    secaoAtiva = secaoNoPonto(w.x, w.y);
    return secaoAtiva;
}

// --- alteracoes -------------------------------------------------------------

function ajusteResumo() {
    const a = ajusteAtual();
    const esp = (a.fh ? 'H' : '') + (a.fv ? 'V' : '');
    return `metade ${secaoAtiva}${trocarMetades ? ' (trocadas)' : ''}  ` +
           `mover ${a.dx.toFixed(0)},${a.dy.toFixed(0)}  ` +
           `escala ${a.sx.toFixed(3)}x${a.sy.toFixed(3)}  ` +
           `giro ${(a.rot * 180 / Math.PI).toFixed(2)}` + String.fromCharCode(176) +
           (esp ? `  espelho ${esp}` : '');
}

function ajusteAviso(txt) { ajusteMsg = txt; ajusteMsgAte = millis() + 2500; }

function ajusteMover(dx, dy) {
    const a = ajusteAtual();
    a.dx += dx; a.dy += dy;
    ajusteSalvar(); ajusteAviso(ajusteResumo());
}

function ajusteEscalar(fator, eixo) {
    const a = ajusteAtual();
    if (eixo !== 'y') a.sx *= fator;
    if (eixo !== 'x') a.sy *= fator;
    ajusteSalvar(); ajusteAviso(ajusteResumo());
}

function ajusteEspelhar(eixo) {
    const a = ajusteAtual();
    if (eixo === 'h') a.fh = !a.fh; else a.fv = !a.fv;
    ajusteSalvar(); ajusteAviso(ajusteResumo());
}

function ajusteTrocar() {
    trocarMetades = !trocarMetades;
    ajusteSalvar();
    ajusteAviso(trocarMetades ? 'metades trocadas' : 'metades na ordem original');
}

function ajusteDigitarEscala() {
    // p/ erro grosso de proporcao, em que 0,4% por clique da roda levaria uma eternidade
    const a = ajusteAtual();
    const s = prompt(`Escala da metade ${secaoAtiva} (X Y, ou um numero para as duas):`,
                     `${a.sx.toFixed(4)} ${a.sy.toFixed(4)}`);
    if (s === null) return;
    const n = s.replace(',', '.').trim().split(/[\s;x]+/).map(parseFloat)
               .filter(v => v > 0.01 && v < 100);
    if (!n.length) { ajusteAviso('escala invalida'); return; }
    a.sx = n[0]; a.sy = n.length > 1 ? n[1] : n[0];
    ajusteSalvar(); ajusteAviso(ajusteResumo());
}

// --- desfazer / refazer ------------------------------------------------------
//
// A pilha guarda o estado ANTES de cada gesto, nao a cada pixel arrastado: um
// arrasto inteiro desfaz de uma vez, que e o que se espera de um Ctrl+Z.

let historico = [], futuro = [];
const HISTORICO_MAX = 60;

function ajusteInstantaneo() {
    return JSON.stringify({ a: ajustes, t: trocarMetades });
}

function ajusteRestaurar(txt) {
    const o = JSON.parse(txt);
    ajustes = {};
    for (const k in o.a) ajustes[k] = Object.assign({}, AJUSTE_ZERO, o.a[k]);
    trocarMetades = !!o.t;
}

function ajusteMarco() {
    // chamar ANTES de alterar: marca o ponto para onde o Ctrl+Z volta
    historico.push(ajusteInstantaneo());
    if (historico.length > HISTORICO_MAX) historico.shift();
    futuro.length = 0;                 // ramo novo: o que fora refeito se perde
}

function ajusteDesfazer() {
    if (!historico.length) { ajusteAviso('nada para desfazer'); return; }
    futuro.push(ajusteInstantaneo());
    ajusteRestaurar(historico.pop());
    ajusteSalvar(); ajusteSalvarSeMexeu();
    ajusteAviso('desfeito — ' + ajusteResumo());
}

function ajusteRefazer() {
    if (!futuro.length) { ajusteAviso('nada para refazer'); return; }
    historico.push(ajusteInstantaneo());
    ajusteRestaurar(futuro.pop());
    ajusteSalvar(); ajusteSalvarSeMexeu();
    ajusteAviso('refeito — ' + ajusteResumo());
}

function ajusteZerarPlaca() {
    ajusteMarco();
    for (const k in ajustes) if (k.startsWith(boardKey + '|')) delete ajustes[k];
    trocarMetades = false;
    ajusteSalvar(); ajusteSalvarSeMexeu();
    ajusteAviso('placa inteira de volta ao alinhamento automatico');
}


function ajusteCentroDaSecao() {
    // centro, em coordenadas de mundo, da metade que esta sendo ajustada
    const s = secoesFoto[secaoAtiva];
    if (!s) return null;
    let b = s.box;
    if (typeof faceUnica !== 'undefined' && faceUnica && window.__geoFaces) {
        b = window.__geoFaces.caixaA;
    }
    const a = ajusteDe(secaoAtiva);
    return { x: (b[0] + b[2]) / 2 + a.dx, y: (b[1] + b[3]) / 2 + a.dy };
}


let ajusteMexeu = false;

function ajusteSalvarSeMexeu() {
    if (!ajusteMexeu) return;
    ajusteMexeu = false;
    ajusteSalvarNoServidor();
}


function ajusteGirar(rad) {
    const a = ajusteAtual();
    a.rot += rad;
    ajusteSalvar(); ajusteAviso(ajusteResumo());
}


function ajusteSalvarNoServidor() {
    // o navegador nao escreve em disco; o servidor.py grava em build/ajustes/<placa>.json
    const corpo = {};
    for (const k in ajustes) {
        const a = ajustes[k];
        if (a.dx || a.dy || a.sx !== 1 || a.sy !== 1 || a.rot || a.fh || a.fv) corpo[k] = a;
    }
    if (trocarMetades) corpo['troca|' + boardKey] = true;
    fetch('/ajuste/' + encodeURIComponent(boardKey), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(corpo)
    }).then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(() => ajusteAviso('salvo em build/ajustes/' + boardKey + '.json'))
      .catch(() => ajusteAviso('nao consegui salvar no servidor (use E para baixar)'));
}


function ajusteZerar() {
    ajustes[ajusteChave(secaoAtiva)] = Object.assign({}, AJUSTE_ZERO);
    ajusteSalvar(); ajusteAviso('zerado — ' + ajusteResumo());
}

function ajusteExportar() {
    const limpo = {};
    for (const k in ajustes) {
        const a = ajustes[k];
        if (a.dx || a.dy || a.sx !== 1 || a.sy !== 1 || a.fh || a.fv) limpo[k] = a;
    }
    if (trocarMetades) limpo['troca|' + boardKey] = true;
    const blob = new Blob([JSON.stringify(limpo, null, 1)], { type: 'application/json' });
    const l = document.createElement('a');
    l.href = URL.createObjectURL(blob);
    l.download = 'ajustes.json';
    l.click();
    ajusteAviso('ajustes.json baixado — guarde em digital_viewer/build/');
}

// --- teclado ----------------------------------------------------------------

const AJUSTE_AJUDA =
    'Alinhar a foto aos pads. Tudo vale para a METADE em que o mouse esta.\n' +
    'Ao soltar o mouse o ajuste e gravado em build/ajustes/<placa>.json.\n\n' +
    'A . . . . . . . . . . . . liga/desliga o MODO AJUSTE\n\n' +
    'Com o modo ligado (pega e arrasta, sem segurar nada):\n' +
    '  arrastar . . . . . . . move a foto\n' +
    '  Shift + arrastar . . gira a foto\n' +
    '  roda . . . . . . . . . escala   (Shift = so X, segurar Y = so Y)\n\n' +
    'Sempre disponivel:\n' +
    '  Ctrl + arrastar . . move a foto (sem ligar o modo)\n' +
    '  Ctrl + roda . . . . escala\n' +
    '  [ e ] . . . . . . . . . gira fino (com Shift, 10x)\n' +
    '  H / J . . . . . . . . . espelha na horizontal / vertical\n' +
    '  T . . . . . . . . . . . troca as duas metades de lugar\n' +
    '  F . . . . . . . . . . . face unica: dobra as metades, um lado por vez\n' +
    '  C . . . . . . . . . . . cursor cruzado: o mesmo ponto na outra face\n' +
    '  S . . . . . . . . . . . digita a escala (X Y)\n' +
    '  setas . . . . . . . . move 1 px de tela (com Shift, 10)\n' +
    '  Ctrl+Z / Ctrl+Y . desfaz / refaz\n' +
    '  R . . . . . . . . . . . zera esta metade (Shift+R: a placa toda)\n' +
    '  E . . . . . . . . . . . baixa ajustes.json (copia de seguranca)';

function ajustePassoTela(sx, sy) {
    // a vista entra girada 180 e espelhada: um passo "para a direita na tela" nao e
    // +x no mundo. Converte pela mesma funcao que o arrasto usa.
    const a = screenToWorld(0, 0), b = screenToWorld(sx, sy);
    ajusteMover(b.x - a.x, b.y - a.y);
}

function ajusteTeclado(e) {
    if (/input|textarea/i.test((e.target.tagName || ''))) return;
    if (e.ctrlKey || e.metaKey) {                        // so Ctrl+Z e Ctrl+Y sao nossos
        const kz = (e.key || '').toLowerCase();
        if (kz === 'z' && !e.shiftKey) { e.preventDefault(); ajusteDesfazer(); }
        else if (kz === 'y' || (kz === 'z' && e.shiftKey)) { e.preventDefault(); ajusteRefazer(); }
        return;
    }
    if (e.altKey) return;                               // nao rouba atalho do navegador
    const passo = e.shiftKey ? 10 : 1;                   // pixels de TELA
    ajusteApontar(mouseX, mouseY);                       // a metade sob o mouse
    ajusteMarco();                                       // ponto de retorno do Ctrl+Z
    const k = e.key;
    if (k === 'ArrowLeft')            ajustePassoTela(-passo, 0);
    else if (k === 'ArrowRight')      ajustePassoTela(passo, 0);
    else if (k === 'ArrowUp')         ajustePassoTela(0, -passo);
    else if (k === 'ArrowDown')       ajustePassoTela(0, passo);
    else if (k === 'h' || k === 'H')  ajusteEspelhar('h');
    else if (k === 'j' || k === 'J')  ajusteEspelhar('v');
    else if (k === 't' || k === 'T')  ajusteTrocar();
    else if (k === 'a' || k === 'A')  ajusteModo();
    else if (k === '[')               ajusteGirar(-0.0005 * (e.shiftKey ? 10 : 1));
    else if (k === ']')               ajusteGirar(+0.0005 * (e.shiftKey ? 10 : 1));
    else if (k === 'f' || k === 'F')  aplicarFaceUnica(!faceUnica);
    else if (k === 'c' || k === 'C')  {
        cursorCruzado = !cursorCruzado;
        ajusteAviso(cursorCruzado ? 'cursor cruzado LIGADO — segue o mouse na outra face'
                                  : 'cursor cruzado desligado');
    }
    else if (k === 's' || k === 'S')  ajusteDigitarEscala();
    else if (k === 'r')               ajusteZerar();
    else if (k === 'R')               ajusteZerarPlaca();   // Shift+R
    else if (k === 'e' || k === 'E')  ajusteExportar();
    else if (k === '?')               alert(AJUSTE_AJUDA);
    else return;
    e.preventDefault();
    clearTimeout(window.__salvaTimer);           // grava depois de parar de teclar
    window.__salvaTimer = setTimeout(ajusteSalvarSeMexeu, 800);
}

function ajusteModo(ligar) {
    modoAjuste = ligar === undefined ? !modoAjuste : ligar;
    const b = document.getElementById('btnAjuste');
    if (b) {
        rotular(b, 'AJUSTE');
        b.classList.toggle('on', modoAjuste);   // o realce vem do CSS (.on)
    }
    ajusteAviso(modoAjuste
        ? 'AJUSTE ligado: arraste a foto, roda = escala, Shift+arrasta = girar'
        : 'ajuste desligado — arrastar volta a mover a vista');
}


function ajusteIniciar() {
    ajusteCarregar();
    carregarSecoes();
    window.addEventListener('keydown', ajusteTeclado);
    // Os dois botoes agora vem prontos no index.html (#btnAjuste e #btnDesfazer,
    // este ultimo ligado no skin.js). O ramo de criacao fica para um HTML sem eles.
    let b = document.getElementById('btnAjuste');
    if (!b) {
        const ctr = document.getElementById('controls');
        if (ctr) {
            b = document.createElement('button');
            b.type = 'button';
            b.id = 'btnAjuste';
            b.innerHTML = 'AJUSTE';
            b.title = 'Liga o modo de ajuste da foto (tecla A). Shift+clique mostra a ajuda.';
            ctr.appendChild(b);
        }
    }
    if (b) b.onclick = (e) => {
        e.preventDefault();
        if (e.shiftKey) alert(AJUSTE_AJUDA); else ajusteModo();
    };
}

// Aviso do ajuste. Era desenhado no canvas, no canto de baixo a esquerda — e ficava
// ATRAS do painel DADOS DETALHADOS, que e HTML por cima do canvas. Agora e HTML
// tambem, com z-index acima do painel e fora da coluna dele.
let ajusteCaixa = null;

function ajusteCaixaAviso() {
    if (ajusteCaixa) return ajusteCaixa;
    ajusteCaixa = document.createElement('div');
    ajusteCaixa.id = 'avisoAjuste';
    ajusteCaixa.style.cssText =
        'position:fixed; left:236px; bottom:12px; z-index:2000; display:none;' +
        'background:rgba(0,0,0,.85); color:#fffb03; border:1px solid #5f5f5f;' +
        'border-radius:4px; padding:6px 10px; font:14px sans-serif;' +
        'pointer-events:none; max-width:calc(100vw - 260px)';
    document.body.appendChild(ajusteCaixa);
    return ajusteCaixa;
}

function ajusteDesenharAviso() {
    const c = ajusteCaixaAviso();
    const visivel = ajusteMsg && millis() <= ajusteMsgAte;
    if (visivel) {
        if (c.textContent !== ajusteMsg) c.textContent = ajusteMsg;
        c.style.display = 'block';
    } else if (c.style.display !== 'none') {
        c.style.display = 'none';
    }
}
