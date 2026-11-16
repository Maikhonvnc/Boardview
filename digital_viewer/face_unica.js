// FACE UNICA: mostra a placa como ela e na mao — um lado por vez, no mesmo lugar.
//
// Como o .bvr vem: as duas faces estao lado a lado (ou empilhadas) como duas ILHAS
// do mesmo contorno, e TODOS os pinos sao PIN_SIDE T. Ou seja, o arquivo nao diz
// qual e a frente e qual e o verso, e o TOP/BOTTOM do viewer nao separava nada.
//
// O que este modo faz: dobra a segunda ilha por cima da primeira, espelhada no eixo
// em que a placa esta dividida — que e a relacao correta entre as duas faces de uma
// placa fotografada dos dois lados de frente (medido: sobrepondo os contornos, o
// encaixe espelhado ganha em 5 de 6 placas). Depois marca uma ilha como lado T e a
// outra como lado B, e ai os botoes TOP / BOTTOM / AMBOS que ja existiam passam a
// funcionar de verdade.
//
// Para que serve: um pad na frente e o ponto por onde a trilha desce ficam na MESMA
// posicao da tela. Vira o lado e voce esta olhando o outro extremo da mesma via —
// util justamente quando ela pode estar rompida.
//
// Ressalva: a dobra leva perto, nao exato. As caixas das duas ilhas diferem 1-4% em
// proporcao, entao sobra um erro dessa ordem entre um lado e outro.

let faceUnica = false;
let faceUnicaPronta = false;

function eixoEIlhas() {
    // As caixas das ilhas ja vem prontas do <placa>_secoes.json, calculadas pelo
    // Python (align_bvr.secoes_validas, que divide pelo vale de densidade de pinos e
    // descarta pedaco solto do contorno). Tentei redescobri-las aqui pelo maior vao
    // do contorno e deu errado — achava uma faixa fina em vez da divisao real.
    if (!secoesFoto || secoesFoto.length !== 2) return null;
    const a = secoesFoto[0].box, b = secoesFoto[1].box;
    const eixo = Math.abs(a[0] - b[0]) > Math.abs(a[1] - b[1]) ? 0 : 1;
    const corte = eixo === 0 ? (a[2] + b[0]) / 2 : (a[3] + b[1]) / 2;
    return { eixo, corte, caixaA: a, caixaB: b };
}

// leva um ponto da ilha B para o lugar correspondente na ilha A (dobra espelhada)
function dobrar(x, y, g) {
    const { eixo, caixaA: a, caixaB: b } = g;
    let u = (x - b[0]) / (b[2] - b[0]);
    let v = (y - b[1]) / (b[3] - b[1]);
    if (eixo === 0) u = 1 - u; else v = 1 - v;
    return { x: a[0] + u * (a[2] - a[0]), y: a[1] + v * (a[3] - a[1]) };
}

