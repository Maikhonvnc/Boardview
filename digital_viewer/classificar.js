// Modo CLASSIFICAR (tecla Q): dizer o que cada componente e, rapido e em lote.
//
// Ao ligar, cada peca ganha um PALPITE pela topologia (cor fraca): 2 pinos com um no
// GND = capacitor; 2 pinos entre duas malhas = resistor; 2 pinos grandes = indutor;
// 4 pinos com 2 numa malha e 2 no GND = chave (botao); 3 pinos = transistor; poucos
// pinos com varios na mesma malha = MOSFET; resto = CI. Voce CONFIRMA (cor cheia):
//
//   1..9, 0   escolhe o "pincel": 1 cap 2 res 3 ind 4 cristal 5 diodo 6 transistor
//             7 MOSFET 8 CI 9 conector 0 apagar (volta a ser so palpite)
//   clique    pinta a peca com o pincel (sem pincel: so mostra o que ela e)
//   Shift+arrastar   pinta todas as pecas dentro do retangulo
//   X         pinta todas as pecas IGUAIS a ultima clicada (mesmos pinos, mesmo
//             tamanho, mesmo numero de pinos no GND) — "todos os capacitores assim"
//   Enter     aceita todos os palpites ainda nao conferidos
//   U         valor da ultima peca (ex.: 10uF, 4R7, 24MHz)
//   N / M     nome da peca (ex.: "2A", "S1") / da malha — continuam valendo aqui
//   Q / Esc   sai
//
// Capacitor recebe um valor ESTIMADO pelo tamanho (marcado com ~). E chute: confira.
//
// Onde fica salvo: o servidor grava em build/anotacoes/<placa>.json (POST
// /api/anotacoes) — vale para todo navegador que abrir a placa. Os nomes dados com
// N e M tambem vao para la. Sem servidor, as mudancas esperam numa fila do navegador.

const CLASS_TIPOS = {
    cap:    { nome: 'capacitor',  cor: [56, 189, 248] },
    res:    { nome: 'resistor',   cor: [250, 204, 21] },
    ind:    { nome: 'indutor',    cor: [168, 85, 247] },
    xtal:   { nome: 'cristal/osc', cor: [236, 72, 153] },
    diodo:  { nome: 'diodo',      cor: [249, 115, 22] },
    trans:  { nome: 'transistor', cor: [74, 222, 128] },
    mosfet: { nome: 'MOSFET',     cor: [239, 68, 68] },
    ci:     { nome: 'CI',         cor: [148, 163, 184] },
    con:    { nome: 'conector',   cor: [45, 212, 191] },
    chave:  { nome: 'chave/botão', cor: [255, 255, 255] },
    pad:    { nome: 'pad de teste', cor: [120, 120, 120] },
    // posicao sem peca (a DJI nao monta em algumas versoes): V diz em qual, ex.: "falta no Mini SE"
    vazio:  { nome: 'sem componente', cor: [255, 0, 255] },
};
// letra (mouse em cima da peca, ou com pecas selecionadas) -> tipo; null = apagar
const CLASS_TECLAS = { c: 'cap', r: 'res', b: 'ind', y: 'xtal', d: 'diodo', t: 'trans',
                       f: 'mosfet', i: 'ci', j: 'con', s: 'chave', p: 'pad', x: 'vazio',
                       delete: null, backspace: null };

let modoClass = false;
let classPincel;             // ultimo tipo usado (so para o painel)
let classSel = new Set();    // pecas selecionadas com Shift+arrastar
let classUltima = null;      // ultima peca clicada (para X e U)
let classRet = null;         // retangulo do Shift+arrastar, em coordenadas do mundo
let anot = { tipos: {}, nomes: {}, malhas: {}, sugestoes: {} };
let classCache = null;       // Map peca -> {caixa, passo, gnd, n, assin, sug}

function anotChave() { return 'anot_fila_' + (typeof boardKey !== 'undefined' ? boardKey : '?'); }
function origDe(p) { return p.nomeOriginal || p.name; }
function netCru(q) { return q.netOriginal || q.net; }

