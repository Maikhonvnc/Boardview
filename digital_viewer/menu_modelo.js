// Menu do MODELO no topo: as outras placas e os arquivos do MESMO drone.
//
// O seletor que ja existia lista as 22 placas do acervo em fila, sem dizer de que
// drone e cada uma. Este aqui parte da placa aberta, descobre a pasta do modelo
// (build/modelos.json, gerado pelo gen_modelos.py) e mostra so o que e daquele
// drone: as outras placas — que abrem no proprio viewer quando existem — e os PDFs
// e fotos da pasta, que abrem em aba nova pela rota /_drones/ do servidor.

let indiceModelos = null;

function montarMenuModelo() {
    const ctr = document.getElementById('controls');
    if (!ctr) return;

    const sel = document.createElement('select');
    sel.id = 'menuModelo';
    sel.title = 'Outras placas e arquivos deste mesmo drone';
    sel.style.cssText = 'background:#3b4a63;color:#9fe8ff;border:none;height:30px;' +
                        'max-width:230px;font-size:11px;margin-right:2px';
    sel.innerHTML = '<option>carregando…</option>';
    ctr.insertBefore(sel, ctr.firstChild);

    fetch('build/modelos.json').then(r => r.ok ? r.json() : null).then(ix => {
        if (!ix) { sel.innerHTML = '<option>sem indice do modelo</option>'; return; }
        indiceModelos = ix;
        const modelo = ix.de_placa[boardKey];
        if (!modelo || !ix.modelos[modelo]) {
            sel.innerHTML = '<option>modelo nao identificado</option>';
            return;
        }
        const m = ix.modelos[modelo];
        sel.innerHTML = '';
        const titulo = document.createElement('option');
        titulo.textContent = '📁 ' + modelo;
        titulo.value = '';
        sel.appendChild(titulo);

        if (m.placas.length) {
            const g = document.createElement('optgroup');
            g.label = 'placas deste drone';
            for (const p of m.placas) {
                const o = document.createElement('option');
                // sem id = existe na pasta mas nao foi montada no viewer
                o.value = p.id ? 'placa:' + p.id : '';
                o.disabled = !p.id;
                o.textContent = (p.id === boardKey ? '▶ ' : p.id ? '   ' : '   (sem viewer) ')
                              + p.nome + (p.foto ? '  📷' : '');
                g.appendChild(o);
            }
            sel.appendChild(g);
        }
        if (m.arquivos.length) {
            const g = document.createElement('optgroup');
            g.label = 'mapas e fotos';
            for (const a of m.arquivos) {
                const o = document.createElement('option');
                o.value = 'url:' + a.url;
                o.textContent = (a.tipo === 'pdf' ? '📄 ' : '🖼️ ') + a.nome;
                g.appendChild(o);
            }
            sel.appendChild(g);
        }
        sel.value = '';

        sel.onchange = () => {
            const v = sel.value;
            sel.value = '';                       // volta a mostrar o nome do modelo
            if (v.startsWith('placa:')) location.search = '?board=' + v.slice(6);
            else if (v.startsWith('url:')) window.open(v.slice(4), '_blank');
        };
    }).catch(() => { sel.innerHTML = '<option>sem indice do modelo</option>'; });
}

function botaoHub() {
    // no redesenho o HUB e o logo da Galvao na barra de cima (#btnHub, no HTML)
    let b = document.getElementById('btnHub');
    if (!b) {
        const ctr = document.getElementById('controls');
        if (!ctr) return;
        b = document.createElement('button');
        b.type = 'button';
        b.id = 'btnHub';
        b.innerHTML = 'HUB';
        b.title = 'Voltar para o hub';
        ctr.insertBefore(b, ctr.firstChild);
    }
    b.onclick = (e) => { e.preventDefault(); location.href = '../HUB.html'; };
}
