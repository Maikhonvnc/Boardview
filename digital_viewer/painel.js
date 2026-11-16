// Painel DADOS DETALHADOS: tensao do pino, dados do componente e lista da malha.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)

// Função que converte nome da malha (net.name) em voltagem exibível
// Tensao deduzida para um pino: pelo nome exibido e, se ele nao disser nada (apelido como
// "PMIC_VIN"), pelo nome cru do arquivo ("7P0_Net9" -> 7.0V). Sem o segundo passo, dar
// apelido a uma malha com prefixo de tensao fazia a tensao sumir do painel.
function tensaoDoPino(pin) {
    if (!pin) return '';
    return netNameToVoltage(pin.net) ||
        (pin.netOriginal && pin.netOriginal !== pin.net ? netNameToVoltage(pin.netOriginal) : '');
}

function netNameToVoltage(netName) {
    if (!netName) return '';

    // tensao MEDIDA pelo usuario tem prioridade
    if (userVolts[netName] != null) {
        let s = ('' + userVolts[netName]).trim();
        return /[vV]/.test(s) ? s : s + 'V';
    }

    const name = netName.toUpperCase();

    const voltageMap = {
        'VBAT': '4.2V',
        'VBUS': '5.0V',
        'VPH_PWR': '4,2V',
        'VSYS': '4.2V',
        'VIO18': '1.8V',
        'VCN18': '1.8V',
        'VIO28': '2.8V',
        'VCN28': '2.8V',
        'PP_VDD_M': '4.2V',
        'PP_VDDM': '4.2V',
        'GND': 'GND',
        
    };

    // Verifica os nomes pré-mapeados
    for (const key in voltageMap) {
        if (name.includes(key)) {
            return voltageMap[key];
        }
    }

    // Detecta padrão com 2 dígitos, tipo "10V53" ou "10P53"
    const match2 = name.match(/(\d{2})(V|P)(\d{2})/);
    if (match2) {
        return `${match2[1]}.${match2[3]}V`;
    }

    // Padrão com 1 inteiro e 2 decimais, ex: 1P85 → 1,85V
    const match1p2 = name.match(/(\d)(V|P)(\d{2})/);
    if (match1p2) {
        return `${match1p2[1]}.${match1p2[3]}V`;
    }

    // Detecta padrão com 1 dígito, tipo "1V8" ou "3P3"
    const match1 = name.match(/(\d)(V|P)(\d)/);
    if (match1) {
        return `${match1[1]}.${match1[3]}V`;
    }

    return ''; // Se não reconhece, retorna vazio
}
let currentNet = null; // 🔥 Salvar a net atual
function updateComponentInfo(part = null, pin = null) {
    const container = document.getElementById('componentInfo');
    const details = document.getElementById('componentDetails');

    if (!details) return;

    if (typeof parts === 'undefined' || !Array.isArray(parts)) {
        details.innerHTML = `<div class="summary"><b>Dados não carregados</b></div>`;
        return;
    }

    const totalComponents = parts.length;
    const totalNets = new Set(parts.flatMap(p => (p.pins || []).map(pin => pin.net))).size;
    const totalPins = parts.reduce((acc, p) => acc + (p.pins ? p.pins.length : 0), 0);

    const isEmpty = !part || !pin;

    const orig = isEmpty ? '' : (part.nomeOriginal || part.name);
    // tudo que vai para o innerHTML abaixo ja sai escapado daqui (escHTML)
    const componente = isEmpty ? '---'
        : (part.name !== orig ? `${escHTML(part.name)} <small>(${escHTML(orig)})</small>` : escHTML(part.name));
    const tipo = isEmpty ? '---' : escHTML(getComponentType(part.name));
    const pads = isEmpty ? '---' : (part.pins ? part.pins.length : '---');
    const net = isEmpty ? '---' : escHTML(pin.net);
    const vRef = isEmpty ? null : uvRef[pin.netOriginal || pin.net];
    const voltage = isEmpty ? '---' : escHTML((typeof tensaoDoPino === 'function' ? (tensaoDoPino(pin) || '---') : '---')
                                              + (vRef != null ? ` · ref ${vRef}V` : ''));
    const netCount = isEmpty ? '---' : parts.filter(p => (p.pins || []).some(pn => pn.net === pin.net)).length;

    // 🔥 Salvar a net atual
    currentNet = isEmpty ? null : pin.net;
    if (typeof marcarParteNoPainel === 'function') marcarParteNoPainel(isEmpty ? null : part);

    // 🔥 Gerar lista agrupada por tipo
    let componentsOnNet = isEmpty 
        ? []
        : parts.filter(p => (p.pins || []).some(pn => pn.net === pin.net));

    const grouped = {};
    componentsOnNet.forEach(comp => {
        const type = getComponentType(comp.name);
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(comp.name);
    });

    const componentsListHTML = componentsOnNet.length > 0 
        ? `
        <div class="scrollable">
            ${Object.entries(grouped).map(([type, names]) => `
                <div class="group">
                    <div class="group-title">${escHTML(type)}</div>
                    <div class="group-items">
                    ${net}
                        ${names.map(n => `<span class="item">${escHTML(n)}</span>`).join(' ')}
                    </div>
                </div>
            `).join('')}
        </div>
        `
        : '---';

    details.innerHTML = `
        <div class="summary">
        DADOS DO COMPONENTE
            <div class="info-box"><span class="info-label">COMPONENTE:</span> <span class="info-value">${componente}</span></div><hr>
            <div class="info-box"><span class="info-label">TIPO:</span> <span class="info-value">${tipo}</span></div><hr>
            <div class="info-box"><span class="info-label">PADS:</span> <span class="info-value">${pads}</span></div><hr>
            <div class="info-box"><span class="info-label">MALHA:</span> <span class="info-value">${net}</span></div><hr>
            <div class="info-box"><span class="info-label">VOLTAGEM:</span> <span class="info-value">${voltage}</span></div><hr>
            ${(() => {   // leitura de diodo (diodo.js, tecla D / Shift+D)
                const n = pin && pin.net;
                const t = (typeof textoDiodo === 'function' && n) ? textoDiodo(n) : '';
                if (!t) return '';
                const ruim = typeof diodoDiverge === 'function' && diodoDiverge(diodoDe(n));
                return `<div class="info-box"><span class="info-label">DIODO:</span> <span class="info-value${ruim ? ' diverge' : ''}">${escHTML(t)}${ruim ? ' ⚠' : ''}</span></div><hr>`;
            })()}
            ${(typeof consensoLinhas === 'function' && !isEmpty) ? consensoLinhas(pin).map(l =>   // consenso do time (medicoes.js)
                `<div class="info-box"><span class="info-label">${escHTML(l.rotulo)}</span> <span class="info-value cons-${escHTML(l.classe)}">${escHTML(l.texto)}</span></div><hr>`).join('') : ''}
            <div class="info-box"><span class="info-label">COMP/ NA MALHA:</span> <span class="info-value">${netCount}</span></div>
        </div>
        <hr>
        <div class="summary">
        TOTAL NA PLACA
            <div class="info-box"><span class="info-label">COMPONENTES:</span> <span class="info-value">${totalComponents}</span></div>
            <div class="info-box"><span class="info-label">MALHAS:</span> <span class="info-value">${totalNets}</span></div>
            <div class="info-box"><span class="info-label">PADS:</span> <span class="info-value">${totalPins}</span></div>
        </div><hr>
        COMPONENTES NA MALHA
     <div class="summary">
        <div class="info-box">
            
        </div>
    `;
}

