// Renomear componentes pelo painel DADOS DETALHADOS.
//
// O .bvr traz nomes crus do fabricante (N28734, N30796...). Aqui voce troca por um
// nome que diga alguma coisa ("PMIC 5V8", "USB VBUS") e ele passa a aparecer no
// painel, no rotulo sobre a placa, na busca do topo e na lista da malha.
//
// O nome original NAO se perde: fica guardado ao lado e volta a aparecer entre
// parenteses. Apagar o campo desfaz a troca.
//
// Onde fica salvo: localStorage, por placa. O botao 💾 baixa um nomes.json para
// guardar em digital_viewer/build/ — esse arquivo vale como padrao em qualquer
// navegador, e o que estiver no localStorage tem prioridade.

let nomesCustom = {};        // nome original -> nome escolhido

function nomesChave() {
    return 'nomes_' + (typeof boardKey !== 'undefined' ? boardKey : '?');
}

function nomesCarregar() {
    fetch('build/nomes.json').then(r => r.ok ? r.json() : {})
        .then(base => {
            const daPlaca = base[boardKey] || {};
            for (const k in daPlaca) if (!(k in nomesCustom)) nomesCustom[k] = daPlaca[k];
            aplicarNomes();
        }).catch(() => {});
    try {
        Object.assign(nomesCustom, JSON.parse(localStorage.getItem(nomesChave()) || '{}'));
    } catch (e) { /* storage indisponivel: vale so nesta sessao */ }
    aplicarNomes();
}

function nomesSalvar() {
    try { localStorage.setItem(nomesChave(), JSON.stringify(nomesCustom)); } catch (e) {}
}

// nome que aparece na tela (o escolhido, se houver)
function nomeExibido(part) {
    if (!part) return '';
    const orig = part.nomeOriginal || part.name;
    return nomesCustom[orig] || orig;
}

function aplicarNomes() {
    if (typeof parts === 'undefined') return;
    for (const p of parts) {
        if (p.nomeOriginal === undefined) p.nomeOriginal = p.name;
        p.name = nomesCustom[p.nomeOriginal] || p.nomeOriginal;
    }
    if (typeof fillComponentDatalist === 'function') fillComponentDatalist();
}

function renomearComponente(part) {
    if (!part) {
        alert('Clique num componente da placa primeiro.');
        return;
    }
    const orig = part.nomeOriginal || part.name;
    const atual = nomesCustom[orig] || '';
    const s = prompt(`Novo nome para ${orig}\n(vazio = voltar ao original):`, atual);
    if (s === null) return;
    // sem caracteres de controle e com tamanho de nome (a tela ja escapa o HTML)
    const novo = s.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 60);
    if (novo) nomesCustom[orig] = novo; else delete nomesCustom[orig];
    nomesSalvar();
    if (typeof anotEnviar === 'function') anotEnviar([['nomes', orig, novo || null]]);   // servidor
    aplicarNomes();
    if (typeof updateComponentInfo === 'function') {
        updateComponentInfo(part, (part.pins && part.pins[0]) || null);
    }
    if (typeof ajusteAviso === 'function') {
        ajusteAviso(novo ? `${orig} agora e "${novo}"` : `${orig} voltou ao nome original`);
    }
}

// --- renomear MALHA ------------------------------------------------------------
// Mesma ideia do componente, mas o nome vale para todos os pinos da malha. Fica em
// localStorage ('malhas_<placa>'), por cima do build/malhas.json; vazio = volta ao
// apelido do arquivo, ou ao nome cru. A chave e SEMPRE o nome cru (pin.netOriginal),
// entao renomear duas vezes nao perde a origem.
function malhasLocais() {
    try { return JSON.parse(localStorage.getItem('malhas_' + boardKey) || '{}'); }
    catch (e) { return {}; }
}

