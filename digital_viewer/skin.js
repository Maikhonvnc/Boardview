// skin.js — camada de aparencia do redesenho (Viewer Galvao.dc.html).
//
// Objetivo: mudar SO o visual. O motor (SCRIPT3.js) e os modulos continuam
// mandando no estado; aqui a gente le esse estado e pinta a interface.
//
// Por que existe um "tick" de sincronia em vez de escutar cliques: metade das
// acoes vem do TECLADO (F, A, T, setas...), e nenhuma delas passa por um clique
// de botao. Escutar clique deixaria o destaque dos botoes mentindo toda vez que
// a pessoa usasse atalho — que e o jeito normal de usar isso na bancada.
// 250 ms de leitura de 4 variaveis custa nada e cobre todos os caminhos.

(function () {
  'use strict';

  // ---------------------------------------------------------------
  // rotular(): troca SO o texto do botao, preservando o icone SVG.
  // Os modulos antigos faziam btn.innerHTML = 'emoji<br>TEXTO', o que
  // apagaria o <svg>. Eles agora chamam isto; sem o <span data-rot>
  // (ou seja, num HTML antigo) o comportamento volta a ser o de antes.
  // ---------------------------------------------------------------
  window.rotular = function (el, txt) {
    if (!el) return;
    const s = el.querySelector('[data-rot]');
    if (s) s.textContent = txt;
    else el.textContent = txt;     // nunca innerHTML: o texto pode vir de dado
  };

  const $ = (id) => document.getElementById(id);
  const val = (nome) => {            // le um global sem explodir se nao existir
    try { return eval(nome); } catch (e) { return undefined; }
  };

  // ---------------------------------------------------------------
  // O p5 escuta o mouse na JANELA e da preventDefault, o que impede um
  // <select> nativo de abrir. #controls / #componentInfo / #componentModal
  // ja sao protegidos pelo protegerControles() do SCRIPT3; a barra de cima
  // e o puxador do painel sao novos, entao precisam da mesma protecao.
  // Sem isto os dropdowns da barra superior nascem mortos e SEM erro nenhum.
  // ---------------------------------------------------------------
  // (o 'mouseup' fica de fora de proposito — ver a nota no protegerControles()
  //  do SCRIPT3.js: engolir o mouseup deixa o p5 achando que o botao continua
  //  pressionado e a vista arrasta sozinha)
  function proteger(el) {
    if (!el) return;
    for (const ev of ['pointerdown', 'mousedown', 'click', 'dblclick', 'wheel']) {
      el.addEventListener(ev, (e) => e.stopPropagation());
    }
  }

  // ---------------------------------------------------------------
  // painel recolhivel
  // ---------------------------------------------------------------
  let painelAberto = true;
  function pintarPainel() {
    const p = $('componentInfo'), b = $('btnPainel'), d = $('dock'), v = $('voltCard');
    if (p) p.classList.toggle('fechado', !painelAberto);
    if (b) b.classList.toggle('encolhido', !painelAberto);
    if (d) d.classList.toggle('encolhido', !painelAberto);
    if (v) v.classList.toggle('encolhido', !painelAberto);
  }
  function alternarPainel() { painelAberto = !painelAberto; pintarPainel(); }

  // ---------------------------------------------------------------
  // sincronia estado -> aparencia
  // ---------------------------------------------------------------
  const ROT_FUNDO = ['BORDAS', 'FOTO', 'SEM FUNDO'];

  function sincronizar() {
    const modo  = val('displayMode');
    const unica = val('faceUnica');
    const aj    = val('modoAjuste');
    const bg    = val('bgMode');

    const liga = (id, on) => { const e = $(id); if (e) e.classList.toggle('on', !!on); };

    liga('btnTop',    modo === 'top');
    liga('btnBottom', modo === 'bottom');
    liga('btnAll',    modo === 'all');
    liga('btnFaceUnica', unica);
    liga('btnAjuste', aj);

    const m = $('ajusteMoldura');
    if (m) m.classList.toggle('on', !!aj);

    // o rotulo do fundo tambem e escrito pelo SCRIPT3/ajuste_fundo; aqui so
    // cobrimos o estado inicial e qualquer caminho que nao passe por la.
    const tb = $('toggleBgBtn');
    if (tb && typeof bg === 'number') {
      const s = tb.querySelector('[data-rot]');
      if (s && s.textContent !== ROT_FUNDO[bg]) s.textContent = ROT_FUNDO[bg];
    }

    const ft = $('faceTag');
    if (ft) {
      const nome = modo === 'bottom' ? 'FACE BOTTOM' : (modo === 'all' ? 'AMBAS AS FACES' : 'FACE TOP');
      if (ft.textContent !== nome) ft.textContent = nome;
    }

    // malha selecionada, no cartao de tensao
    const vn = $('voltNet');
    if (vn) {
      const net = val('currentNet');
      const txt = 'MALHA ' + (net ? net : '—');
      if (vn.textContent !== txt) vn.textContent = txt;
    }

    // leitura de diodo da malha selecionada (diodo.js); vermelha se diverge da ref
    const vd = $('voltDiodo');
    if (vd) {
      const net = val('currentNet');
      const t = (net && typeof textoDiodo === 'function') ? textoDiodo(net) : '';
      vd.hidden = !t;
      const txt = t ? 'DIODO ' + t : '';
      if (vd.textContent !== txt) vd.textContent = txt;
      vd.classList.toggle('diverge', !!t && diodoDiverge(diodoDe(net)));
    }

    // os <select> de placa e de modelo sao criados por JS dentro de #controls;
    // o lugar deles no redesenho e a barra de cima.
    // o aviso do ajuste fica ACIMA do dock. Como o dock quebra em varias linhas
    // em tela estreita, a altura dele varia — medir e a unica forma de o aviso
    // nao acabar por cima dos botoes.
    const dk = $('dock');
    if (dk) {
      const alt = Math.round(dk.getBoundingClientRect().height) + 26;
      document.documentElement.style.setProperty('--aviso-bottom', alt + 'px');
    }

    const nav = $('navControls'), ctr = $('controls');
    if (nav && ctr) {
      for (const sel of Array.from(ctr.querySelectorAll('select'))) {
        sel.removeAttribute('style');   // o style inline antigo era cinza/amarelo
        nav.appendChild(sel);
      }
    }
  }

  // ---------------------------------------------------------------
  // nome da placa na barra de cima
  // ---------------------------------------------------------------
  function nomearPlaca() {
    const alvo = $('nomePlaca');
    if (!alvo) return;
    const id = window.__board ||
               new URLSearchParams(location.search).get('board') || 'mine2';
    alvo.textContent = id.toUpperCase();
    fetch('build/boards.json')
      .then((r) => r.json())
      .then((l) => {
        const b = l.find((x) => x.id === id);
        if (b && b.name) alvo.textContent = b.name.toUpperCase();
      })
      .catch(() => {});
  }

  // ---------------------------------------------------------------
  function iniciar() {
    proteger($('topbar'));
    proteger($('btnPainel'));

    const bp = $('btnPainel');
    if (bp) bp.onclick = (e) => { e.preventDefault(); alternarPainel(); };

    // DESFAZER: agora e botao fixo do HTML (antes o ajuste_fundo.js criava um).
    const bd = $('btnDesfazer');
    if (bd) bd.onclick = (e) => {
      e.preventDefault();
      if (e.shiftKey) { if (typeof ajusteZerarPlaca === 'function') ajusteZerarPlaca(); }
      else { if (typeof ajusteDesfazer === 'function') ajusteDesfazer(); }
    };

    window.addEventListener('keydown', (e) => {
      if (/input|textarea/i.test(e.target && e.target.tagName || '')) return;
      if (e.key === 'Tab') { e.preventDefault(); alternarPainel(); }
      // "/" foca a busca — e o que a tecla desenhada no campo promete
      if (e.key === '/') { e.preventDefault(); const s = $('searchComponent'); if (s) s.focus(); }
    });

    nomearPlaca();
    pintarPainel();
    sincronizar();
    setInterval(sincronizar, 250);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
