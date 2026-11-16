// draw() do p5: fundo, contorno, pinos e as camadas dos outros modulos.
// (parte do antigo SCRIPT3.js, dividido em 11/2026 — a ordem dos <script> no index.html importa:
//  nucleo, tensao, inicio, desenho, vista, clique, painel, pecas, bvr, busca)

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
