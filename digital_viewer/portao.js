// So age no GitHub Pages (na bancada, com o servidor.py, nao faz nada). Garante que o
// service worker (../sw.js) esta no comando e que ha login; senao manda para entrar.html.
// NAO e ele que protege as placas: e o banco (nuvem/esquema.sql).
(function () {
    if (!/\.github\.io$/.test(location.hostname) && location.port !== '8799') return;
    const entrar = () => location.replace('../entrar.html?volta=' + encodeURIComponent(location.href));
    const sw = navigator.serviceWorker;
    if (!sw) return entrar();
    if (!sw.controller) {                    // primeira visita ou Ctrl+F5
        window.stop();
        return entrar();
    }
    fetch('../__sessao').then(r => r.json()).then(j => {
        if (!j.nome) return entrar();
        // o nome do caderno e o do login (o banco grava esse de qualquer jeito)
        const por = () => { lsGravar(CADERNO.tecnico, j.nome); cadernoPintar(); };
        if (document.readyState === 'complete') por(); else window.addEventListener('load', por);
    }).catch(entrar);
    // link do CSV: /api/ fica fora da pasta do site, entao navegar ate la daria 404
    document.addEventListener('click', async e => {
        const a = e.target.closest && e.target.closest('a[href^="/api/"]');
        if (!a) return;
        e.preventDefault();
        const r = await fetch(a.getAttribute('href'));
        if (!r.ok) return alert('Não consegui baixar (' + r.status + ').');
        const b = document.createElement('a');
        b.href = URL.createObjectURL(await r.blob());
        b.download = 'caderno.csv';
        b.click();
        setTimeout(() => URL.revokeObjectURL(b.href), 10000);
    });
})();