// --- palpite --------------------------------------------------------------------
function classMedidas(p) {
    const ps = p.pins || [];
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const q of ps) {
        const r = q.radius || 4;
        x0 = Math.min(x0, q.x - r); y0 = Math.min(y0, q.y - r);
        x1 = Math.max(x1, q.x + r); y1 = Math.max(y1, q.y + r);
    }
    const passo = ps.length === 2 ? Math.hypot(ps[0].x - ps[1].x, ps[0].y - ps[1].y) : 0;
    const gnd = ps.filter(q => netCru(q) === 'GND').length;
    return { caixa: [x0, y0, x1, y1], passo, gnd, n: ps.length,
             assin: `${ps.length}|${Math.round(passo)}|${gnd}|${Math.round(Math.max(x1 - x0, y1 - y0) / 4)}` };
}

function classSugerir(p, m) {
    const ps = p.pins || [];
    const conta = {};
    for (const q of ps) { const n = netCru(q); conta[n] = (conta[n] || 0) + 1; }
    const repet = Math.max(0, ...Object.entries(conta).filter(([n]) => n !== 'GND').map(([, c]) => c));
    if (m.n <= 1) return 'pad';
    if (m.n === 2) {
        if (m.passo >= 60 && m.gnd === 0) return 'ind';
        return m.gnd === 1 ? 'cap' : 'res';
    }
    if (m.n === 3) return 'trans';
    if (m.n === 4 && m.gnd === 2 && repet === 2) return 'chave';
    if (m.n === 4 && m.gnd >= 1 && (m.caixa[2] - m.caixa[0]) < 140) return 'xtal';
    if (m.n >= 5 && m.n <= 10 && repet >= 3) return 'mosfet';
    if (m.n >= 20 && m.gnd <= m.n / 3 && ps.every(q => (q.radius || 0) >= 8) && repet <= 2) return 'con';
    return 'ci';
}

// valor tipico de capacitor pelo passo entre os pinos (unidades do .bvr). Chute.
function classValorCap(passo) {
    if (passo < 14) return '~100nF';
    if (passo < 24) return '~1uF';
    if (passo < 40) return '~4.7-10uF';
    return '~22uF';
}

function classPreparar() {
    if (classCache || typeof parts === 'undefined') return;
    classCache = new Map();
    for (const p of parts) {
        const m = classMedidas(p);
        m.sug = classSugerir(p, m);
        classCache.set(p, m);
    }
}

function classTipo(p) {
    const a = anot.tipos[origDe(p)];
    // tipo que este navegador nao conhece (central com versao mais nova): cai no palpite
    if (a && CLASS_TIPOS[a.t]) return { t: a.t, v: a.v, ok: true, por: a.por, em: a.em };
    // sugestao do sugerir_placas.py: palpite mais forte, com motivo e nome sugerido
    const s = anot.sugestoes && anot.sugestoes[origDe(p)];
    if (s && CLASS_TIPOS[s.t]) return { t: s.t, v: s.v, ok: false, sug: true, nome: s.nome, motivo: s.motivo };
    const m = classCache && classCache.get(p);
    return m ? { t: m.sug, v: m.sug === 'cap' ? classValorCap(m.passo) : null, ok: false } : null;
}

// --- gravar ----------------------------------------------------------------------
function anotAplicarLocal(muds) {
    for (const [s, k, v] of muds) {
        if (!anot[s]) continue;
        if (v === null) delete anot[s][k]; else anot[s][k] = v;
    }
}

function anotFila() {
    try { return JSON.parse(localStorage.getItem(anotChave()) || '[]'); } catch (e) { return []; }
}

