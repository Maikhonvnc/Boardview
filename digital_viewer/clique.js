// Mouse: tooltip, clique num pino, arrastar e soltar.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)

 
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