function renomearMalha(netAtual) {
    if (!netAtual) { alert('Clique num pino da malha primeiro.'); return; }
    let cru = netAtual;
    for (const p of parts) for (const q of (p.pins || []))
        if (q.net === netAtual && q.netOriginal) { cru = q.netOriginal; break; }
    if (cru === 'GND' || cru === 'NC') { alert(cru + ' nao se renomeia.'); return; }

    const locais = malhasLocais();
    const s = prompt(`Novo nome para a malha ${netAtual}` +
                     (cru !== netAtual ? ` (original: ${cru})` : '') +
                     `\n(vazio = voltar ao original):`, locais[cru] || '');
    if (s === null) return;
    const novo = s.replace(/[\u0000-\u001f\u007f]/g, '').trim().replace(/\s+/g, '_').slice(0, 60);

    const arq = window.__malhas && window.__malhas[boardKey] || {};
    const doArquivo = arq[cru] || (typeof malhaCanon === 'function' ? arq[malhaCanon(cru)] : undefined);
    const exibido = novo || doArquivo || cru;

    // Duas malhas com o mesmo nome acenderiam juntas na tela — parece uma ligacao
    // que nao existe. Isso engana o diagnostico, entao nao deixa.
    for (const p of parts) for (const q of (p.pins || []))
        if (q.net === exibido && (q.netOriginal || q.net) !== cru) {
            alert(`Ja existe outra malha chamada "${exibido}". Escolha outro nome.`);
            return;
        }
    // o viewer deduz tensao do nome (VBAT -> 4,2 V, 3P3 -> 3,3 V)
    if (novo && typeof netNameToVoltage === 'function' && netNameToVoltage(novo) &&
        !confirm(`O nome "${novo}" faz o viewer mostrar ${netNameToVoltage(novo)} ` +
                 `nessa malha sem ninguem ter medido. Usar mesmo assim?`)) return;

    // O apelido pode estar guardado pelo nome cru ("7P0_Net9") ou sem o prefixo ("Net9",
    // ver malhaCanon): apagar tem que tirar os dois, senao o outro reaparece.
    const can = typeof malhaCanon === 'function' ? malhaCanon(cru) : cru;
    if (novo) locais[cru] = novo; else { delete locais[cru]; delete locais[can]; }
    try { localStorage.setItem('malhas_' + boardKey, JSON.stringify(locais)); } catch (e) {}
    if (typeof anotEnviar === 'function')                                                 // servidor
        anotEnviar(novo || can === cru ? [['malhas', cru, novo || null]]
                                       : [['malhas', cru, null], ['malhas', can, null]]);
    if (apelidoMalha.locais) {
        if (novo) apelidoMalha.locais[cru] = novo;
        else { delete apelidoMalha.locais[cru]; delete apelidoMalha.locais[can]; }
    }

    for (const p of parts) for (const q of (p.pins || []))
        if ((q.netOriginal || q.net) === cru) q.net = exibido;
    // a tensao medida estava no nome antigo: vai junto
    if (userVolts[netAtual] != null && netAtual !== exibido) {
        userVolts[exibido] = userVolts[netAtual]; delete userVolts[netAtual];
        try { localStorage.setItem('uv_' + boardKey, JSON.stringify(userVolts)); } catch (e) {}
    }
    if (typeof currentNet !== 'undefined' && currentNet === netAtual) currentNet = exibido;
    if (typeof renderBuffer === 'function') renderBuffer();
    if (typeof updateComponentInfo === 'function' && parteNoPainel)
        updateComponentInfo(parteNoPainel, typeof selectedPin !== 'undefined' ? selectedPin : null);
    if (typeof ajusteAviso === 'function')
        ajusteAviso(novo ? `malha ${cru} agora e "${exibido}"` : `malha ${cru} voltou para "${exibido}"`);
}

function malhaSelecionada() {
    if (typeof selectedPin !== 'undefined' && selectedPin) return selectedPin.net;
    return typeof currentNet !== 'undefined' ? currentNet : null;
}

function nomesExportar() {
    const tudo = {};
    try { // junta o que ja houver no arquivo com o desta placa
        tudo[boardKey] = nomesCustom;
    } catch (e) {}
    const blob = new Blob([JSON.stringify(tudo, null, 1)], { type: 'application/json' });
    const l = document.createElement('a');
    l.href = URL.createObjectURL(blob);
    l.download = 'nomes.json';
    l.click();
    if (typeof ajusteAviso === 'function') {
        ajusteAviso('nomes.json baixado — guarde em digital_viewer/build/');
    }
}

// --- ligacao com o painel ----------------------------------------------------

// guarda qual componente esta no painel, p/ o botao saber quem renomear
let parteNoPainel = null;

function marcarParteNoPainel(part) { parteNoPainel = part; }

function botoesDeNome() {
    const alvo = document.getElementById('componentInfo');
    if (!alvo || document.getElementById('btnRenomear')) return;
    const linha = document.createElement('div');
    linha.style.cssText = 'display:flex; gap:4px; margin-top:6px';

    const b = document.createElement('button');
    b.id = 'btnRenomear';
    b.textContent = '✏️ RENOMEAR';
    b.title = 'Trocar o nome do componente selecionado (tecla N)';
    b.style.cssText = 'flex:1; background:#757575; color:#fff; border:none; padding:6px;' +
                      'border-radius:6px; cursor:pointer; font-size:12px';
    b.onclick = (e) => { e.preventDefault(); renomearComponente(parteNoPainel); };

    const g = document.createElement('button');
    g.textContent = '💾';
    g.title = 'Baixar nomes.json com os nomes desta placa';
    g.style.cssText = 'background:#757575; color:#fff; border:none; padding:6px 10px;' +
                      'border-radius:6px; cursor:pointer; font-size:12px';
    g.onclick = (e) => { e.preventDefault(); nomesExportar(); };

    const m = document.createElement('button');
    m.id = 'btnRenomearMalha';
    m.textContent = 'MALHA';
    m.title = 'Trocar o nome da malha do pino selecionado (tecla M)';
    m.onclick = (e) => { e.preventDefault(); renomearMalha(malhaSelecionada()); };

    linha.appendChild(b);
    linha.appendChild(m);
    linha.appendChild(g);
    alvo.appendChild(linha);
}

function renomearIniciar() {
    nomesCarregar();
    botoesDeNome();
    window.addEventListener('keydown', (e) => {
        if (/input|textarea/i.test((e.target.tagName || ''))) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (e.key === 'n' || e.key === 'N') {
            e.preventDefault();
            renomearComponente(parteNoPainel);
        }
        if (e.key === 'm' || e.key === 'M') {
            e.preventDefault();
            renomearMalha(malhaSelecionada());
        }
    });
}