let anotEnviando = false;
function anotEnviar(muds) {
    if (typeof boardKey === 'undefined') return;
    if (muds && muds.length) {
        anotAplicarLocal(muds);
        const fila = anotFila();
        fila.push(...muds);
        try { localStorage.setItem(anotChave(), JSON.stringify(fila)); } catch (e) {}
    }
    if (anotEnviando) return;
    const fila = anotFila();
    if (!fila.length) return;
    anotEnviando = true;
    const lote = fila.slice(0, 5000);
    const postar = (muds) => fetch('/api/anotacoes/' + encodeURIComponent(boardKey), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mudancas: muds }),
    });
    const aviso = (t) => typeof ajusteAviso === 'function' && ajusteAviso(t);
    (async () => {
        let recusadas = 0;
        let r = await postar(lote);
        if (r.status === 400 || r.status === 413) {
            // servidor antigo recusa o LOTE inteiro por causa de uma mudanca: manda uma a
            // uma e descarta so a ruim, senao a fila ficava tentando para sempre
            for (const m of lote) {
                const r1 = await postar([m]);
                if (r1.status === 400 || r1.status === 413) recusadas++;
                else if (!r1.ok) throw new Error('servidor respondeu ' + r1.status);
            }
        } else if (!r.ok) {
            throw new Error('servidor respondeu ' + r.status);
        } else {
            const j = await r.json().catch(() => ({}));
            recusadas = (j.recusadas || []).length;
        }
        const resto = anotFila().slice(lote.length);   // o que entrou enquanto enviava fica
        try { localStorage.setItem(anotChave(), JSON.stringify(resto)); } catch (e) {}
        anotEnviando = false;
        if (recusadas) aviso(`${recusadas} marcação(ões) recusada(s) pelo servidor (versão diferente do programa?)`);
        if (resto.length) anotEnviar();
    })().catch(e => {
        anotEnviando = false;
        aviso('classificação NÃO gravou no servidor (' + e.message + ') — fica na fila');
    });
}

