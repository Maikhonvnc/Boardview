// "Servidor" do Boardview no GitHub Pages: responde no navegador os mesmos enderecos do
// servidor.py (/api/*, /ajuste/*, digital_viewer/build/*), guardando tudo no Supabase.
// O viewer nao sabe a diferenca. Quem manda no acesso e o banco (nuvem/esquema.sql).
importScripts('nuvem-config.js', 'consenso_nuvem.js');
const CFG = self.BV_NUVEM, RAIZ = new URL('./', self.location).pathname;
const C_SESSAO = 'bv-sessao', C_PLACAS = 'bv-placas', K_SESSAO = RAIZ + '__sessao', K_MANIFESTO = RAIZ + '__manifesto';
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json' } });
class Falha extends Error { constructor(status, msg) { super(msg); this.status = status; } }

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
    const u = new URL(e.request.url);
    if (u.origin !== self.location.origin) return;
    let f = null;
    if (u.pathname === K_SESSAO) f = () => sessaoRota(e.request);
    else if (u.pathname.startsWith('/api/')) f = () => api(e.request, u);
    else if (u.pathname.startsWith('/ajuste/')) f = () => ajuste(e.request, u);
    else if (u.pathname.startsWith(RAIZ + 'digital_viewer/build/'))
        f = () => arquivo(decodeURIComponent(u.pathname.slice((RAIZ + 'digital_viewer/build/').length)));
    if (f) e.respondWith(f().catch(err => json({ erro: err.message }, err.status || 503)));
});

// --- sessao --------------------------------------------------------------------------
async function lerSessao() {
    const r = await (await caches.open(C_SESSAO)).match(K_SESSAO);
    return r ? r.json() : null;
}
async function guardarSessao(s) {
    await (await caches.open(C_SESSAO)).put(K_SESSAO, json(s));
    return s;
}
async function sair() { await caches.delete(C_SESSAO); await caches.delete(C_PLACAS); manifestoP = null; }

async function sessaoRota(req) {
    if (req.method === 'POST') { await sair(); await guardarSessao(await req.json()); return json({ ok: true }); }
    if (req.method === 'DELETE') { await sair(); return json({ ok: true }); }
    const s = await lerSessao();
    return json({ nome: s ? s.nome : null });
}

let renovando = null;
function renovar(velha) {
    return renovando ||= (async () => {
        const agora = await lerSessao();
        if (agora && agora.access_token !== velha.access_token) return agora;   // outra chamada ja renovou
        const r = await fetch(CFG.url + '/auth/v1/token?grant_type=refresh_token', {
            method: 'POST', headers: { apikey: CFG.chave, 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: velha.refresh_token }) });
        if ([400, 401, 403].includes(r.status)) { await sair(); throw new Falha(401, 'entre de novo'); }
        if (!r.ok) throw new Falha(503, 'login fora do ar');
        const j = await r.json();
        return guardarSessao({ nome: velha.nome, access_token: j.access_token, refresh_token: j.refresh_token,
                               expira: Date.now() + j.expires_in * 1000 });
    })().finally(() => { renovando = null; });
}

async function supa(caminho, opts = {}) {
    let s = await lerSessao();
    if (!s) throw new Falha(401, 'sem login');
    if (!s.expira || s.expira < Date.now() + 60000) s = await renovar(s);
    const ir = t => fetch(CFG.url + caminho, Object.assign({}, opts, { cache: 'no-store',
        headers: Object.assign({ apikey: CFG.chave, Authorization: 'Bearer ' + t }, opts.headers) }));
    let r = await ir(s.access_token);
    if (r.status === 401) r = await ir((await renovar(s)).access_token);
    return r;
}

async function rpc(nome, corpo) {
    const r = await supa('/rest/v1/rpc/' + nome, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                   body: JSON.stringify(corpo) });
    if (r.ok) return r.json();
    throw new Falha([400, 401, 403, 413].includes(r.status) ? r.status : 503, 'banco respondeu ' + r.status);
}

// --- arquivos das placas (bucket privado) ----------------------------------------------
const baixar = c => supa('/storage/v1/object/authenticated/placas/' + c.split('/').map(encodeURIComponent).join('/'));
let manifestoP = null, manifestoEm = 0;
function manifesto() {                         // {caminho: sha256}; confere de novo a cada 10 min
    if (manifestoP && Date.now() - manifestoEm < 600000) return manifestoP;
    manifestoEm = Date.now();
    const p = (async () => {
        const c = await caches.open(C_PLACAS);
        let r = null;
        try { r = await baixar('manifesto.json'); }
        catch (e) { if (e.status === 401) throw e; }
        if (r && r.ok) { await c.put(K_MANIFESTO, r.clone()); return r.json(); }
        // sem internet / servidor fora: a ultima copia. Acesso negado (4xx) nao usa copia.
        const velho = (!r || r.status >= 500) && await c.match(K_MANIFESTO);
        if (velho) return velho.json();
        throw new Falha(r ? 403 : 503, 'sem acesso as placas');
    })();
    manifestoP = p;
    p.catch(() => { if (manifestoP === p) manifestoP = null; });
    return p;
}

