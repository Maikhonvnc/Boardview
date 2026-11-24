// Porta do consenso.py para o service worker (sw.js). A regra e a do consenso.py; o teste
// testes/test_consenso_js.py compara os dois — mudou um, mude o outro.
var Consenso = (function () {
    const TOL = { diodo: [0.025, 0.04], tensao: [0.05, 0.03] };
    const chaveTecnico = t => String(t || '').normalize('NFKD').replace(/\p{M}/gu, '')
        .toLowerCase().replace(/ß/g, 'ss').split(/\s+/).filter(Boolean).join(' ');
    const chaveOS = o => chaveTecnico(o)
        .replace(/^o\.?s\.?(?![a-z])[\s.:#°-]*(no?(?![a-z])[\s.:#°-]*)?/, '').replace(/[^0-9a-z]/g, '');
    const uniq = xs => [...new Set(xs)].sort();

    function votos(linhas) {
        linhas = [...linhas].sort((a, b) => a.seq - b.seq);
        const canceladas = new Set(linhas.filter(r => r.evento === 'retira' && r.cancela).map(r => r.cancela));
        const ultimo = new Map();
        for (const r of linhas) {
            if (r.evento !== 'medida' || canceladas.has(r.uuid)) continue;
            if (r.papel !== 'ref' || !chaveOS(r.os) || r.momento === 'boot') continue;
            ultimo.set(JSON.stringify([chaveTecnico(r.tecnico), chaveOS(r.os)]), r);
        }
        return [...ultimo.values()].map(r => ({ tecnico: chaveTecnico(r.tecnico), os: chaveOS(r.os), valor: r.valor,
            valor_num: r.valor_num, categoria: r.categoria }));
    }
    function grupos(tipo, vs) {
        const tol = v => Math.max(TOL[tipo][0], Math.abs(v) * TOL[tipo][1]);
        const gs = [], ol = vs.filter(v => v.categoria === 'OL');
        if (ol.length) gs.push({ tipo: 'OL', votos: ol });
        let atual = [];
        for (const v of vs.filter(v => v.categoria === 'num').sort((a, b) => a.valor_num - b.valor_num)) {
            const u = atual[atual.length - 1];
            if (u && v.valor_num - u.valor_num > tol(u.valor_num)) { gs.push({ tipo: 'num', votos: atual }); atual = []; }
            atual.push(v);
        }
        if (atual.length) gs.push({ tipo: 'num', votos: atual });
        for (const g of gs) {
            const xs = g.votos.map(v => v.valor_num).filter(x => x != null).sort((a, b) => a - b), k = xs.length >> 1;
            g.n = g.votos.length; g.os = uniq(g.votos.map(v => v.os)); g.tecnicos = uniq(g.votos.map(v => v.tecnico));
            g.mediana = xs.length ? (xs.length % 2 ? xs[k] : (xs[k - 1] + xs[k]) / 2) : null;
            g.min = xs.length ? xs[0] : null; g.max = xs.length ? xs[xs.length - 1] : null;
        }
        return gs.sort((a, b) => b.n - a.n);
    }
    function calcular(tipo, linhas) {
        const vs = votos(linhas);
        if (!vs.length) return { estado: 'sem_dados', n_votos: 0, n_os: 0, grupos: [] };
        const gs = grupos(tipo, vs), p = gs[0], outros = gs.slice(1);
        let estado = 'nao_confirmado';
        if (vs.length > 1) {
            if (outros.length && outros[0].n === p.n) estado = 'divergente';
            else if (p.n >= 2) estado = p.n >= 3 && p.os.length >= 2 ? 'validado' : 'confirmado';
        }
        const valor = g => g.tipo === 'OL' ? 'OL' : g.mediana;
        const r = { estado, n_votos: vs.length, n_os: new Set(vs.map(v => v.os)).size,
            grupos: gs.map(g => ({ valor: valor(g), n: g.n, min: g.min, max: g.max, os: g.os, tecnicos: g.tecnicos })) };
        if (estado !== 'divergente') {
            r.valor = valor(p); r.faixa = [p.min, p.max];
            r.fora = outros.flatMap(g => g.votos.map(v => v.valor));
        }
        return r;
    }
    function porPlaca(linhas) {
        const pontos = new Map();
        for (const r of linhas) {
            const k = JSON.stringify([r.fp, r.alvo, r.tipo, r.tipo === 'tensao' ? (r.alimentacao || '') : '']);
            if (!pontos.has(k)) pontos.set(k, []);
            pontos.get(k).push(r);
        }
        const saida = {};
        for (const [k, ls] of pontos) {
            const [fp, alvo, tipo, cond] = JSON.parse(k), c = calcular(tipo, ls);
            if (c.estado === 'sem_dados') continue;
            (((saida[fp] ??= {})[alvo] ??= {})[tipo] ??= {})[cond] = c;
        }
        return saida;
    }
    return { TOL, porPlaca, chaveOS, chaveTecnico };
})();
if (typeof module !== 'undefined') module.exports = Consenso;