function anotCarregar() {
    if (typeof boardKey === 'undefined') return;
    // pela API: na bancada o servidor busca o do central (e guarda copia)
    fetch('/api/anotacoes/' + encodeURIComponent(boardKey), { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(j => {
            if (j) for (const s of ['tipos', 'nomes', 'malhas', 'sugestoes']) anot[s] = Object.assign({}, j[s] || {});
            anotAplicarLocal(anotFila());   // o que ainda nao chegou no servidor vale por cima
            // nomes e apelidos gravados no servidor valem em qualquer navegador
            if (typeof nomesCustom !== 'undefined' && Object.keys(anot.nomes).length) {
                Object.assign(nomesCustom, anot.nomes);
                if (typeof aplicarNomes === 'function') aplicarNomes();
            }
            if (Object.keys(anot.malhas).length && typeof apelidoMalha === 'function') {
                apelidoMalha('');                                // cria o cache .locais
                Object.assign(apelidoMalha.locais, anot.malhas);
                if (typeof reaplicarApelidos === 'function') reaplicarApelidos();
            }
            classPainel();
        }).catch(() => {});
}

// --- pintar --------------------------------------------------------------------------
// cada marcacao leva QUEM marcou e quando (o nome e o mesmo do caderno)
function classAssinar(t, v) {
    const o = { t, por: classTecnico, em: new Date().toISOString().slice(0, 19) };
    if (v) o.v = v;
    return o;
}
let classTecnico = '';
function classPedirTecnico() {
    classTecnico = typeof cadernoGarantirTecnico === 'function' ? cadernoGarantirTecnico() : 'anonimo';
    return !!classTecnico;
}

function classPintar(lista, tipo) {
    if (!classPedirTecnico()) return 0;
    const muds = [];
    for (const p of lista) {
        const k = origDe(p);
        const atual = anot.tipos[k];
        if (tipo === null) { if (atual) muds.push(['tipos', k, null]); continue; }
        // mesmo tipo de novo: mantem o valor que ja tinha (R010, 10uF...)
        const v = (atual && atual.t === tipo && atual.v)
            || (tipo === 'cap' ? classValorCap(classCache.get(p).passo) : undefined);
        if (!atual || atual.t !== tipo || atual.v !== v) muds.push(['tipos', k, classAssinar(tipo, v)]);
        muds.push(...classResolverSugestao(p, tipo));
    }
    if (muds.length) anotEnviar(muds);
    classPainel();
    return muds.length;
}

// Peca debaixo do mouse: entre as caixas que contem o ponto, a que tem o PINO mais
// perto. Escolher "a menor caixa" pegava um capacitor sobreposto em cima de um BGA e o
// N renomeava a peca errada.
// Conferir uma peca que tinha sugestao: a sugestao sai; se o tecnico CONFIRMOU o mesmo
// tipo e a peca nao tem nome, o nome sugerido ("BUCK Net29", "PMIC?") vira o nome.
function classResolverSugestao(p, tipo) {
    const k = origDe(p), s = anot.sugestoes && anot.sugestoes[k];
    if (!s) return [];
    const muds = [['sugestoes', k, null]];
    if (s.nome && s.t === tipo && typeof nomesCustom !== 'undefined' && !nomesCustom[k]) {
        nomesCustom[k] = s.nome;
        muds.push(['nomes', k, s.nome]);
        if (typeof nomesSalvar === 'function') nomesSalvar();
        if (typeof aplicarNomes === 'function') aplicarNomes();
    }
    return muds;
}

function classPecaEm(wx, wy) {
    let melhor = null, dist = Infinity;
    for (const [p, m] of classCache) {
        const [x0, y0, x1, y1] = m.caixa;
        if (wx < x0 || wx > x1 || wy < y0 || wy > y1) continue;
        for (const q of p.pins || []) {
            const d = Math.hypot(q.x - wx, q.y - wy) - (q.radius || 0);
            if (d < dist) { dist = d; melhor = p; }
        }
    }
    return melhor;
}

function classDescrever(p) {
    const t = classTipo(p);
    const nome = typeof nomeExibido === 'function' ? nomeExibido(p) : p.name;
    const quem = t && t.ok ? (t.por ? ` — marcado por ${t.por}${t.em ? ' em ' + t.em.slice(0, 10) : ''}` : '')
        : t && t.sug ? ` (SUGESTÃO${t.nome ? ' "' + t.nome + '"' : ''}: ${t.motivo})` : ' (palpite)';
    const tipo = t ? CLASS_TIPOS[t.t].nome + (t.v ? ' ' + t.v : '') + quem : '?';
    return `${nome}${nome !== origDe(p) ? ' (' + origDe(p) + ')' : ''}: ${tipo}`;
}

// chamado do mousePressed/Dragged/Released (SCRIPT3.js); true = o modo tratou
function classMouse(fase) {
    if (!modoClass || !classCache) return false;
    const w = screenToWorld(mouseX, mouseY);
    const aviso = (t) => typeof ajusteAviso === 'function' && ajusteAviso(t);
    if (fase === 'press') {
        if (keyIsDown(16)) { classRet = [w.x, w.y, w.x, w.y]; return true; }
        const p = classPecaEm(w.x, w.y);
        if (!p) { if (classSel.size) { classSel.clear(); aviso('seleção limpa'); } return false; }
        classUltima = p;
        aviso(classDescrever(p));
        return false;                         // deixa o viewer selecionar o pino tambem
    }
    if (fase === 'drag' && classRet) { classRet[2] = w.x; classRet[3] = w.y; return true; }
    if (fase === 'release' && classRet) {
        const [ax, ay, bx, by] = classRet;
        classRet = null;
        const x0 = Math.min(ax, bx), x1 = Math.max(ax, bx), y0 = Math.min(ay, by), y1 = Math.max(ay, by);
        for (const [p, m] of classCache)
            if (m.caixa[0] >= x0 && m.caixa[2] <= x1 && m.caixa[1] >= y0 && m.caixa[3] <= y1) classSel.add(p);
        aviso(`${classSel.size} peça(s) selecionada(s) — aperte a letra do tipo (C, R, B...) · Esc limpa`);
        return true;
    }
    return false;
}

// --- teclado ---------------------------------------------------------------------
function classTeclado(e) {
    if (/input|textarea|select/i.test(e.target.tagName || '')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (k === 'q' || k === 'Q') { classModo(); e.preventDefault(); e.stopImmediatePropagation(); return; }
    if (!modoClass) return;
    const aviso = (t) => typeof ajusteAviso === 'function' && ajusteAviso(t);
    const kl = k.toLowerCase();
    if (k === 'N' && e.shiftKey) {             // Shift+N: nomes de esquema (C12, R40, U3...)
        classGerarNomes();
    } else if (kl === 'n') {
        // N renomeia a peca DEBAIXO DO MOUSE (fora do modo, o N do renomear.js usa a do
        // painel, que so muda clicando num pino — num CI grande o clique cai no corpo)
        const w = screenToWorld(mouseX, mouseY);
        const p = classPecaEm(w.x, w.y) || classUltima;
        if (!p) aviso('ponha o mouse em cima de uma peça');
        else if (typeof renomearComponente === 'function') { classUltima = p; renomearComponente(p); }
    } else if (k === 'Escape') {
        if (classSel.size) { classSel.clear(); aviso('seleção limpa'); } else classModo(false);
    } else if (kl in CLASS_TECLAS) {
        // vale para a selecao; sem selecao, para a peca debaixo do mouse
        const w = screenToWorld(mouseX, mouseY);
        const sob = classPecaEm(w.x, w.y);
        const alvo = classSel.size ? [...classSel] : (sob ? [sob] : []);
        if (!alvo.length) aviso('ponha o mouse em cima de uma peça (ou selecione com Shift+arrastar)');
        else {
            classPincel = CLASS_TECLAS[kl];
            const n = classPintar(alvo, classPincel);
            if (sob && !classSel.size) classUltima = sob;
            aviso(alvo.length === 1 ? classDescrever(alvo[0])
                  : `${n} peça(s) marcada(s) como ${classPincel ? CLASS_TIPOS[classPincel].nome : 'palpite'}`);
            classSel.clear();
        }
    } else if (kl === 'g') {
        // G = grupo: todas as pecas IGUAIS a da debaixo do mouse ganham o tipo dela
        const w = screenToWorld(mouseX, mouseY);
        const ref = classPecaEm(w.x, w.y) || classUltima;
        if (!ref) aviso('ponha o mouse em cima de uma peça');
        else {
            const ass = classCache.get(ref).assin;
            const iguais = [...classCache].filter(([, m]) => m.assin === ass).map(([p]) => p);
            const tipo = classTipo(ref).t;
            const n = classPintar(iguais, tipo);
            aviso(`${iguais.length} peça(s) iguais a ${origDe(ref)} — ${n} marcada(s) como ${CLASS_TIPOS[tipo].nome}`);
        }
    } else if (k === 'Enter') {
        const falta = [...classCache.keys()].filter(p => !anot.tipos[origDe(p)]);
        if (falta.length && confirm(`Aceitar o palpite de ${falta.length} peça(s) ainda não conferida(s)?`)
            && classPedirTecnico()) {
            anotEnviar(falta.flatMap(p => {
                const t = classTipo(p);
                return [['tipos', origDe(p), classAssinar(t.t, t.v)], ...classResolverSugestao(p, t.t)];
            }));
            classPainel();
            aviso(`${falta.length} palpite(s) aceito(s)`);
        }
    } else if (kl === 'v') {
        const w = screenToWorld(mouseX, mouseY);
        classUltima = classPecaEm(w.x, w.y) || classUltima;
        if (!classUltima) aviso('ponha o mouse em cima de uma peça');
        else {
            const t = classTipo(classUltima);
            const s = prompt(`Valor de ${origDe(classUltima)} (${CLASS_TIPOS[t.t].nome}) — ex.: 10uF, 4R7, 24MHz:`,
                             (t.v || '').replace(/^~/, ''));
            if (s !== null && classPedirTecnico()) {
                const v = s.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 20);
                anotEnviar([['tipos', origDe(classUltima), classAssinar(t.t, v)]]);
                classPainel();
                aviso(classDescrever(classUltima));
            }
        }
    } else if (k === '?') alert(CLASS_AJUDA);
    else return;                              // N, M e o resto seguem para os outros modulos
    e.preventDefault();
    e.stopImmediatePropagation();             // Enter/numeros nao chegam no viewer/ajuste
}

// --- nomes de esquema ----------------------------------------------------------------
// Os N70752 do .bvr nao dizem nada. Shift+N da a cada peca CONFERIDA que ainda nao tem
// nome um nome no padrao de esquema eletrico, numerado pela posicao (de cima para baixo,
// da esquerda para a direita, em faixas). Quem ja tem nome (dado com N) fica como esta;
// numero ja usado nao se repete. O N original continua aparecendo entre parenteses.
const CLASS_PREFIXO = { cap: 'C', res: 'R', ind: 'L', xtal: 'Y', diodo: 'D', trans: 'Q', mosfet: 'Q',
                        ci: 'U', con: 'J', chave: 'SW', pad: 'TP', vazio: 'NC' };

function classGerarNomes() {
    const aviso = (t) => typeof ajusteAviso === 'function' && ajusteAviso(t);
    if (typeof nomesCustom === 'undefined') return;
    const usados = {};                                         // prefixo -> maior numero ja usado
    for (const nome of Object.values(nomesCustom)) {
        const m = /^([A-Z]+)(\d+)$/.exec(nome);
        if (m) usados[m[1]] = Math.max(usados[m[1]] || 0, +m[2]);
    }
    const faixa = 120;                                         // altura da faixa (unidades do .bvr)
    const sem = [...classCache].filter(([p]) => anot.tipos[origDe(p)] && !nomesCustom[origDe(p)])
        .map(([p, m]) => ({ p, cx: (m.caixa[0] + m.caixa[2]) / 2, cy: (m.caixa[1] + m.caixa[3]) / 2 }))
        .sort((a, b) => Math.floor(a.cy / faixa) - Math.floor(b.cy / faixa) || a.cx - b.cx);
    if (!sem.length) {
        const palpites = [...classCache.keys()].filter(p => !anot.tipos[origDe(p)]).length;
        aviso(`as conferidas já têm nome — ${palpites} peça(s) ainda são só palpite: confira (ou Enter aceita todos) e aperte Shift+N de novo`);
        return;
    }
    if (!confirm(`Dar nome de esquema (C1, R1, U1...) a ${sem.length} peça(s) conferida(s) sem nome?\n` +
                 'Quem já tem nome fica como está. Dá para trocar depois com N.')) return;
    const muds = [];
    for (const { p } of sem) {
        const pre = CLASS_PREFIXO[anot.tipos[origDe(p)].t] || 'X';
        usados[pre] = (usados[pre] || 0) + 1;
        const nome = pre + usados[pre];
        nomesCustom[origDe(p)] = nome;
        muds.push(['nomes', origDe(p), nome]);
    }
    if (typeof nomesSalvar === 'function') nomesSalvar();
    if (typeof aplicarNomes === 'function') aplicarNomes();
    anotEnviar(muds);
    aviso(`${muds.length} peça(s) com nome novo`);
}

const CLASS_AJUDA =
    'CLASSIFICAR (Q liga/desliga)\n\n' +
    'Mouse em cima da peça + letra:\n' +
    '  C capacitor   R resistor   B bobina/indutor   Y cristal\n' +
    '  D diodo   T transistor   F MOSFET   I CI   J conector\n' +
    '  S chave/botão   P pad de teste   X sem componente (vazio)\n' +
    '  Del apagar\n\n' +
    '  Shift+arrastar . . seleciona várias; a letra vale para todas\n' +
    '  G . . . . . . . . . todas as peças IGUAIS à do mouse ganham o tipo dela\n' +
    '  Enter . . . . . . . aceita todos os palpites (só contorno)\n' +
    '  V . . . . . . . . . valor da peça do mouse (10uF, 4R7, 24MHz)\n' +
    '  N . . . . . . . . . nome da peça debaixo do mouse\n' +
    '  M . . . . . . . . . nome da malha do pino selecionado\n' +
    '  Shift+N . . . . . . nomes de esquema (C1, R1, U1...) nas conferidas sem nome\n' +
    '  Esc . . . . . . . . limpa a seleção; de novo, sai\n\n' +
    'Preenchido = conferido. Só contorno = palpite pela ligação.\n' +
    'Capacitor ganha valor estimado pelo tamanho (~): é chute.';

function classModo(ligar) {
    modoClass = ligar === undefined ? !modoClass : ligar;
    if (modoClass) { classPreparar(); classPincel = undefined; }
    classPainel();
    if (typeof ajusteAviso === 'function')
        ajusteAviso(modoClass ? 'CLASSIFICAR ligado — mouse em cima + letra (C R B Y D T F I J S P X), ? ajuda' : 'classificar desligado');
}

// --- painel com a contagem --------------------------------------------------------
let classCaixa = null;
function classPainel() {
    if (!classCaixa) {
        classCaixa = document.createElement('div');
        classCaixa.style.cssText = 'position:fixed; right:12px; bottom:84px; z-index:2000; background:rgba(0,0,0,.85);' +
            'color:#eee; border:1px solid #5f5f5f; border-radius:6px; padding:8px 10px; font:12px sans-serif; pointer-events:none';
        document.body.appendChild(classCaixa);
    }
    if (!modoClass || !classCache) { classCaixa.style.display = 'none'; return; }
    const ok = {}, sug = {};
    for (const p of classCache.keys()) {
        const t = classTipo(p);
        const alvo = t.ok ? ok : sug;
        alvo[t.t] = (alvo[t.t] || 0) + 1;
    }
    const conf = Object.values(ok).reduce((a, b) => a + b, 0);
    let h = `<b>CLASSIFICAR</b> — ${conf}/${classCache.size} conferidas<br>`;
    const teclas = {};
    for (const [k, t] of Object.entries(CLASS_TECLAS)) if (t) teclas[t] = k.toUpperCase();
    for (const [t, d] of Object.entries(CLASS_TIPOS)) {
        if (!ok[t] && !sug[t] && !teclas[t]) continue;
        const borda = classPincel === t ? 'outline:1px solid #fff;' : '';
        h += `<span style="${borda}"><span style="display:inline-block;width:9px;height:9px;` +
             `background:rgb(${d.cor.join(',')});margin-right:4px"></span>${teclas[t] ? teclas[t] + ' ' : ''}` +
             `${d.nome}: ${ok[t] || 0}${sug[t] ? ` <span style="opacity:.55">+${sug[t]}?</span>` : ''}</span><br>`;
    }
    h += `<span style="opacity:.6">${classSel.size ? classSel.size + ' selecionada(s) · ' : ''}mouse em cima + letra · ? ajuda</span>`;
    classCaixa.innerHTML = h;               // so texto nosso (tipos fixos e numeros)
    classCaixa.style.display = 'block';
}

// --- desenho (dentro do draw, com a transformacao do mundo aplicada) -------------
function classDesenhar() {
    if (!modoClass || !classCache) return;
    push();
    for (const [p, m] of classCache) {
        const t = classTipo(p);
        const c = CLASS_TIPOS[t.t].cor;
        const [x0, y0, x1, y1] = m.caixa;
        // conferido = preenchido leve; palpite = so contorno (a foto aparece por baixo)
        if (t.ok && t.t === 'vazio') {           // posicao vazia: X magenta, sem preencher
            noFill(); stroke(c[0], c[1], c[2], 230); strokeWeight(1.5 / scaleFactor);
            line(x0, y0, x1, y1); line(x0, y1, x1, y0);
        } else if (t.sug) {                      // sugestao: contorno forte e tracejado, sem preencher
            noFill(); stroke(c[0], c[1], c[2], 240); strokeWeight(2 / scaleFactor);
            drawingContext.setLineDash([4 / scaleFactor, 3 / scaleFactor]);
            rect(x0, y0, x1 - x0, y1 - y0);
            drawingContext.setLineDash([]);
            continue;
        } else if (t.ok) { fill(c[0], c[1], c[2], 70); stroke(c[0], c[1], c[2], 230); strokeWeight(1.5 / scaleFactor); }
        else { noFill(); stroke(c[0], c[1], c[2], 120); strokeWeight(1 / scaleFactor); }
        rect(x0, y0, x1 - x0, y1 - y0);
    }
    noFill();
    for (const p of classSel) {
        const [x0, y0, x1, y1] = classCache.get(p).caixa;
        stroke(255, 255, 0); strokeWeight(2 / scaleFactor);
        rect(x0, y0, x1 - x0, y1 - y0);
    }
    const w = screenToWorld(mouseX, mouseY);
    const sob = classPecaEm(w.x, w.y);
    if (sob) {
        const [x0, y0, x1, y1] = classCache.get(sob).caixa;
        stroke(255); strokeWeight(2.5 / scaleFactor);
        rect(x0, y0, x1 - x0, y1 - y0);
    }
    if (classRet) {
        const [ax, ay, bx, by] = classRet;
        fill(255, 255, 255, 30); stroke(255); strokeWeight(1 / scaleFactor);
        rect(Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay));
    }
    pop();
}

function classIniciar() {
    window.addEventListener('keydown', classTeclado, true);   // captura: antes do ajuste/viewer
    anotCarregar();
    anotEnviar();                                             // o que sobrou na fila de antes
    setInterval(() => anotEnviar(), 30000);
}
