// Busca de componente, proximo pino da malha, malha selecionada, resize e teclado.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)


 
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