async function arquivo(caminho) {
    if (!await lerSessao()) return json({ erro: 'sem login' }, 401);
    const aj = /^ajustes\/([A-Za-z0-9._-]+)\.json$/.exec(caminho);
    if (aj) {
        const d = await rpc('bv_ajuste', { p_placa: aj[1] });
        return d ? json(d) : json({}, 404);
    }
    const sha = (await manifesto())[caminho];
    if (!sha) return json({ erro: 'nao existe' }, 404);
    const c = await caches.open(C_PLACAS), chave = RAIZ + '__placa/' + encodeURIComponent(caminho);
    const guardado = await c.match(chave);
    if (guardado && guardado.headers.get('x-sha') === sha) return guardado;
    const r = await baixar(caminho);
    if (!r.ok) return json({ erro: 'arquivo: ' + r.status }, r.status);
    const resp = new Response(await r.blob(), { headers: { 'x-sha': sha,
        'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream' } });
    await c.put(chave, resp.clone()).catch(() => {});       // disco cheio: so nao guarda
    return resp;
}

// --- api -----------------------------------------------------------------------------
const PLACA = /^[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}$/;
const COLUNAS = ['seq', 'uuid', 'evento', 'placa', 'fp', 'alvo', 'tipo', 'papel', 'valor', 'valor_num', 'categoria',
    'alimentacao', 'momento', 'os', 'tecnico', 'criado_em', 'recebido_em', 'formato', 'cancela'];

async function api(req, u) {
    const p = decodeURIComponent(u.pathname), placa = u.searchParams.get('placa');
    const exigir = x => { if (!PLACA.test(x || '')) throw new Falha(400, 'placa invalida'); return x; };
    if (p === '/api/leituras' && req.method === 'POST')
        return json(await rpc('bv_inserir', { p_leituras: (await req.json()).leituras }));
    if (p === '/api/leituras') return json({ leituras: await rpc('bv_leituras', { p_placa: exigir(placa) }) });
    if (p === '/api/leituras.csv') return csv(await rpc('bv_leituras', { p_placa: exigir(placa) }));
    if (p === '/api/consenso') {
        const [info, ls] = await Promise.all([rpc('bv_arquivo', { p_placa: exigir(placa) }), rpc('bv_leituras', { p_placa: placa })]);
        if (!info) return json({ erro: 'placa desconhecida' }, 404);
        return json({ placa, fp: info.fp, origem: 'central', calculado_em: new Date().toISOString(),
                      tolerancia: Consenso.TOL, versoes: Consenso.porPlaca(ls) });
    }
    if (p === '/api/sync') return json({ papel: 'local', faltam: 0, erro: null, recusadas: 0 });
    let m = /^\/api\/arquivo\/(.+)$/.exec(p);
    if (m) {
        const info = await rpc('bv_arquivo', { p_placa: exigir(m[1]) });
        return info ? json(info) : json({}, 404);
    }
    m = /^\/api\/anotacoes\/(.+)$/.exec(p);
    if (m && req.method === 'POST')
        return json(await rpc('bv_gravar_anotacoes', { p_placa: exigir(m[1]), p_mudancas: (await req.json()).mudancas }));
    if (m) return json(Object.assign(await rpc('bv_anotacoes', { p_placa: exigir(m[1]) }), { origem: 'central' }));
    return json({ erro: 'nao existe' }, 404);
}

async function ajuste(req, u) {
    const placa = decodeURIComponent(u.pathname.slice('/ajuste/'.length)), d = await req.json(), limpo = {};
    if (req.method !== 'POST' || !PLACA.test(placa)) throw new Falha(400, 'ajuste invalido');
    for (const k of Object.keys(d))            // so as chaves DESTA placa, como o servidor.py
        if (k === 'troca|' + placa || (k.startsWith(placa + '|') && /^\d$/.test(k.slice(placa.length + 1)))) limpo[k] = d[k];
    return json(await rpc('bv_gravar_ajuste', { p_placa: placa, p_dados: limpo }));
}

function csv(ls) {
    const livre = new Set(['tecnico', 'os', 'alvo']);
    const cel = (c, x) => {
        x = x == null ? '' : String(x);
        if (livre.has(c) && /^\s*[=+\-@]/.test(x)) x = "'" + x;
        return /[;"\r\n]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x;
    };
    const linhas = [COLUNAS.join(';')].concat([...ls].reverse().map(r => COLUNAS.map(c => cel(c, r[c])).join(';')));
    return new Response('﻿' + linhas.join('\r\n') + '\r\n', { headers: { 'Content-Type': 'text/csv; charset=utf-8' } });
}
