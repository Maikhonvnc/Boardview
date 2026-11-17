// Caderno de bancada — fase 1 da plataforma de medicoes (ver PLATAFORMA.md).
//
// Cada leitura de tensao (V / Shift+V) e de diodo (D / Shift+D) vira um registro com
// quem mediu, a OS, a condicao e a malha CRUA, e vai para o disco pelo servidor
// (POST /api/leituras -> dados/medicoes.sqlite3).
//
// Nunca se perde uma leitura: ela entra PRIMEIRO numa fila no localStorage e so sai
// dela quando o servidor responde que gravou (ele so responde depois do commit). Sem
// servidor, fica na fila e e reenviada sozinha (a cada 30 s, ao voltar a rede e ao
// abrir o viewer). Reenviar nao duplica: o uuid e gerado aqui e o banco ignora repetido.
// Leitura que o servidor recusa sai da fila porque ele guarda a recusa no banco.
//
// Sem Shift = a placa da bancada (REPARO). Com Shift = placa BOA (REFERENCIA): so essas
// vao contar como voto na fase 2, e so com o numero da OS preenchido.

const CADERNO = {
    fila: 'caderno_fila', rejeitadas: 'caderno_rejeitadas', tecnico: 'caderno_tecnico',
    os: 'caderno_os', alim: 'caderno_alimentacao', momento: 'caderno_momento',
    ultimas: 'caderno_ultimas',    // ultima medida enviada por (alvo|tipo|papel)
};
let cadernoFp = null;          // impressao digital da placa aberta (GET /api/arquivo)
let cadernoEnviando = false;
let cadernoErro = null;        // ultimo erro de envio, para o status

function lsLer(k, padrao) {
    try { const v = localStorage.getItem(k); return v === null ? padrao : JSON.parse(v); }
    catch (e) { return padrao; }
}
function lsGravar(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; }
}

