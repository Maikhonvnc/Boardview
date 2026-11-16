// Estado global do viewer (pecas, vista, selecao) e utilitarios de texto.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)

// rotular(): definido no skin.js (redesenho). Este guarda-costas mantem os
// modulos funcionando num HTML antigo, sem skin.js — la o botao volta a ser
// so texto, que era exatamente o comportamento anterior.
if (typeof window.rotular !== 'function') {
    window.rotular = function (el, txt) {
        if (!el) return;
        const s = el.querySelector('[data-rot]');
        if (s) s.textContent = txt; else el.textContent = txt;
    };
}

// escHTML(): texto -> HTML seguro. Nome de componente, apelido de malha, tensao e
// leitura de diodo sao DIGITADOS por gente — e na plataforma do time, por colegas.
// Se um deles entrar cru num innerHTML, um texto como <img src=x onerror=...> vira
// codigo rodando no navegador de todo mundo que abrir a placa. Tudo que vem de dado
// (arquivo .bvr ou digitacao) passa por aqui antes de ir para innerHTML; o resto
// usa textContent.
function escHTML(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Formato aceito para uma tensao medida: numero (ponto ou virgula), opcional "V".
// Devolve o texto normalizado ("3.3") ou null se nao for numero.
function tensaoValida(s) {
    const m = String(s).trim().match(/^(-?\d+(?:[.,]\d+)?)\s*[vV]?$/);
    if (!m) return null;
    const v = m[1].replace(',', '.');
    return Math.abs(parseFloat(v)) < 1000 ? v : null;   // 3300 e mV digitado como V: o caderno recusaria
}

// Variables globales
let fileContent;
let parts = [];
let outlinePoints = [];
let flipHorizontal = true; // Estado del reflejo
// Variables para transformación global
let scaleFactor = 1;
let rotationAngle = Math.PI; // Inicialmente 180° (en radianes)
let offsetX = 0;
let offsetY = 0;
let pinScaleFactor = 1; // Ajusta según lo necesites //1
let isDragging = false;

// Buffer para renderizar el contorno (elemento estático)
let buffer;

// Modo de visualización: "all", "top" o "bottom"
let displayMode = "top";

// Variables para interacción
let tooltip = null;       // Información detallada del pin (tooltip)
let selectedPin = null;   // Pin seleccionado

// Desplazamiento horizontal para separar componentes TOP y BOTTOM cuando se muestran juntos
let bottomOffset = 0;

//////////////////////////
// PRELOAD y SETUP
//////////////////////////
let bgImage; // Variável global para armazenar a imagem de fundo (borda tracada)
let photoImage; // foto real da placa (alinhada ao .bvr) — adaptacao local
let bgMode = 0; // 0=borda, 1=foto, 2=nenhum
let showBg = true; // compat