function prepararFaceUnica() {
    const g = eixoEIlhas();
    if (!g) return false;
    window.__geoFaces = g;
    const kx = (g.caixaA[2] - g.caixaA[0]) / (g.caixaB[2] - g.caixaB[0]);
    const ky = (g.caixaA[3] - g.caixaA[1]) / (g.caixaB[3] - g.caixaB[1]);
    const sinal = g.eixo === 0 ? [-kx, ky] : [kx, -ky];   // o espelho inverte um eixo

    for (const part of parts) {
        if (!part.pins.length) continue;
        const px = part.pins.reduce((s, p) => s + p.x, 0) / part.pins.length;
        const py = part.pins.reduce((s, p) => s + p.y, 0) / part.pins.length;
        const naA = (g.eixo === 0 ? px : py) < g.corte;
        part.faceU = naA ? 'T' : 'B';
        part.sideOrig = part.side;
        for (const pin of part.pins) {
            pin.x0 = pin.x; pin.y0 = pin.y;
            const q = naA ? { x: pin.x, y: pin.y } : dobrar(pin.x, pin.y, g);
            pin.xu = q.x; pin.yu = q.y;
            if (pin.outlineRelative) {
                pin.outlineRelative0 = pin.outlineRelative;
                pin.outlineRelativeU = naA ? pin.outlineRelative
                    : pin.outlineRelative.map((v, i) => v * (i % 2 === 0 ? sinal[0] : sinal[1]));
            }
        }
        // PART_OUTLINE_RELATIVE aqui vem em coordenadas absolutas; dobra igual aos pinos
        if (part.outline && part.outline.length >= 4) {
            part.outline0 = part.outline;
            if (naA) {
                part.outlineU = part.outline;
            } else {
                const o = part.outline.slice();
                for (let i = 0; i + 1 < o.length; i += 2) {
                    const q = dobrar(o[i], o[i + 1], g);
                    o[i] = q.x; o[i + 1] = q.y;
                }
                part.outlineU = o;
            }
        }
    }
    // contorno da placa: fica so o da ilha A (a silhueta passa a ser uma so)
    window.__outlineOrig = outlinePoints.slice();
    window.__outlineA = outlinePoints.filter(
        p => (g.eixo === 0 ? p.x : p.y) < g.corte);
    faceUnicaPronta = true;
    return true;
}

function aplicarFaceUnica(ligar) {
    if (ligar && !faceUnicaPronta && !prepararFaceUnica()) {
        ajusteAviso('esta placa nao tem duas metades — face unica nao se aplica');
        return false;
    }
    faceUnica = ligar;
    for (const part of parts) {
        if (part.faceU === undefined) continue;
        part.side = ligar ? part.faceU : (part.sideOrig || 'T');
        if (part.outlineU) part.outline = ligar ? part.outlineU : part.outline0;
        for (const pin of part.pins) {
            if (pin.xu === undefined) continue;
            pin.x = ligar ? pin.xu : pin.x0;
            pin.y = ligar ? pin.yu : pin.y0;
            if (pin.outlineRelativeU) {
                pin.outlineRelative = ligar ? pin.outlineRelativeU : pin.outlineRelative0;
            }
            if (pin.outline) delete pin.outline;   // recalculado no proximo desenho
        }
    }
    outlinePoints.length = 0;
    outlinePoints.push(...(ligar ? window.__outlineA : window.__outlineOrig));
    if (ligar && displayMode === 'all') displayMode = 'top';   // "ambos" separa de novo
    if (typeof renderBuffer === 'function') renderBuffer();
    if (typeof calcularTransformacion === 'function') calcularTransformacion();
    const b = document.getElementById('btnFaceUnica');
    if (b) rotular(b, ligar ? '1 FACE' : '2 FACES');
    ajusteAviso(ligar ? 'face unica: TOP e BOTTOM no mesmo lugar — vire com os botoes'
                      : 'de volta as duas metades lado a lado');
    return true;
}

// qual imagem de fundo entra em cada face, e onde
function secaoDaFace() {
    // em face unica, o lado mostrado manda: TOP = metade 0, BOTTOM = metade 1
    return displayMode === 'bottom' ? 1 : 0;
}

function botaoFaceUnica() {
    // o botao agora vem pronto no index.html (com icone); aqui so se liga o clique.
    // O ramo de criacao continua para o caso de um HTML sem ele.
    let b = document.getElementById('btnFaceUnica');
    if (!b) {
        const ctr = document.getElementById('controls');
        if (!ctr) return;
        b = document.createElement('button');
        b.type = 'button';
        b.id = 'btnFaceUnica';
        b.innerHTML = '2 FACES';
        b.title = 'Dobra as duas metades uma sobre a outra: um lado por vez, no mesmo lugar (tecla F)';
        ctr.appendChild(b);
    }
    b.onclick = (e) => { e.preventDefault(); aplicarFaceUnica(!faceUnica); };
}