// crypto.randomUUID so existe em contexto seguro (https ou 127.0.0.1); por IP da rede
// em http ele some, entao ha o caminho manual com getRandomValues
function uuid4() {
    try { if (crypto.randomUUID) return crypto.randomUUID(); } catch (e) { /* segue */ }
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
const PAGINA = uuid4();        // marca as leituras desta aba (para completar o fp depois)

function cadernoAviso(txt) { if (typeof ajusteAviso === 'function') ajusteAviso(txt); }

// Corta por CARACTERE (Array.from), nao por unidade UTF-16: cortar um emoji ao meio
// deixava um pedaco solto que o servidor nao conseguia gravar.
function limparNome(s) {
    return Array.from(String(s || '').replace(/[\u0000-\u001f\u007f]/g, '').trim())
        .slice(0, 40).join('')
        .replace(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g, '')
        .trim();
}
// mesma regra do servidor: comeca por letra/numero, depois letras, numeros e . _ / - espaco
// O prefixo "OS" sai ("OS 123" -> "123"); o consenso.py normaliza de novo no voto
// (maiusculas, acento, pontuacao), entao leituras antigas com "OS 123" contam igual.
function limparOS(s) {
    return String(s || '').replace(/[^A-Za-z0-9 ._/-]/g, '').replace(/^[^A-Za-z0-9]+/, '')
        .replace(/^o\.?s\.?(?![a-z])[\s.:#-]*/i, '').slice(0, 30).trim();
}

// A leitura de ESTA placa (V/D, papel 'reparo') que esta na tela foi feita NESTA OS e
// nesta condicao? O localStorage e por modelo: sem isto o painel acusava a placa nova
// com o valor da anterior (revisao de outubro).
function cadernoLeituraAtual(net, tipo) {
    const alvo = alvoMedicao(net);
    const ult = alvo && lsLer(CADERNO.ultimas, {})[`${boardKey}|${alvo}|${tipo}|reparo`];
    if (!ult || (ult.os || null) !== (limparOS(lsLer(CADERNO.os, '')) || null)) return false;
    return tipo !== 'tensao' || (ult.alimentacao === lsLer(CADERNO.alim, 'fonte') &&
                                 ult.momento === lsLer(CADERNO.momento, 'estavel'));
}

// O nome vem ANTES do valor (setNetVoltage e anotarDiodo chamam isto primeiro): cancelar
// aqui cancela a leitura inteira, em vez de a tela mostrar um valor que nao foi anotado.
function cadernoGarantirTecnico() {
    let t = lsLer(CADERNO.tecnico, '');
    if (!t) {
        const s = prompt('Seu nome (fica salvo neste navegador e vai em cada leitura):', '');
        t = limparNome(s);
        if (t) lsGravar(CADERNO.tecnico, t);
    }
    if (!t) cadernoAviso('leitura cancelada: falta o nome do técnico');
    return t;
}

// Alvo da leitura: a malha CRUA (o apelido muda; o nome do arquivo nao). Pino sem
// malha (NC) nao se liga a nenhum outro, entao vira PECA.PINO — usando o pino CLICADO
// (window.pinoClicado), porque o clique num NC nao seleciona pino (selectedPin=null).
function alvoMedicao(net) {
    const cru = typeof malhaCrua === 'function' ? malhaCrua(net) : net;
    if (cru && cru !== 'NC') return cru;
    const pin = window.pinoClicado || (typeof selectedPin !== 'undefined' ? selectedPin : null);
    if (!pin || (pin.netOriginal || pin.net) !== 'NC' || typeof parts === 'undefined') return null;
    const dono = parts.find(p => (p.pins || []).includes(pin));
    return dono ? `${dono.nomeOriginal || dono.name}.${pin.number}` : null;
}

// Chamado por setNetVoltage (SCRIPT3.js) e anotarDiodo (diodo.js) DEPOIS de gravar a
// copia local. valor vazio/null = o tecnico apagou -> evento 'retira'.
function cadernoRegistrar({ tipo, papel, net, valor }) {
    const alvo = alvoMedicao(net);
    if (!alvo) {
        alert('Não consegui identificar o pino desta leitura: ela NÃO foi para o caderno.\n' +
              'Clique no pino de novo e repita.');
        return;
    }
    const tecnico = cadernoGarantirTecnico();
    if (!tecnico) return;
    const os = limparOS(lsLer(CADERNO.os, '')) || null;
    // a placa entra na chave: Net100 existe em varias placas, e sem ela uma leitura
    // igual em outra placa era ignorada e apagar numa cancelava a da outra
    const chave = `${boardKey}|${alvo}|${tipo}|${papel}`;
    const ultimas = lsLer(CADERNO.ultimas, {});
    const ult = ultimas[chave];
    // tensao depende da condicao: 3,3 V na fonte e 3,3 V na bateria sao leituras diferentes
    const alimAgora = tipo === 'tensao' ? lsLer(CADERNO.alim, 'fonte') : undefined;
    const momentoAgora = tipo === 'tensao' ? lsLer(CADERNO.momento, 'estavel') : undefined;
    if (valor) {
        // Enter num valor ja anotado (mesmo valor, mesma OS, mesma condicao): nao vira leitura nova
        if (ult && ult.valor === String(valor) && (ult.os || null) === os &&
            ult.alimentacao === alimAgora && ult.momento === momentoAgora) {
            cadernoAviso('leitura igual à já anotada — não gravei de novo');
            return;
        }
    } else if (!ult) {
        return;                 // apagar algo que este navegador nunca anotou: nada a cancelar
    } else if ((ult.os || null) !== os) {
        // o valor na tela e de OUTRA OS (outra placa): apagar limpa a tela, nao cancela
        // o voto daquela placa
        cadernoAviso('valor era de outra OS: limpei só da tela, o caderno continua com ele');
        return;
    }
    const ev = {
        uuid: uuid4(), evento: valor ? 'medida' : 'retira', placa: boardKey, fp: cadernoFp,
        pagina: PAGINA, alvo, tipo, papel, tecnico, criado_em: new Date().toISOString(),
    };
    if (valor) {
        ev.valor = String(valor);
        ev.os = os;
        if (tipo === 'tensao') {
            ev.alimentacao = lsLer(CADERNO.alim, 'fonte');
            ev.momento = lsLer(CADERNO.momento, 'estavel');
        }
    } else {
        // o 'retira' desfaz a medida anterior: leva o uuid dela e a OS/condicao DELA,
        // nao as do campo agora (a OS pode ter mudado no meio)
        ev.cancela = ult.uuid;
        ev.os = ult.os || null;
        if (tipo === 'tensao') { ev.alimentacao = ult.alimentacao; ev.momento = ult.momento; }
    }
    const fila = lsLer(CADERNO.fila, []);
    fila.push(ev);
    if (!lsGravar(CADERNO.fila, fila)) {
        alert('Não consegui guardar a leitura no navegador (armazenamento cheio ou bloqueado). ' +
              'Anote o valor no papel.');
        return;
    }
    if (valor) ultimas[chave] = { uuid: ev.uuid, valor: ev.valor, os, alimentacao: ev.alimentacao, momento: ev.momento };
    else delete ultimas[chave];
    lsGravar(CADERNO.ultimas, ultimas);
    if (papel === 'ref' && valor && !os) cadernoAviso('referência sem OS: fica no caderno, mas não vai contar como voto');
    cadernoPintar();
    cadernoEnviar();
}

// Trocou a OS = outra placa na bancada. Os valores de ESTA placa (V e D) sao por
// modelo no navegador; perguntar se limpa a tela (o caderno continua com tudo).
function cadernoTrocouDePlaca(osAntes) {
    const temV = typeof userVolts !== 'undefined' && Object.keys(userVolts).length;
    const dd = typeof diodosCarregar === 'function' ? diodosCarregar() : {};
    const temD = Object.values(dd).some(d => d && d.med != null);
    if (!temV && !temD) return;
    if (!confirm(`OS mudou (era ${osAntes}). Limpar da tela as tensões e diodos da placa anterior?
` +
                 '(as referências e o caderno não mudam)')) return;
    if (temV) { for (const k of Object.keys(userVolts)) delete userVolts[k]; saveUserVolts(); }
    if (temD) {
        for (const k of Object.keys(dd)) { if (dd[k]) delete dd[k].med; if (dd[k] && dd[k].ref == null) delete dd[k]; }
        diodosSalvar(dd);
    }
    if (typeof painelRepintar === 'function') painelRepintar();
    if (typeof redraw === 'function') redraw();
}

async function cadernoPostar(lote) {
    const r = await fetch('/api/leituras', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leituras: lote }),
    });
    return r.ok ? Object.assign({ ok: true, status: r.status }, await r.json()) : { ok: false, status: r.status };
}

