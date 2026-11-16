// setup() do p5: liga os modulos, carrega a placa e os controles do topo.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)


 function setup() {
         // Define o tamanho do canvas para ocupar toda a tela
         let canvasWidth = windowWidth; // Largura do canvas igual à largura da janela
         let canvasHeight = windowHeight; // Altura do canvas igual à altura da janela
         createCanvas(canvasWidth, canvasHeight);
         
         protegerControles();  // sem isto os <select> da barra nao abrem (ver abaixo)
         ajusteIniciar();   // antes do parse: as teclas tem que valer mesmo se a placa falhar
         // Chamadas das funções após a criação do canvas
         try {
             parseFile();
         } catch (e) {
             console.error('nao consegui ler o .bvr desta placa:', e);
         }
         // apelidos de malha chegam por fetch (index.html), nao pelo preload: reaplica
         // quando vierem. Se ja tiverem chegado, o then roda logo em seguida.
         if (window.__malhasP) window.__malhasP.then(m => {
             window.__malhas = m || {};
             reaplicarApelidos();
         });
         frameRate(20); // Limita la velocidad de fotogramas a 20 FPS mientras mas usa mas recurso util para pc de bajo recursos
    
         buffer = createGraphics(width, height); // Usando o tamanho do canvas
         renderBuffer();
     
         calcularTransformacion();
        
         renderBuffer();
         
     
 
     
    // Configurar botones
    select('#btnAll').mousePressed(() => {
        displayMode = "all";
    });
    select('#btnTop').mousePressed(() => {
        displayMode = "top";
    });
    select('#btnBottom').mousePressed(() => {
        displayMode = "bottom";
    });
    select('#btnNextNet').mousePressed(() => {
        moveToNextPinInNet();
    });
    // Botón para rotar 90° cada click
    select('#btnRotate').mousePressed(() => {
        rotationAngle += Math.PI / 2;
    });
    document.getElementById("flipButton").addEventListener("click", () => {
        flipHorizontal = !flipHorizontal;
    });
    // Botão para mostrar/ocultar imagem de fundo
   
    let searchInput = document.getElementById("searchComponent");

    searchInput.addEventListener("mousedown", (event) => {
        event.stopPropagation(); // Evita que p5.js intercepte el evento
    });
     // Conecta o botão ao evento
     const toggleBtn = document.getElementById('toggleBgBtn');
      toggleBtn.addEventListener('click', (event) => {
      event.preventDefault(); // impede recarregamento ou comportamento padrão
     bgMode = (bgMode + 1) % 3;               // borda -> foto -> nenhum
     showBg = bgMode !== 2;
     rotular(toggleBtn, bgMode === 0 ? 'BORDAS' : (bgMode === 1 ? 'FOTO' : 'SEM FUNDO'));
    });

     // botao + tecla V: define a tensao MEDIDA da malha selecionada
     const voltBtn = document.getElementById('btnVolt');
     if (voltBtn) voltBtn.addEventListener('click', (e) => { e.preventDefault();
       setNetVoltage(selectedPin ? selectedPin.net : null, e.shiftKey ? 'ref' : 'reparo'); });
     window.addEventListener('keydown', (e) => {
       if (/input|textarea|select/i.test((e.target.tagName || ''))) return;   // digitando na busca/OS
       // V = placa da bancada; Shift+V = placa boa. Ctrl+V (colar) nao abre o pedido.
       if ((e.key === 'v' || e.key === 'V') && !e.ctrlKey && !e.metaKey && !e.altKey)
         setNetVoltage(selectedPin ? selectedPin.net : null, e.shiftKey ? 'ref' : 'reparo');
       // Enter = PROXIMO: anda pelos pinos da malha marcada sem tirar a mao do teclado
       if (e.key === 'Enter') { e.preventDefault(); moveToNextPinInNet(); }
     });
 


    fillComponentDatalist();
    setupSearchListener();
    setupBoardPicker();
    botaoFaceUnica();         // dobra as duas metades numa so (tecla F)
    montarMenuModelo();       // outras placas e arquivos do mesmo drone
    botaoHub();               // volta pro hub
    renomearIniciar();        // renomear componente pelo painel (botao ou tecla N)
    if (typeof diodoIniciar === 'function') diodoIniciar();   // modo diodo: D / Shift+D
    if (typeof cadernoIniciar === 'function') cadernoIniciar(); // caderno de bancada (medicoes.js)
    if (typeof cobreIniciar === 'function') cobreIniciar();     // trilhas reais, se a placa tiver (cobre.js)
    if (typeof classIniciar === 'function') classIniciar();     // modo Classificar, tecla Q (classificar.js)

    // o modo Foto e ligado por carregarSecoes() quando a placa tem metades
}

// O p5 escuta o mouse na JANELA e o mousePressed() daqui retorna false, o que vira
// preventDefault() no evento. E preventDefault no mousedown IMPEDE um <select>
// nativo de abrir a lista — era por isso que os dropdowns da barra nao funcionavam
// (o campo de busca ja tinha uma gambiarra individual pelo mesmo motivo).
// Solucao: o que acontece dentro da barra de controles nao sobe ate o p5.
// ATENCAO ao 'mouseup': ele NAO pode ser bloqueado. O que quebra o <select> e o
// preventDefault no MOUSEDOWN; o mouseup nao tem nada a ver com isso. Mas o p5
// marca mouseIsPressed=true quando o mousedown chega a um botao registrado com
// select('#id').mousePressed(...) — e se o mouseup for engolido aqui, ele nunca
// volta pra false. Resultado: depois de clicar TOP/BOTTOM a vista passava a
// arrastar sozinha com o mouse solto, como se o botao estivesse preso.
function protegerControles() {
    for (const id of ['controls', 'componentInfo', 'componentModal']) {
        const el = document.getElementById(id);
        if (!el) continue;
        for (const ev of ['pointerdown', 'mousedown', 'click', 'dblclick', 'wheel']) {
            el.addEventListener(ev, (e) => e.stopPropagation());
        }
    }
}

// dropdown de placas (adaptacao local): le build/boards.json e troca via ?board=
function setupBoardPicker() {
  fetch('build/boards.json').then(r => r.json()).then(list => {
    const sel = document.createElement('select');
    sel.style.cssText = 'background:#5f5e5e;color:#fbff00;border:none;height:30px;max-width:200px;font-size:11px';
    for (const b of list) {
      const o = document.createElement('option'); o.value = b.id; o.textContent = b.name;
      if (b.id === boardKey) o.selected = true; sel.appendChild(o);
    }
    sel.onchange = () => { location.search = '?board=' + sel.value; };
    const ctr = document.getElementById('controls');
    if (ctr) ctr.insertBefore(sel, ctr.firstChild);
  }).catch(() => {});
}