updateComponentInfo();
// Função para detectar o tipo de componente
function getComponentType(name) {
    const prefix = name.toUpperCase();
    if (prefix.startsWith('CON') || prefix.startsWith('J')) return 'CONECTOR';
    if (prefix.startsWith('ZD') || prefix.startsWith('DZ')) return 'DIODO ZENER';
    if (prefix.startsWith('R')) return 'RESISTOR';
    if (prefix.startsWith('C')) return 'CAPACITOR';
    if (prefix.startsWith('U')) return 'CIRCUITO INTEGRADO';
    if (prefix.startsWith('L')) return 'BOBINA / INDUTOR';
    if (prefix.startsWith('D')) return 'DIODO';
    if (prefix.startsWith('Q')) return 'TRANSISTOR';
    return 'NÃO DEFINIDO';
}
updateComponentInfo();

  
// 🔥 Função para gerar lista no modal baseada na currentNet
function generateComponentListForNet() {
    const container = document.getElementById('listaDaMalha');
    container.innerHTML = '';

    if (!currentNet) {
        container.innerHTML = '<div>Nenhuma malha selecionada</div>';
        return;
    }

    const componentsOnNet = parts.filter(p => 
        (p.pins || []).some(pn => pn.net === currentNet)
    );

    if (componentsOnNet.length === 0) {
        container.innerHTML = '<div>Nenhum componente nesta malha</div>';
        return;
    }

    const grouped = {};
    componentsOnNet.forEach(comp => {
        const type = getComponentType(comp.name);
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(comp.name);
    });

    for (const [type, items] of Object.entries(grouped)) {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'group';

        const title = document.createElement('div');
        title.className = 'group-title';
        title.textContent = type;
        groupDiv.appendChild(title);

        const itemsDiv = document.createElement('div');
        itemsDiv.className = 'group-items';

        items.forEach(name => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'item';
            itemDiv.textContent = name;
            itemsDiv.appendChild(itemDiv);
        });

        groupDiv.appendChild(itemsDiv);
        container.appendChild(groupDiv);
    }
}

// 🔥 Controle do Modal
const modal = document.getElementById("componentModal");
const btn = document.getElementById("openModalBtn");
const span = document.getElementsByClassName("close")[0];

// o botao abre E fecha (a lista agora e gaveta: o resto da tela segue clicavel)
btn.onclick = function() {
    if (modal.style.display === "block") { modal.style.display = "none"; return; }
    generateComponentListForNet();
    modal.style.display = "block";
}
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === "block") modal.style.display = "none";
});

span.onclick = function() {
    modal.style.display = "none";
}

window.onclick = function(event) {
    if (event.target == modal) {
        modal.style.display = "none";
    }
}