async function cadernoEnviar() {
    if (cadernoEnviando) return;
    let fila = lsLer(CADERNO.fila, []);
    // completa o fp das leituras desta aba feitas antes de o fp chegar
    if (cadernoFp && fila.some(e => !e.fp && e.pagina === PAGINA)) {
        fila = fila.map(e => (!e.fp && e.pagina === PAGINA) ? Object.assign({}, e, { fp: cadernoFp }) : e);
        lsGravar(CADERNO.fila, fila);
    }
    // desta aba e ainda sem fp: espera o fp, para nao ser carimbada com outro arquivo
    const prontas = fila.filter(e => e.fp || e.pagina !== PAGINA);
    if (!prontas.length) { cadernoPintar(); return; }
    cadernoEnviando = true;
    let maisUmaVolta = false;
    try {
        const lote = prontas.slice(0, 200);
        let res = await cadernoPostar(lote);
        if (!res.ok && (res.status === 400 || res.status === 413)) {
            // o servidor recusa leitura por leitura; recusar o LOTE nao deveria
            // acontecer. Se acontecer, manda uma por vez para isolar a ruim, em vez de
            // travar a fila inteira atras dela.
            const junto = { ok: true, aceitas: [], rejeitadas: [] };
            for (const ev of lote) {
                const r1 = await cadernoPostar([ev]);
                if (r1.ok) { junto.aceitas.push(...(r1.aceitas || [])); junto.rejeitadas.push(...(r1.rejeitadas || [])); }
                else if (r1.status === 400 || r1.status === 413)
                    junto.rejeitadas.push({ uuid: ev.uuid, motivo: 'servidor recusou (' + r1.status + ')', local: true });
                else throw new Error('servidor respondeu ' + r1.status);
            }
            res = junto;
        }
        if (!res.ok) throw new Error('servidor respondeu ' + res.status);
        const feitos = new Set(res.aceitas || []);
        const recusadas = (res.rejeitadas || []).filter(x => x.uuid);
        if (recusadas.length) {
            const lista = lsLer(CADERNO.rejeitadas, []);
            for (const x of recusadas) {
                const ev = lote.find(e => e.uuid === x.uuid);
                if (ev) lista.push(Object.assign({}, ev, { motivo: x.motivo }));
            }
            const guardou = lsGravar(CADERNO.rejeitadas, lista.slice(-1000));
            for (const x of recusadas) {
                // recusa registrada no servidor pode sair da fila; a isolada aqui (local)
                // so sai se ficou guardada na lista
                if (!x.local || guardou) feitos.add(x.uuid);
            }
            cadernoAviso(`${recusadas.length} leitura(s) recusada(s) pelo servidor — veja no caderno`);
        }
        // rele a fila: pode ter entrado leitura nova enquanto o envio estava no ar
        const resto = lsLer(CADERNO.fila, []).filter(e => !feitos.has(e.uuid));
        lsGravar(CADERNO.fila, resto);
        cadernoErro = null;
        maisUmaVolta = resto.some(e => e.fp || e.pagina !== PAGINA) && feitos.size > 0;   // havia mais de 200
    } catch (e) {
        cadernoErro = String((e && e.message) || e);
    } finally {
        cadernoEnviando = false;
        cadernoPintar();
    }
    if (maisUmaVolta) setTimeout(cadernoEnviar, 0);
    // gravou: o voto pode ter mudado o consenso (na bancada, da tempo de chegar no central)
    else if (!cadernoErro) setTimeout(() => consensoBuscar().then(syncBuscar), 1500);
}

