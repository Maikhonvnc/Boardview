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

// ===== Tensao MEDIDA pelo usuario (adaptacao local): salva por placa+malha e colore a malha =====
let boardKey = (function(){ if (window.__board) return window.__board;   // vem do preload
  let m = location.search.match(/board=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : 'mine2'; })();
let userVolts = {};
try { userVolts = JSON.parse(localStorage.getItem('uv_' + boardKey) || '{}'); } catch(e) {}

// Apelido de malha: build/malhas.json = {"<placa>": {"Net161": "BATERIA_ENTRADA"}},
// carregado no preload() do index.html. Sem o arquivo (ou noutra pagina, como o
// mine2_db.html) devolve o nome cru. CUIDADO ao escolher apelidos: o viewer deduz
// tensao do nome — "VBAT"/"VSYS" viram 4,2 V e "3P3"/"1V8" viram tensao.
// A tensao MEDIDA estava guardada pelo nome cru; ela migra para o apelido aqui,
// senao renomear a malha apagaria a medicao da tela.
// troca o nome exibido de todos os pinos de acordo com os apelidos atuais
function reaplicarApelidos() {
    if (typeof parts === 'undefined') return;
    for (const p of parts) for (const q of (p.pins || []))
        if (q.netOriginal) q.net = apelidoMalha(q.netOriginal);
    if (typeof renderBuffer === 'function') renderBuffer();
}

// Identidade da malha sem o prefixo de tensao. Alguns .bvr trazem a malha como
// "7P0_Net9" / "3P0Net18" / "VCC_3P2V_Net65"; os apelidos (malhas.json, anotacoes) e o
// cobre (.cobre.json) usam "Net9". Sem isto o apelido e o cobre dessas malhas nunca
// apareciam. O nome sem prefixo e unico em todas as placas (conferido em 11/2026).
function malhaCanon(n) {
    const m = /(Net\d+)$/.exec(n || '');
    return m ? m[1] : n;
}

function apelidoMalha(cru) {
    // o que foi renomeado na tela (tecla M, localStorage) vence o build/malhas.json
    if (apelidoMalha.locais === undefined) {
        try { apelidoMalha.locais = JSON.parse(localStorage.getItem('malhas_' + boardKey) || '{}'); }
        catch (e) { apelidoMalha.locais = {}; }
    }
    const m = window.__malhas && window.__malhas[boardKey];
    const can = malhaCanon(cru);
    const novo = apelidoMalha.locais[cru] || apelidoMalha.locais[can] || (m && (m[cru] || m[can])) || cru;
    if (novo !== cru && userVolts[cru] != null && userVolts[novo] == null) {
        userVolts[novo] = userVolts[cru];
        delete userVolts[cru];
        try { localStorage.setItem('uv_' + boardKey, JSON.stringify(userVolts)); } catch (e) {}
    }
    return novo;
}
function saveUserVolts(){ try { localStorage.setItem('uv_' + boardKey, JSON.stringify(userVolts)); } catch(e){} }
function parseVoltNum(s){ if (s == null) return null; let m = (''+s).replace(',','.').match(/(\d+(?:\.\d+)?)/);
  if (!m) return null; let v = parseFloat(m[1]); return (v >= 0 && v <= 60) ? v : null; }
function voltBandColor(v){
  const B = [[12,[220,38,38]],[8,[249,115,22]],[5,[34,197,94]],[3.3,[14,165,233]],[3.0,[20,184,166]],
             [2.8,[132,204,22]],[1.8,[168,85,247]],[1.2,[234,179,8]],[1.0,[236,72,153]],[0.8,[100,116,139]]];
  for (const [bv,c] of B) if (Math.abs(bv - v) <= 0.2) return c;
  let h = (((v*57+15)%360)+360)%360, s = 0.85, val = 0.95, c = val*s, x = c*(1-Math.abs((h/60)%2-1)), m = val-c;
  let seg = [[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][Math.floor(h/60)%6];
  return [Math.round((seg[0]+m)*255), Math.round((seg[1]+m)*255), Math.round((seg[2]+m)*255)];
}
// papel: 'reparo' (V, a placa da bancada) ou 'ref' (Shift+V, placa BOA). A copia local
// (userVolts) continua sendo o que a tela mostra; a leitura vai tambem para o caderno
// (medicoes.js), com o papel, o tecnico, a OS e a condicao.
// Tensao da placa BOA (Shift+V): copia separada, chaveada pela malha CRUA. Antes as duas
// dividiam o userVolts: o Shift+V vinha preenchido com o valor da placa com defeito, e
// apagar com V apagava a referencia so na tela.
let uvRef = {};
try { uvRef = JSON.parse(localStorage.getItem('uvref_' + boardKey) || '{}'); } catch (e) {}

function setNetVoltage(net, papel = 'reparo'){
  if (!net) { alert('Selecione um pad/malha primeiro (clique num pino).'); return; }
  if (net === 'GND') { alert('No GND não tem tensão para anotar.'); return; }
  // o nome do tecnico vem ANTES do valor: cancelar o nome cancela a leitura inteira
  if (typeof cadernoGarantirTecnico === 'function' && !cadernoGarantirTecnico()) return;
  const ref = papel === 'ref';
  const cru = typeof malhaCrua === 'function' ? malhaCrua(net) : net;
  let cur = ref ? (uvRef[cru] ?? '') : (userVolts[net] ?? '');
  const quem = ref ? 'REFERÊNCIA (placa boa)' : 'ESTA placa';
  let s = prompt('Tensão MEDIDA — ' + quem + '\nmalha ' + net +
                 '  (ex: 5, 3.3, 8, 1.8).  Vazio = apagar:', cur);
  if (s === null) return;
  let v = null;
  if (s.trim() !== '') {
    v = tensaoValida(s);
    if (v === null) { alert('Tensão precisa ser um número abaixo de 1000 (ex.: 3.3, 8 ou 1,8).'); return; }
  }
  if (ref) {
    if (v === null) delete uvRef[cru]; else uvRef[cru] = v;
    try { localStorage.setItem('uvref_' + boardKey, JSON.stringify(uvRef)); } catch (e) {}
  } else {
    if (v === null) delete userVolts[net]; else userVolts[net] = v;
    saveUserVolts();
  }
  if (typeof cadernoRegistrar === 'function') cadernoRegistrar({ tipo: 'tensao', papel, net, valor: v });
  if (typeof redraw === 'function') redraw();
}

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
 
 //////////////////////////
 // DIBUJO
 //////////////////////////
 
 let blinkState = 0;  // Controla o estado de piscamento
 let blinkInterval = 15;  // Intervalo em frames para alternar as cores (ajuste conforme necessário)
 
 function draw() {
    background(0);
   
    // T1: Rotação global centrada no canvas
    push();
    translate(width / 2, height / 2);
    rotate(rotationAngle);
    translate(-width / 2, -height / 2);
  
    if (displayMode === "all") {
      bottomOffset = computeBottomOffset();
    }
  
    // T2: Reflejo horizontal (flip horizontal) se ativado
    push();
    if (flipHorizontal) {
      translate(width, 0);
      scale(-1, 1);
    }
  
    // T3: Translação e escala (zoom/pan)
    push();
    translate(offsetX, offsetY);
    scale(scaleFactor);
  
      
  
    // 🔽 Desenha a imagem de fundo com zoom e pan aplicados
    drawBackgroundImage();
    
    function getBvrBoundingBox() {
        let xs = outlinePoints.map(p => p.x);
        let ys = outlinePoints.map(p => p.y);
        let minX = Math.min(...xs);
        let maxX = Math.max(...xs);
        let minY = Math.min(...ys);
        let maxY = Math.max(...ys);
        console.log("BBox:", { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY });
        return {
          minX,
          maxX,
          minY,
          maxY,
          width: maxX - minX,
          height: maxY - minY
        };
      }
      
      function drawBackgroundImage() {
        if (bgMode === 2) return;                 // fundo desligado
        let bbox = getBvrBoundingBox();
        // FOTO: uma imagem por metade da placa, cada uma na sua caixa e com o seu
        // ajuste (ver ajuste_fundo.js). BORDAS: a imagem unica do DigitalBoard.
        if (bgMode === 1 && desenharSecoesFoto(bbox)) return;
        let img = bgMode === 0 ? bgImage : photoImage;
        if (img && img.width) {          // imagem que falhou ao carregar fica 0x0 e quebra o draw
          push();
          scale(1, -1); // Inverte Y
          translate(0, -bbox.maxY - bbox.minY); // Ajusta o Y para origem
          image(img, bbox.minX, bbox.minY, bbox.width, bbox.height);
          pop();
        }
      }
      
      
      push();

pop();

      
      
drawComponentBoundingBoxes();
      
   ///////////////////////////////////////////
   //////////___OUTLINE_BORDA___//////////////////
   ///////////////////////////////////////
   let threshold = 1.1; // Distância mínima entre pontos para considerar duplicados
   let minSegmentLength = 2; // Tamanho mínimo de segmento de linha para ser considerado válido (ajustável)
   
   function arePointsClose(p1, p2, threshold) {
       return dist(p1.x, p1.y, p2.x, p2.y) < threshold;
   }
   
   function filterOutlinePoints(outlinePoints, threshold) {
       let filteredPoints = [outlinePoints[0]];
       for (let i = 1; i < outlinePoints.length; i++) {
           let currentPoint = outlinePoints[i];
           let lastAddedPoint = filteredPoints[filteredPoints.length - 1];
           if (!arePointsClose(lastAddedPoint, currentPoint, threshold)) {
               filteredPoints.push(currentPoint);
           }
       }
       return filteredPoints;
   }
   
   function segmentLength(p1, p2) {
       return dist(p1.x, p1.y, p2.x, p2.y);
   }
   
   function removeSmallSegments(points, minLength) {
       let cleanedPoints = [points[0]];
       for (let i = 1; i < points.length; i++) {
           let currentPoint = points[i];
           let lastAddedPoint = cleanedPoints[cleanedPoints.length - 1];
           if (segmentLength(lastAddedPoint, currentPoint) > minLength) {
               cleanedPoints.push(currentPoint);
           }
       }
       return cleanedPoints;
   }
   
   function simplifyContour(points, epsilon) {
       if (points.length < 3) return points;
       let dmax = 0;
       let index = 0;
       for (let i = 1; i < points.length - 1; i++) {
           let d = perpendicularDistance(points[i], points[0], points[points.length - 1]);
           if (d > dmax) {
               index = i;
               dmax = d;
           }
       }
       if (dmax > epsilon) {
           let left = simplifyContour(points.slice(0, index + 1), epsilon);
           let right = simplifyContour(points.slice(index), epsilon);
           return left.slice(0, left.length - 1).concat(right);
       } else {
           return [points[0], points[points.length - 1]];
       }
   }
   
   function perpendicularDistance(pt, lineStart, lineEnd) {
       let normalLength = dist(lineStart.x, lineStart.y, lineEnd.x, lineEnd.y);
       return Math.abs((pt.x - lineStart.x) * (lineEnd.y - lineStart.y) - (pt.y - lineStart.y) * (lineEnd.x - lineStart.x)) / normalLength;
   }
   
   let filteredOutlinePoints = filterOutlinePoints(outlinePoints, threshold);
   let cleanedOutlinePoints = removeSmallSegments(filteredOutlinePoints, minSegmentLength);
   let simplifiedOutlinePoints = simplifyContour(cleanedOutlinePoints, 0.5);
   
   // Preenche a área dentro do contorno com verde
   fill(255, 255, 255, 0,); // Verde para representar a placa
   stroke(255, 255, 255, 0,); // Borda branca
   strokeWeight(1 / scaleFactor);
   beginShape();
   for (let p of simplifiedOutlinePoints) {
       vertex(p.x, p.y);
   }
   endShape(CLOSE);
   

    // -----------------------------------------

    

    // Dibujar el buffer (0x0 quando o canvas nasceu sem tamanho: pular)
    if (buffer && buffer.width && buffer.height) image(buffer, 0, 0);
    if (typeof desenharCobre === 'function') desenharCobre();   // trilhas reais da malha (cobre.js)
    

    // Atualiza o estado de piscamento
blinkState = (frameCount % blinkInterval < blinkInterval / 2) ? 255 : 0;  // Alterna entre 255 e 0 a cada intervalo

// Desenha os pinos com efeito de piscar
/// Desenha os pinos com efeito de piscar
// modo Classificar: pads translucidos, para ver a foto (a peca) por baixo
const _classTransl = typeof modoClass !== 'undefined' && modoClass;
if (_classTransl) drawingContext.globalAlpha = 0.3;
if (scaleFactor >= 0.2) {
    for (let part of parts) {
        if (displayMode === "top" && part.side !== "T") continue;
        if (displayMode === "bottom" && part.side !== "B") continue;

        let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;

        for (let pin of part.pins) {
            // Calcular posição do pino na tela (uma vez só)
            let screenX = (pin.x + groupOffset) * scaleFactor + offsetX;
            let screenY = pin.y * scaleFactor + offsetY;

            // IGNORAR pino se estiver fora da tela — melhora o desempenho
            if (screenX < -20 || screenX > width + 20 || screenY < -20 || screenY > height + 20) continue;

            // A partir daqui, só processa pinos realmente visíveis
            let enlargedRadius = pin.radius * 1.9;
            let isPPnV = typeof pin.net === "string" && /^PP[0-9]V/.test(pin.net);

            noStroke();

            // Aplica a cor piscando ao pino selecionado e pinos conectados
            let _uv = (typeof pin.net === "string") ? parseVoltNum(userVolts[pin.net]) : null;
            if (selectedPin === pin || (selectedPin && pin.net === selectedPin.net)) {
                fill(blinkState === 255 ? color(255, 0, 255) : color(100, 180, 100));
            } else if (_uv != null) {                       // tensao MEDIDA -> cor da faixa
                let _c = voltBandColor(_uv); fill(_c[0], _c[1], _c[2]);
            } else if (typeof pin.net === "string" && pin.net.startsWith("VB")) {
                fill(255, 0, 0);
            } else if (typeof pin.net === "string" && pin.net.startsWith("VSW")) {
                fill(230, 200, 100);
            } else if (typeof pin.net === "string" && pin.net.startsWith("V")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("DV")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("PWR")) {
                fill(255, 100, 100);
            } else if (typeof pin.net === "string" && pin.net.startsWith("RF")) {
                fill(0, 130, 0);
            } else if (typeof pin.net === "string" && pin.net.startsWith("PP_VDD")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("PP_BAT")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("PP_VS")) {
                fill(255, 70, 70);
             } else if (typeof pin.net === "string" && pin.net.startsWith("0P")) {
                fill(255, 70, 70);
             } else if (typeof pin.net === "string" && pin.net.startsWith("1P")) {
                fill(255, 70, 70);
             } else if (typeof pin.net === "string" && pin.net.startsWith("2P")) {
                fill(255, 70, 70);
             } else if (typeof pin.net === "string" && pin.net.startsWith("3P")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("4P")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("5P")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("5V")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("1V")) {
                fill(255, 70, 70);
            } else if (typeof pin.net === "string" && pin.net.startsWith("2V")) {
                fill(255, 70, 70);
            } else if (isPPnV) {
                fill(230, 200, 100);
            } else if (pin.net === "GND") {
                fill(120, 120, 120);
            } else if (pin.net === "NC") {
                fill(100, 130, 180);
            } else if (pin.side === "B") {
                fill(255, 200, 0);
            } else if (pin.side === "TP") {
                fill(255, 255, 0);
            } else {
                fill(230, 200, 100);
            }

            // Borda para PPnV
            if (isPPnV) {
                stroke(200, 50, 50);
                strokeWeight(1.5);
            } else {
                noStroke();
            }

            // Desenhar o pino
            if (pin.outlineRelative && pin.outlineRelative.length >= 4) {
                beginShape();
                for (let j = 0; j < pin.outlineRelative.length; j += 2) {
                    let vx = pin.x + pin.outlineRelative[j];
                    let vy = pin.y + pin.outlineRelative[j + 1];
                    vertex(vx + groupOffset, vy);
                }
                endShape(CLOSE);
            } else {
                if (part.name && ['u', 'a', 'nfc', '1', 'n', 'tp'].some(prefix => part.name.toLowerCase().startsWith(prefix))) {
                    ellipse(pin.x + groupOffset, pin.y, enlargedRadius, enlargedRadius);
                } else {
                    rect(pin.x + groupOffset - enlargedRadius / 2, pin.y - enlargedRadius / 2, enlargedRadius, enlargedRadius);
                }
            }

            // === DESENHAR TEXTOS APENAS EM ZOOM GRANDE ===
            if (
                scaleFactor >= 4.0 &&
                screenX > 0 && screenX < width &&
                screenY > 0 && screenY < height
            ) {
                push();
                fill(255);
                noStroke();
                textAlign(CENTER, CENTER);

                translate(0, height);
                scale(1, -1);

                textSize(min(pin.radius * 0.8, 20));
                text(pin.number || pin.name || "", pin.x + groupOffset, height - pin.y - 1);

                if (typeof pin.net === "string" && pin.net.length > 0) {
                    textSize(min(pin.radius * 0.1, 4));
                    text(pin.net, pin.x + groupOffset, height - pin.y + 8);
                }

                pop();
            }

            // === DESENHAR NET NO CENTRO DO PINO SE TIVER OUTLINE E ZOOM GRANDE ===
            if (
                scaleFactor >= 4.0 &&
                pin.net &&
                pin.outlineRelative && pin.outlineRelative.length >= 4 &&
                screenX > 0 && screenX < width &&
                screenY > 0 && screenY < height
            ) {
                push();
                fill(0);
                noStroke();
                textAlign(CENTER, CENTER);

                // Centro aproximado da área do pino
                let centerX = pin.x + groupOffset + (pin.outlineRelative[0] + pin.outlineRelative[2]) / 2;
                let centerY = pin.y + (pin.outlineRelative[1] + pin.outlineRelative[3]) / 2;

                textSize(min(pin.radius * 0.5, 12));

                let netText = pin.net;
                let lines = [];
                for (let i = 0; i < netText.length; i += 6) {
                    lines.push(netText.slice(i, i + 6));
                }

                let lineHeight = textSize() * 1.2;
                for (let i = 0; i < lines.length; i++) {
                    text(
                        lines[i],
                        centerX * scaleFactor + offsetX,
                        (centerY + (i - (lines.length - 1) / 2) * lineHeight) * scaleFactor + offsetY
                    );
                }

                pop();
            }

            noStroke();
        }
    }
}
if (_classTransl) drawingContext.globalAlpha = 1;
if (typeof classDesenhar === 'function') classDesenhar();   // tipos das pecas (classificar.js)




    
    
    drawSelectedNetConnections();
   
    drawPartNames();
    desenharCursorCruzado();   // o mesmo ponto na outra face (tecla C)

    pop(); // Fin T3: Traslación y escalado
    pop(); // Fin T2: Reflejo horizontal
    pop(); // Fin T1: Rotación

    // Dibujar el tooltip sin transformaciones
    drawTooltip();
    ajusteDesenharAviso();    // mostra o ajuste da foto enquanto se mexe nele
}


 
 //////////////////////////
 // FUNCIONES DE CONVERSIÓN
 //////////////////////////
 
 // Función para el click y tooltip (transformación completa)
function worldToScreen(wx, wy) {
    let p = createVector(wx, wy);

    // T3: Traslación y escalado
    p.x = p.x * scaleFactor + offsetX;
    p.y = p.y * scaleFactor + offsetY;

    // T2: Flip horizontal (si está activo)
    if (flipHorizontal) {
        p.x = width - p.x;
    }

    // T1: Rotación global
    let cx = width / 2;
    let cy = height / 2;
    p.sub(createVector(cx, cy));
    let cosA = Math.cos(rotationAngle);
    let sinA = Math.sin(rotationAngle);
    let xRot = p.x * cosA - p.y * sinA;
    let yRot = p.x * sinA + p.y * cosA;
    p.set(xRot, yRot);
    p.add(createVector(cx, cy));

    return { x: p.x, y: p.y };
}



function screenToWorld(mx, my) {
    let p = createVector(mx, my);
    let cx = width / 2, cy = height / 2;

    // Invertir T1: Deshacer la rotación global (inversa)
    p.sub(createVector(cx, cy));
    let cosA = Math.cos(-rotationAngle);
    let sinA = Math.sin(-rotationAngle);
    let xNew = p.x * cosA - p.y * sinA;
    let yNew = p.x * sinA + p.y * cosA;
    p.set(xNew, yNew);
    p.add(createVector(cx, cy));

    // Invertir T2: Deshacer flip horizontal (si está activo)
    if (flipHorizontal) {
        p.x = width - p.x;
    }

    // Invertir T3: Deshacer traslación y escalado
    p.x = (p.x - offsetX) / scaleFactor;
    p.y = (p.y - offsetY) / scaleFactor;

    return { x: p.x, y: p.y };
}



// Funciones para el zoom (ignorando el flip horizontal)

// Convertir de pantalla a "mundo" para el zoom: se invierte primero T3 (traslación y escala) y luego T1 (rotación global)
function screenToWorldZoom(mx, my) {
    let p = createVector(mx, my);

    // Invertir T3: Traslación y escalado
    p.x = (p.x - offsetX) / scaleFactor;
    p.y = (p.y - offsetY) / scaleFactor;

    // Invertir T1: Deshacer la rotación global alrededor del centro
    let cx = width / 2;
    let cy = height / 2;
    p.sub(createVector(cx, cy));
    let cosA = Math.cos(-rotationAngle);
    let sinA = Math.sin(-rotationAngle);
    let xNew = p.x * cosA - p.y * sinA;
    let yNew = p.x * sinA + p.y * cosA;
    p.set(xNew, yNew);
    p.add(createVector(cx, cy));

    return { x: p.x, y: p.y };
}

// Convertir de "mundo" a pantalla para el zoom: se aplica primero T1 (rotación global) y luego T3 (traslación y escala)
function worldToScreenZoom(wx, wy) {
    let p = createVector(wx, wy);

    // Aplicar T1: Rotación global alrededor del centro
    let cx = width / 2;
    let cy = height / 2;
    p.sub(createVector(cx, cy));
    let cosA = Math.cos(rotationAngle);
    let sinA = Math.sin(rotationAngle);
    let xNew = p.x * cosA - p.y * sinA;
    let yNew = p.x * sinA + p.y * cosA;
    p.set(xNew, yNew);
    p.add(createVector(cx, cy));

    // Aplicar T3: Traslación y escalado
    p.x = p.x * scaleFactor + offsetX;
    p.y = p.y * scaleFactor + offsetY;

    return { x: p.x, y: p.y };
}

// Función de zoom centrado en el mouse usando las funciones para zoom (sin flip horizontal)
function mouseWheel(event) {
    if (modoAjuste || keyIsDown(17)) {   // escala a FOTO da metade sob o mouse
        // Shift+roda: o Chrome manda a roda como rolagem HORIZONTAL (deltaY=0, vem em
        // deltaX) e o sentido saia sempre o mesmo. Usa o eixo que tiver movimento.
        const d = event.deltaY || event.deltaX || event.delta || 0;
        const f = d > 0 ? 1 / 1.004 : 1.004;
        ajusteApontar(mouseX, mouseY);
        // Y: segurar a tecla Y + roda. O Alt+roda ficou como alternativa, mas no Windows
        // o navegador sequestra o Alt (barra de menus) e muitas vezes ele nao chega aqui.
        const eixoY = event.altKey || keyIsDown(89);
        ajusteEscalar(f, event.shiftKey ? 'x' : (eixoY ? 'y' : null));
        clearTimeout(window.__salvaTimer);
        window.__salvaTimer = setTimeout(ajusteSalvarSeMexeu, 800);
        return false;
    }
    // Convertir la posición del mouse a coordenadas "mundo" (para zoom)
    let worldBefore = screenToWorldZoom(mouseX, mouseY);

    // Ajustar el factor de zoom: 0.9 para alejar, 1.1 para acercar
    let zoomFactor = event.delta > 0 ? 0.9 : 1.1;
    scaleFactor *= zoomFactor;

    // Calcular la nueva posición en pantalla para ese mismo punto del mundo (usando la conversión para zoom)
    let screenAfter = worldToScreenZoom(worldBefore.x, worldBefore.y);

    // Ajustar los offsets para que el punto bajo el mouse permanezca fijo
    offsetX += (mouseX - screenAfter.x);
    offsetY += (mouseY - screenAfter.y);

    return false;
}










 
 //////////////////////////
 // INTERACCIÓN
 //////////////////////////
 
 // Dibujar el tooltip "derecho" (sin rotación ni escala)
 function drawTooltip() {
     if (tooltip) {
         let screenPos = worldToScreen(tooltip.x, tooltip.y);
         push();
         resetMatrix(); // Resetea las transformaciones para dibujar el texto sin afectar
         textAlign(LEFT, TOP);
         textSize(14);
         noStroke();
         let padding = 4;
         let txt = tooltip.text;
         let txtWidth = textWidth(txt);
         fill(255, 255, 255, 120);//AMARWELO CAIXINHA DE INFORMAÇOES
         rect(screenPos.x, screenPos.y - 20, txtWidth + padding * 2, 40, 4);
         fill(0);
         text(txt, screenPos.x + padding, screenPos.y - 20 + padding);
         pop();
     }
 }
 
 // Detecta el click convirtiendo las coordenadas de pantalla a mundo
 
function mousePressed() {
    if (typeof classMouse === 'function' && classMouse('press')) return false;   // modo Classificar (Q)
    if (modoAjuste || keyIsDown(17)) {
        // marca o ponto de retorno ANTES do gesto: assim o Ctrl+Z desfaz o arrasto
        // inteiro de uma vez, e nao pixel a pixel
        ajusteApontar(mouseX, mouseY);
        ajusteMarco();
        return false;                                 // ajustando a foto, nao selecionando
    }
    // Converter posição do mouse para coordenadas do mundo
    let worldPos = screenToWorld(mouseX, mouseY);
    let mx = worldPos.x;
    let my = worldPos.y;
    let found = false;

    for (let part of parts) {
        if (displayMode === "top" && part.side !== "T") continue;
        if (displayMode === "bottom" && part.side !== "B") continue;
        let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;

        for (let pin of part.pins) {
            // Calcula o centro da pad
            let worldX = pin.x + groupOffset;
            let worldY = pin.y;

            // Verifica se o clique está dentro da pad
            let hit = false;
            if (pin.outline && pin.outline.length) {
                const poly = pin.outline.map(v => ({
                    x: v.x + worldX,
                    y: v.y + worldY
                }));
                hit = pointInPolygon(mx, my, poly);
            } else {
                hit = dist(mx, my, worldX, worldY) <= pin.radius;
            }

            if (hit) {
    // o pino clicado, MESMO sendo GND/NC (que nao viram selectedPin): o caderno precisa
    // dele para anotar diodo em pino sem malha como PECA.PINO (medicoes.js)
    window.pinoClicado = pin;
    const tipPos = { x: worldX, y: worldY, side: part.side };
    let tooltipText;

    if (pin.net === "GND" || pin.net === "NC") {
        tooltipText = `Parte: ${part.name} /  PINO: ${pin.net}`;
        selectedPin = null;
    } else {
        tooltipText = `COMP: ${part.name}/ MALHA: ${pin.net} / PINO: ${pin.name}`;
        selectedPin = pin;
        actualizarRedSeleccionada();
    }

    tooltip = {
        text: tooltipText,
        ...tipPos
    };

    const pinDisplay = document.getElementById("pinDisplay");
    if (pinDisplay) {
        pinDisplay.textContent = tooltipText;   // nomes vem do .bvr e de renomeacao: nunca HTML
    }

    const voltageDisplay = document.getElementById("voltageDisplay");
    if (voltageDisplay) {
        const voltage = tensaoDoPino(pin);
        voltageDisplay.textContent = voltage ? voltage : '...';
    }

    // 👉 Chama a função para atualizar o container
    updateComponentInfo(part, pin);

    found = true;
    break;
}

        }
        if (found) break;
    }

    return false; // Evita comportamento padrão
}


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


 function mouseDragged() {
     if (typeof classMouse === 'function' && classMouse('drag')) return false;

     if (mouseButton === LEFT || mouseButton === RIGHT) {
 
         // Cambia el cursor a "grabbing" mientras se arrastra
         cursor('grabbing');
         let worldCurrent = screenToWorld(mouseX, mouseY);
         let worldPrev = screenToWorld(pmouseX, pmouseY);
         let dw = createVector(worldCurrent.x - worldPrev.x, worldCurrent.y - worldPrev.y);
         // Modo ajuste ligado (tecla A) ou Ctrl segurado: arrasta a FOTO, nao a vista
         if (modoAjuste || keyIsDown(17)) {
             ajusteApontar(mouseX, mouseY);
             if (keyIsDown(16)) {      // Shift: gira em vez de mover
                 // angulo entre o centro da metade e o mouse, antes e depois
                 const c = ajusteCentroDaSecao();
                 if (c) {
                     const a1 = Math.atan2(worldPrev.y - c.y, worldPrev.x - c.x);
                     const a2 = Math.atan2(worldCurrent.y - c.y, worldCurrent.x - c.x);
                     ajusteGirar(a2 - a1);
                 }
             } else {
                 ajusteMover(dw.x, dw.y);
             }
             return false;
         }
         // Como offset se aplica después del escalado, se actualiza en coordenadas de pantalla
         offsetX += dw.x * scaleFactor;
         offsetY += dw.y * scaleFactor;
         renderBuffer();
         return false;
     }
 }
 
 function mouseReleased() {
    if (typeof classMouse === 'function' && classMouse('release')) return false;
    isDragging = false; // Mostra os nomes novamente ao soltar o mouse
    cursor(modoAjuste ? 'grab' : 'default');
    // ao SOLTAR, grava o ajuste desta placa em build/ajustes/<placa>.json
    if (typeof ajusteSalvarSeMexeu === 'function') ajusteSalvarSeMexeu();
}
 
 
 
  //////////////////////////
 // OTRAS FUNCIONES (Parseo, etc.)
 //////////////////////////
 
 function renderBuffer() {
    buffer.clear();
    buffer.push();
    // Dibuja el contorno en sus coordenadas originales
    buffer.stroke(255, 255, 255, 0);
    buffer.noFill();
    buffer.beginShape();
   // for (let p of outlinePoints) {
       // buffer.vertex(p.x, p.y);
   // }
    buffer.endShape(CLOSE);
    buffer.pop();
}
 
 // Calcula la transformación global basándose en outlinePoints
 function calcularTransformacion() {
     if (outlinePoints.length === 0) return;
     // canvas ainda sem tamanho (janela oculta na hora do load): o fator sairia
     // NEGATIVO e a tela ficava preta sem erro nenhum
     if (width <= 40 || height <= 40) return;
     let minX = outlinePoints[0].x, maxX = outlinePoints[0].x;
     let minY = outlinePoints[0].y, maxY = outlinePoints[0].y;
     for (let p of outlinePoints) {
         if (p.x < minX) minX = p.x;
         if (p.x > maxX) maxX = p.x;
         if (p.y < minY) minY = p.y;
         if (p.y > maxY) maxY = p.y;
     }
     let contWidth = maxX - minX;
     let contHeight = maxY - minY;
     let margen = 20;
     let factorX = (width - 2 * margen) / contWidth;
     let factorY = (height - 2 * margen) / contHeight;
     scaleFactor = Math.min(factorX, factorY);
     offsetX = margen - minX * scaleFactor + (width - 2 * margen - contWidth * scaleFactor) / 2;
     offsetY = margen - minY * scaleFactor + (height - 2 * margen - contHeight * scaleFactor) / 2;
 }
 
 // Calcula el desplazamiento horizontal para componentes del lado inferior en modo "all"
 function computeBottomOffset() {
     let topMinX = Infinity, topMaxX = -Infinity;
     for (let part of parts) {
         if (part.side === "T") {
             for (let pin of part.pins) {
                 let r = pin.radius;
                 if (pin.x - r < topMinX) topMinX = pin.x - r;
                 if (pin.x + r > topMaxX) topMaxX = pin.x + r;
             }
         }
     }
     return (topMaxX - topMinX) + 50;
 }
 function drawOrthogonalLine(x1, y1, x2, y2) {
    console.log(`Linha de (${x1}, ${y1}) para (${x2}, ${y2})`);
    line(x1, y1, x2, y1); // horizontal
    line(x2, y1, x2, y2); // vertical
}

function drawBlueDot(x, y) {
    push();
    fill(255, 0, 255,); // VerMELHO PINO SELECIONADO
    strokeWeight(1);
    ellipse(x, y, 6, 6);
    pop();
}

function drawSelectedNetConnections() {
    if (!selectedPin) return;
    if (typeof linhasVerdesLigadas !== 'undefined' && !linhasVerdesLigadas) return;   // tecla K (cobre.js)

    push();
    strokeWeight(2);
    stroke(0, 255, 0); // Verde para la línea de conexión
    noFill();

    let connectedPoints = [];

    for (let part of parts) {
        let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;

        for (let pin of part.pins) {
            if (pin.net === selectedPin.net) {
                let px = pin.x + (part.side === "B" ? groupOffset : 0);
                let py = pin.y;
                connectedPoints.push({ x: px, y: py });
            }
        }
    }

    connectedPoints.sort((a, b) => a.x - b.x || a.y - b.y);

    console.log("Pontos conectados:");
    connectedPoints.forEach(p => {
        console.log(`(${p.x}, ${p.y})`);
        drawBlueDot(p.x, p.y);
    });

    for (let i = 1; i < connectedPoints.length; i++) {
        let p1 = connectedPoints[i - 1];
        let p2 = connectedPoints[i];
        console.log(`Linha: (${p1.x}, ${p1.y}) -> (${p2.x}, ${p2.y})`);
        drawOrthogonalLine(p1.x, p1.y, p2.x, p2.y);
    }
    

    pop();
}





function drawComponentBoundingBoxes() {
    let backgroundRects = [];

    for (let part of parts) {
        if (displayMode === "top" && part.side !== "T") continue;
        if (displayMode === "bottom" && part.side !== "B") continue;
        let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;

        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;

        if (part.outline && part.outline.length > 0) {
            for (let i = 0; i < part.outline.length; i += 2) {
                let relX = part.outline[i];
                let relY = part.outline[i + 1];

                let absX = part.origin.x + relX;
                let absY = part.origin.y + relY;

                minX = Math.min(minX, absX);
                maxX = Math.max(maxX, absX);
                minY = Math.min(minY, absY);
                maxY = Math.max(maxY, absY);
            }
        } else if (part.pins && part.pins.length > 0) {
            for (let pin of part.pins) {
                let pinX = pin.x + part.origin.x;
                let pinY = pin.y + part.origin.y;
                minX = Math.min(minX, pinX);
                maxX = Math.max(maxX, pinX);
                minY = Math.min(minY, pinY);
                maxY = Math.max(maxY, pinY);
            }
        } else {
            continue; // Pular se não houver outline nem pinos
        }
        let x = minX + groupOffset;
        let y = minY;
        let w = maxX - minX;
        let h = maxY - minY;

        // Corrigido: Verifica se está completamente fora da tela
        let screenMin = worldToScreen(x, y);
        let screenMax = worldToScreen(x + w, y + h);

        let screenLeft   = Math.min(screenMin.x, screenMax.x);
        let screenRight  = Math.max(screenMin.x, screenMax.x);
        let screenTop    = Math.min(screenMin.y, screenMax.y);
        let screenBottom = Math.max(screenMin.y, screenMax.y);

        let completelyOffScreen =
            screenRight < 0 ||
            screenLeft > width ||
            screenBottom < 0 ||
            screenTop > height;

        if (completelyOffScreen) continue;


        backgroundRects.push({ 
            x, 
            y, 
            w, 
            h, 
            fillColor: determineFillColor(part)
        });
    }

    // Desenhar os retângulos visíveis
    noStroke();
    for (let rectData of backgroundRects) {
        fill(rectData.fillColor);
        rect(rectData.x, rectData.y, rectData.w, rectData.h);
    }

    // Desenhar bordas do componente
    stroke(150, 150, 150);
    noFill();
    strokeWeight(2);

    for (let rectData of backgroundRects) {
        rect(rectData.x, rectData.y, rectData.w, rectData.h);
    }
}

// Função de cor conforme o nome do componente
function determineFillColor(part) {
    if (part.name.startsWith("C")) {
        return color(255, 255, 150, 85);
    } else if (part.name.startsWith("R")) {
        return color(50, 50, 50, 100);
    } else if (part.name.startsWith("MIC")) {
        return color(255, 255, 150, 225);
    } else if (part.name.startsWith("N")) {
        return color(0, 0, 255, 0);
    // L e U eram preto solido: com os nomes de esquema (L1, U2) tapavam a foto
    } else if (part.name.startsWith("L")) {
        return color(30, 30, 30, 60);
    } else if (part.name.startsWith("ZD")) {
        return color(80, 80, 80, 125);
    } else if (part.name.startsWith("U")) {
        return color(10, 10, 10, 60);
    } else if (part.name.startsWith("u")) {
        return color(10, 10, 10, 60);
    } else if (part.name.startsWith("S")) {
        return color(128, 128, 128, 115);
    } else if (part.name.startsWith("H")) {
        return color(50, 50, 50, 120);
    } else if (part.name.startsWith("J")) {
        return color(200, 200, 200, 35);
    } else if (part.name.startsWith("D")) {
        return color(80, 80, 80, 125);
    } else if (part.name.startsWith("Q")) {
        return color(80, 80, 80, 125);
    } else if (part.name.startsWith("RF")) {
        return color(255, 255, 0, 105);
    } else if (part.name.startsWith("ANT")) {
        return color(128, 128, 128, 155);
    } else if (part.name.startsWith("PA")) {
        return color(50, 50, 50, 120);
    } else if (part.name.startsWith("F")) {
        return color(0, 0, 255, 75);
    } else {
        return color(255, 255, 0, 0);
    }
}

function drawPartNames() {
    if (scaleFactor < 1.1 || scaleFactor >= 4.0 || isDragging) return;

    push();
    resetMatrix();
    textAlign(CENTER, CENTER);
    fill(255);
    noStroke();

    for (let part of parts) {
        if (displayMode === "top" && part.side !== "T") continue;
        if (displayMode === "bottom" && part.side !== "B") continue;

        if (part.pins.length > 0) {
            let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;
            let sumX = 0, sumY = 0;

            for (let pin of part.pins) {
                sumX += pin.x;
                sumY += pin.y;
            }

            let centerX = sumX / part.pins.length + groupOffset;
            let centerY = sumY / part.pins.length;

            let centerScreen = worldToScreen(centerX, centerY);

            if (centerScreen.x >= 0 && centerScreen.x <= width && centerScreen.y >= 0 && centerScreen.y <= height) {
                textSize(12);
                text(part.name, centerScreen.x, centerScreen.y);
            }
        }
    }

    pop();
}

function parseFile() {
    let i = 0;
    while (i < fileContent.length) {
        let line = fileContent[i].trim();
        if (line.startsWith("PART_NAME")) {
            let tokens = line.split(/\s+/);
            let partName = tokens[1];
            let part = { name: partName, pins: [], outline: [] };
            i++;
            while (i < fileContent.length && !fileContent[i].trim().startsWith("PART_END")) {
                let innerLine = fileContent[i].trim();

                if (innerLine.startsWith("PART_SIDE")) {
                    let tokensSide = innerLine.split(/\s+/);
                    part.side = tokensSide[1]; // "T" ou "B"
                }

                if (innerLine.startsWith("PART_ORIGIN")) {
                    let tokensOrigin = innerLine.split(/\s+/);
                    part.origin = {
                        x: parseFloat(tokensOrigin[1]),
                        y: parseFloat(tokensOrigin[2])
                    };
                }

                if (innerLine.startsWith("PART_OUTLINE_RELATIVE")) {
                    let tokensOutline = innerLine.split(/\s+/);
                    tokensOutline.shift(); // remove "PART_OUTLINE_RELATIVE"
                    part.outline = tokensOutline.map(Number);
                }

                if (innerLine.startsWith("PIN_ID")) {
                    let pin = {};
                    i++;
                    while (i < fileContent.length && !fileContent[i].trim().startsWith("PIN_END")) {
                        let pinLine = fileContent[i].trim();
                        let tokensPin = pinLine.split(/\s+/);
                        switch (tokensPin[0]) {
                            case "PIN_NUMBER":
                                pin.number = tokensPin[1];
                                break;
                            case "PIN_NAME":
                                pin.name = tokensPin.slice(1).join(" ");
                                break;
                            case "PIN_ORIGIN":
                                pin.x = parseFloat(tokensPin[1]);
                                pin.y = parseFloat(tokensPin[2]);
                                break;
                            case "PIN_RADIUS":
                                pin.radius = parseFloat(tokensPin[1]);
                                break;
                            case "PIN_NET":
                                // apelido da malha (build/malhas.json); o nome cru fica guardado
                                pin.netOriginal = tokensPin.slice(1).join(" ");
                                pin.net = apelidoMalha(pin.netOriginal);
                                break;
                            case "PIN_OUTLINE_RELATIVE":
                                pin.outlineRelative = tokensPin.slice(1).map(Number);
                                break;
                        }
                        i++;
                    }
                    part.pins.push(pin);
                } else {
                    i++;
                }
            }
            parts.push(part);
        } else if (line.startsWith("OUTLINE_SEGMENTED")) {
            let tokens = line.split(/\s+/);
            tokens.shift();
            for (let j = 0; j < tokens.length; j += 2) {
                let x = parseFloat(tokens[j]);
                let y = parseFloat(tokens[j + 1]);
                outlinePoints.push({ x, y });
            }
            i++;
        } else {
            i++;
        }
    }
}


 
 function fillComponentDatalist() {
     let componentList = select('#componentList');
     let namesSet = new Set();
     for (let part of parts) {
         namesSet.add(part.name);
     }
     let namesArray = Array.from(namesSet);
     namesArray.sort();
     // DOM direto, nao o createElement do p5: o do p5 poe o conteudo via innerHTML,
     // e o nome (que pode ter sido renomeado por alguem) viraria HTML
     const lista = componentList.elt;
     lista.textContent = '';
     for (let name of namesArray) {
         const option = document.createElement('option');
         option.value = name;
         option.textContent = name;
         lista.appendChild(option);
     }
 }
 
 function centerOnComponent(componentName) {
     let foundPart = parts.find(
         (part) => part.name.toLowerCase() === componentName.toLowerCase()
     );
     if (foundPart && foundPart.pins.length > 0) {
         if (displayMode !== "all") {
             if (foundPart.side === "T" && displayMode !== "top") {
                 displayMode = "top";
             } else if (foundPart.side === "B" && displayMode !== "bottom") {
                 displayMode = "bottom";
             }
         }
         let sumX = 0,
             sumY = 0;
         for (let pin of foundPart.pins) {
             sumX += pin.x;
             sumY += pin.y;
         }
         let centerX = sumX / foundPart.pins.length;
         let centerY = sumY / foundPart.pins.length;
         let groupOffset = 0;
         if (displayMode === "all" && foundPart.side === "B") {
             groupOffset = computeBottomOffset();
         }
         offsetX = width / 2 - (centerX + groupOffset) * scaleFactor;
         offsetY = height / 2 - centerY * scaleFactor;
         tooltip = {
             text: `Componente: ${foundPart.name}`,
             x: centerX,
             y: centerY,
             side: foundPart.side,
         };
         // pins[0] costuma ser GND, que o clique evita de proposito: escolhe o primeiro
         // pino de malha de verdade e SINCRONIZA painel/cartao — antes a placa piscava
         // uma malha e V/D/N iam para a selecao anterior (revisao js-04)
         const pino = foundPart.pins.find(p => p.net !== 'GND' && p.net !== 'NC') || null;
         selectedPin = pino;
         window.pinoClicado = pino;
         if (pino) actualizarRedSeleccionada();
         updateComponentInfo(foundPart, pino);
         renderBuffer();
     } else {
         console.log("Componente no encontrado: " + componentName);
     }
 }
 
 function setupSearchListener() {
     let searchInput = select('#searchComponent');
     searchInput.changed(() => {
         let searchTerm = searchInput.value().trim();
         if (searchTerm !== "") {
             centerOnComponent(searchTerm);
         }
     });
 }
 
function moveToNextPinInNet() {
    if (!selectedPin) return;
    let sameNetPins = [];
    for (let part of parts) {
        for (let pin of part.pins) {
            if (pin.net === selectedPin.net) {
                sameNetPins.push({ pin, part, partSide: part.side, partName: part.name });
            }
        }
    }
    if (sameNetPins.length > 1) {
        let currentIndex = sameNetPins.findIndex(
            (item) => item.pin === selectedPin
        );
        let nextIndex = (currentIndex + 1) % sameNetPins.length;
        let nextItem = sameNetPins[nextIndex];
        if (displayMode !== "all") {
            if (nextItem.partSide === "T" && displayMode !== "top") {
                displayMode = "top";
                flipHorizontal = true;
            } else if (nextItem.partSide === "B" && displayMode !== "bottom") {
                displayMode = "bottom";
                flipHorizontal = false;
            }
        }
        let groupOffset =
            displayMode === "all" && nextItem.partSide === "B" ? bottomOffset : 0;
        selectedPin = nextItem.pin;
        window.pinoClicado = nextItem.pin;
        actualizarRedSeleccionada();
        updateComponentInfo(nextItem.part, nextItem.pin);   // painel acompanha o Enter

        tooltip = {
            text: `Parte: ${nextItem.partName}\nNet: ${nextItem.pin.net}`,
            x: nextItem.pin.x,
            y: nextItem.pin.y,
            side: nextItem.partSide,
        };
        offsetX = width / 2 - (selectedPin.x + groupOffset) * scaleFactor;
        offsetY = height / 2 - selectedPin.y * scaleFactor;
        //renderBuffer();
    }
}
function actualizarRedSeleccionada() {
    if (!selectedPin) {
        netLines = [];
        return;
    }

    let connectedPoints = [];

    for (let part of parts) {
        let groupOffset = (displayMode === "all" && part.side === "B") ? bottomOffset : 0;

        for (let pin of part.pins) {
            if (pin.net === selectedPin.net) {
                let px = pin.x + (part.side === "B" ? groupOffset : 0);
                let py = pin.y;
                connectedPoints.push({ x: px, y: py });
            }
        }
    }

    connectedPoints.sort((a, b) => a.x - b.x || a.y - b.y);

    netLines = [];

    for (let i = 1; i < connectedPoints.length; i++) {
        const p1 = connectedPoints[i - 1];
        const p2 = connectedPoints[i];
        netLines.push({ x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y });
    }
}
 
function windowResized() {
    resizeCanvas(windowWidth, windowHeight);
    // o buffer nasce com o tamanho da janela; se a pagina abriu numa janela ainda
    // sem tamanho ele fica 0x0 e nunca mais serve — refaz junto com o canvas
    if (!buffer || buffer.width !== width || buffer.height !== height) {
        buffer = createGraphics(width, height);
    }
    renderBuffer(); // Vuelve a dibujar el contenido después del ajuste
}

function keyPressed() {
    if (document.activeElement.tagName === "INPUT") {
        return; // Permite escribir en el input
    }
    return false; // Evita que p5.js bloquee la entrada
}