function cadernoBuscarFp() {
    if (cadernoFp || typeof boardKey === 'undefined') return Promise.resolve();
    return fetch('/api/arquivo/' + encodeURIComponent(boardKey))
        .then(r => r.ok ? r.json() : null)
        .then(j => { if (j && j.fp) cadernoFp = j.fp; })
        .catch(() => {});
}

// --- fase 2: consenso ("validado por N") e situacao do central ----------------------
// O consenso e calculado no servidor (consenso.py, o unico lugar da regra); aqui so se
// mostra. Na bancada ele vem do central, ou da copia guardada se o central estiver fora.
let consensoDados = null;      // GET /api/consenso
let consensoAssinatura = '';   // so repinta o painel quando o consenso da placa mudou
let syncSituacao = null;       // GET /api/sync: {papel: 'bancada'|'local', faltam, erro}

function painelRepintar() {
    if (typeof updateComponentInfo !== 'function' || typeof parteNoPainel === 'undefined' || !parteNoPainel) return;
    const pc = window.pinoClicado;
    const pin = (pc && (parteNoPainel.pins || []).includes(pc)) ? pc
        : (typeof selectedPin !== 'undefined' ? selectedPin : null);
    if (pin) updateComponentInfo(parteNoPainel, pin);
}

function consensoBuscar() {
    if (typeof boardKey === 'undefined') return Promise.resolve();
    return fetch('/api/consenso?placa=' + encodeURIComponent(boardKey), { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(j => {
            if (!j || !j.versoes || typeof j.versoes !== 'object') return;
            consensoDados = j;
            const ass = JSON.stringify([j.origem, cadernoFp && j.versoes[cadernoFp]]);
            if (ass !== consensoAssinatura) { consensoAssinatura = ass; painelRepintar(); }
        })
        .catch(() => {});
}

function syncBuscar() {
    return fetch('/api/sync', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(j => { if (j) { syncSituacao = j; cadernoPintar(); } })
        .catch(() => {});
}

function consensoNum(x) {
    if (typeof x === 'string') x = x.toUpperCase() === 'OL' ? 'OL' : parseFloat(x);
    if (x === 'OL') return 'OL';
    if (typeof x !== 'number' || !isFinite(x)) return '?';
    return String(Number(x.toFixed(3))).replace('.', ',');
}

// mesmo alvo que o caderno grava: malha crua, ou PECA.PINO num pino sem malha (NC)
function consensoAlvo(pin) {
    const cru = pin.netOriginal || pin.net;
    if (cru && cru !== 'NC') return cru;
    if (typeof parts === 'undefined') return null;
    const dono = parts.find(p => (p.pins || []).includes(pin));
    return dono ? `${dono.nomeOriginal || dono.name}.${pin.number}` : null;
}

// a leitura DESTA placa (a da bancada) cai fora da faixa do consenso? Tolerancia vem do
// servidor (a mesma que agrupa os votos)
function consensoFora(c, tipo, meu) {
    if (meu == null || meu === '' || !c || !['validado', 'confirmado'].includes(c.estado)) return false;
    const m = String(meu).trim().replace(',', '.').toUpperCase();
    if (c.valor === 'OL' || m === 'OL') return (c.valor === 'OL') !== (m === 'OL');
    const x = parseFloat(m);
    if (!isFinite(x) || !Array.isArray(c.faixa)) return false;
    const tol = ((consensoDados && consensoDados.tolerancia) || {})[tipo] || [0, 0];
    const folga = (v) => Math.max(tol[0], Math.abs(v) * tol[1]);
    return x < c.faixa[0] - folga(c.faixa[0]) || x > c.faixa[1] + folga(c.faixa[1]);
}

function consensoTexto(c, un) {
    const votos = (k) => k === 1 ? '1 voto' : `${k} votos`;
    if (c.estado === 'divergente')
        return 'divergente: ' + (c.grupos || []).map(g => `${consensoNum(g.valor)}${un} (${g.n})`).join(' × ');
    let t = consensoNum(c.valor) + un;
    if (c.estado === 'nao_confirmado') return t + ' · 1 voto, falta confirmar';
    t += ` · ${c.estado} · ${votos(c.n_votos)} (${c.n_os} OS)`;
    if (Array.isArray(c.faixa) && c.faixa[0] !== c.faixa[1] && c.valor !== 'OL')
        t += ` · ${consensoNum(c.faixa[0])}–${consensoNum(c.faixa[1])}`;
    if (c.fora && c.fora.length) t += ` · fora: ${c.fora.map(consensoNum).join(', ')}`;
    return t;
}

// Linhas do painel para o pino (SCRIPT3 updateComponentInfo escapa o texto; a classe
// sai sempre desta lista fixa).
const CONSENSO_CLASSES = ['validado', 'confirmado', 'nao_confirmado', 'divergente', 'fora'];
function consensoLinhas(pin) {
    if (!pin || !consensoDados || !cadernoFp) return [];
    const v = (consensoDados.versoes || {})[cadernoFp];
    const alvo = v && consensoAlvo(pin);
    const ponto = alvo && v[alvo];
    if (!ponto) return [];
    const origem = consensoDados.origem === 'copia' ? ' (cópia, central fora)'
        : (consensoDados.aviso ? ' (só deste PC)' : '');
    const linhas = [];
    const alim = lsLer(CADERNO.alim, 'fonte') === 'bateria' ? 'bateria' : 'fonte';
    const ct = ponto.tensao && ponto.tensao[alim];
    if (ct) {
        const meu = typeof userVolts !== 'undefined' ? userVolts[pin.net] : null;
        const fora = cadernoLeituraAtual(pin.net, 'tensao') && consensoFora(ct, 'tensao', meu);
        linhas.push({ rotulo: `REF ${alim.toUpperCase()}:`, classe: fora ? 'fora' : ct.estado,
                      texto: consensoTexto(ct, ' V') + origem + (fora ? ` · ESTA PLACA ${meu} V ⚠` : '') });
    }
    const cd = ponto.diodo && ponto.diodo[''];
    if (cd) {
        const d = typeof diodoDe === 'function' ? diodoDe(pin.net) : null;
        const meu = d ? d.med : null;
        const fora = cadernoLeituraAtual(pin.net, 'diodo') && consensoFora(cd, 'diodo', meu);
        linhas.push({ rotulo: 'REF DIODO:', classe: fora ? 'fora' : cd.estado,
                      texto: consensoTexto(cd, '') + origem + (fora ? ` · ESTA PLACA ${meu} ⚠` : '') });
    }
    return linhas.map(l => Object.assign(l, { classe: CONSENSO_CLASSES.includes(l.classe) ? l.classe : 'nao_confirmado' }));
}

// --- painel ---------------------------------------------------------------------
function cadernoPintar() {
    const $ = (id) => document.getElementById(id);
    const tec = $('cadTecnico');
    if (tec) tec.textContent = lsLer(CADERNO.tecnico, '') || 'definir nome';
    const os = $('cadOS');
    if (os && document.activeElement !== os) os.value = lsLer(CADERNO.os, '');
    for (const [id, chave, padrao] of [['cadAlim', CADERNO.alim, 'fonte'], ['cadMomento', CADERNO.momento, 'estavel']]) {
        const atual = lsLer(chave, padrao);
        document.querySelectorAll(`#${id} button`).forEach(b => b.classList.toggle('on', b.dataset.v === atual));
    }
    const st = $('cadStatus');
    if (st) {
        const n = lsLer(CADERNO.fila, []).length;
        const rec = lsLer(CADERNO.rejeitadas, []).length;
        let txt, cls;
        if (n && cadernoErro) { txt = `${n} na fila · servidor fora, tentando de novo`; cls = 'pendente'; }
        else if (n && !cadernoFp) { txt = `${n} na fila · esperando o servidor`; cls = 'pendente'; }
        else if (n) { txt = `${n} na fila · enviando`; cls = 'pendente'; }
        else { txt = 'tudo salvo no disco'; cls = 'ok'; }
        // bancada: o que ainda nao chegou no servidor da empresa (fase 2)
        const s = syncSituacao;
        if (!n && s && s.papel === 'bancada') {
            if (s.faltam && s.erro) { txt += ` · ${s.faltam} esperando o central (fora do ar)`; cls = 'pendente'; }
            else if (s.faltam) txt += ` · ${s.faltam} indo para o central`;
            else if (s.erro) txt += ' · central fora do ar';
            else txt += ' · central em dia';
            // o central respondeu, mas NAO aceitou: nao e "em dia" (programa/.bvr diferente?)
            if (s.recusadas) {
                txt += ` · ⚠ central RECUSOU ${s.recusadas} leitura(s): ${s.recusa_motivo || '?'}`;
                cls = 'pendente';
            }
            if (s.erro_anotacoes) { txt += ' · classificação não subiu: ' + s.erro_anotacoes; cls = 'pendente'; }
        }
        st.textContent = txt;
        st.className = 'cad-status ' + cls;
        const r = $('cadRecusadas');
        if (r) { r.hidden = !rec; r.textContent = `${rec} recusada(s)`; }
    }
    const csv = $('cadCsv');
    if (csv && typeof boardKey !== 'undefined') csv.href = '/api/leituras.csv?placa=' + encodeURIComponent(boardKey);
}

// --- fase 3: anotacoes de antes do caderno ------------------------------------------
// As tensoes (uv_<placa>, chave = nome EXIBIDO), as referencias (uvref_<placa>, nome cru)
// e os diodos (dd_<placa>, {med, ref} por nome cru) feitos antes da fase 1 so existem
// neste navegador. Uma vez por placa, com a placa aberta (precisa das pecas para traduzir
// apelido -> malha crua) e o fp ja conhecido, oferece mandar tudo para a fila do caderno.
// Vao sem OS: entram no caderno, mas referencia sem OS nao conta como voto.
function cadernoMigrarAntigas() {
    if (typeof boardKey === 'undefined' || !cadernoFp) return;
    if (typeof parts === 'undefined' || !parts.length) return;
    const marca = 'caderno_migrado_' + boardKey;
    if (lsLer(marca, false)) return;
    const cru = (n) => typeof malhaCrua === 'function' ? malhaCrua(n) : n;
    const itens = [];                                    // [alvo, tipo, papel, valor]
    for (const [n, v] of Object.entries(lsLer('uv_' + boardKey, {})))
        if (v != null && v !== '') itens.push([cru(n), 'tensao', 'reparo', v]);
    for (const [n, v] of Object.entries(lsLer('uvref_' + boardKey, {})))
        if (v != null && v !== '') itens.push([n, 'tensao', 'ref', v]);
    for (const [n, d] of Object.entries(lsLer('dd_' + boardKey, {}))) {
        if (d && d.med != null && d.med !== '') itens.push([n, 'diodo', 'reparo', d.med]);
        if (d && d.ref != null && d.ref !== '') itens.push([n, 'diodo', 'ref', d.ref]);
    }
    const ultimas = lsLer(CADERNO.ultimas, {});
    const novos = itens.filter(([alvo, tipo, papel]) =>
        alvo && alvo !== 'GND' && !ultimas[`${boardKey}|${alvo}|${tipo}|${papel}`]);
    if (!novos.length) { lsGravar(marca, true); return; }
    const lista = novos.slice(0, 12).map(([a, t, p, v]) => `  ${a}  ${t}${p === 'ref' ? ' (ref)' : ''} = ${v}`).join('\n');
    if (!confirm(`Achei ${novos.length} anotação(ões) antiga(s) desta placa (${boardKey}) só neste navegador:\n\n` +
                 lista + (novos.length > 12 ? '\n  ...' : '') +
                 '\n\nMandar para o caderno (banco de medições)?')) {
        cadernoAviso('migração adiada — pergunto de novo ao reabrir a placa');
        return;
    }
    const tecnico = cadernoGarantirTecnico();
    if (!tecnico) return;
    const fila = lsLer(CADERNO.fila, []);
    const agora = new Date().toISOString();
    for (const [alvo, tipo, papel, v] of novos) {
        const ev = { uuid: uuid4(), evento: 'medida', placa: boardKey, fp: cadernoFp, pagina: PAGINA,
                     alvo, tipo, papel, tecnico, criado_em: agora, valor: String(v), os: null };
        if (tipo === 'tensao') { ev.alimentacao = lsLer(CADERNO.alim, 'fonte'); ev.momento = lsLer(CADERNO.momento, 'estavel'); }
        fila.push(ev);
        ultimas[`${boardKey}|${alvo}|${tipo}|${papel}`] =
            { uuid: ev.uuid, valor: ev.valor, os: null, alimentacao: ev.alimentacao, momento: ev.momento };
    }
    if (!lsGravar(CADERNO.fila, fila)) { alert('Não consegui guardar a migração no navegador.'); return; }
    lsGravar(CADERNO.ultimas, ultimas);
    lsGravar(marca, true);
    cadernoAviso(`${novos.length} anotação(ões) antiga(s) na fila do caderno`);
}

function cadernoIniciar() {
    const $ = (id) => document.getElementById(id);
    const tec = $('cadTecnico');
    if (tec) tec.onclick = (e) => {
        e.preventDefault();
        const s = prompt('Nome do técnico (fica salvo neste navegador):', lsLer(CADERNO.tecnico, ''));
        if (s === null) return;
        const t = limparNome(s);
        if (t) lsGravar(CADERNO.tecnico, t);
        cadernoPintar();
    };
    const os = $('cadOS');
    if (os) {
        os.addEventListener('input', () => lsGravar(CADERNO.os, limparOS(os.value)));
        let osAntes = limparOS(lsLer(CADERNO.os, ''));
        os.addEventListener('focus', () => { osAntes = limparOS(lsLer(CADERNO.os, '')); });
        os.addEventListener('change', () => {
            os.value = limparOS(os.value); lsGravar(CADERNO.os, os.value);
            if (osAntes && os.value !== osAntes) cadernoTrocouDePlaca(osAntes);
            osAntes = os.value;
        });
    }
    for (const [id, chave] of [['cadAlim', CADERNO.alim], ['cadMomento', CADERNO.momento]]) {
        document.querySelectorAll(`#${id} button`).forEach(b => b.addEventListener('click', (e) => {
            e.preventDefault(); lsGravar(chave, b.dataset.v); cadernoPintar();
            painelRepintar();          // a referencia de tensao mostrada depende de fonte/bateria
        }));
    }
    const rec = $('cadRecusadas');
    if (rec) rec.onclick = (e) => {
        e.preventDefault();
        const lista = lsLer(CADERNO.rejeitadas, []);
        const linhas = lista.slice(-15).map(x => `${x.tipo} ${x.alvo} = ${x.valor || '(apagar)'} → ${x.motivo}`);
        if (confirm('Leituras recusadas pelo servidor (últimas). O servidor também guarda as recusas.\n\n' +
                    linhas.join('\n') + '\n\nOK = limpar esta lista')) {
            lsGravar(CADERNO.rejeitadas, []); cadernoPintar();
        }
    };
    cadernoPintar();
    const ciclo = () => cadernoBuscarFp().then(cadernoMigrarAntigas).then(cadernoEnviar)
        .then(consensoBuscar).then(syncBuscar);
    ciclo();
    setInterval(ciclo, 30000);
    window.addEventListener('online', ciclo);
}
