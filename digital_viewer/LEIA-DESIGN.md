# Viewer DigitalBoard — redesenho (IMPLEMENTADO)

> **Estado:** o redesenho de `Viewer redesign Galv/Viewer Galvao.dc.html` ja esta aplicado.
> Este documento deixou de ser um briefing e passou a descrever o que existe.

Ferramenta local de reparo de placas de drone DJI. Mostra o **boardview** (pads, malhas,
componentes) sobre a **foto real** da placa, alinhada. Usada na bancada, com multímetro na mão.

Não é um site: roda num servidor local (`servidor.py`, porta 8777), offline, num PC só.

---

## O que mexer

| arquivo | o que é |
|---|---|
| `index.html` | estrutura + **todo o CSS** (é aqui que o design mora) |
| `SCRIPT3.js` | motor de desenho em p5.js — **não é para redesenhar**, só para ler |
| `ajuste_fundo.js` | alinhamento manual da foto |
| `face_unica.js` | dobra as duas faces numa só |
| `menu_modelo.js` | menu do modelo + botão HUB |
| `skin.js` | aparência: sincroniza estado→interface, `rotular()`, painel recolhível |
| `assets/` | `RaceSport.ttf` e `gd-logo-white.svg` — locais, nada de CDN |
| `renomear.js` | renomear componentes |

O canvas do p5 ocupa a tela inteira; tudo o mais é HTML sobreposto. **O redesenho é dos
elementos HTML e do CSS** — a placa em si é desenhada no canvas e não se estiliza por CSS.

---

## Estado atual da interface

- **Barra superior** (`#topbar`): logo da Galvão = HUB, nome da placa + face atual, os dois
  seletores (placa e modelo) e a busca. É o grupo **navegar**.
- **Painel esquerdo** (`#componentInfo`, 286 px, recolhe para 52 px pelo puxador ou por `Tab`):
  dados do componente, totais da placa, malha e renomear.
- **Cartão de tensão** (`#voltCard` / `#voltageDisplay`): nome da malha e o valor medido.
  Acompanha o painel quando ele recolhe.
- **Dock inferior** (`#controls`): todos os botões, agrupados e separados por divisórias.
- **Modal** (`#componentModal`): lista os componentes da malha.
- **Aviso** (`#avisoAjuste`, criado por JS): pílula laranja acima do dock. A altura do dock é
  **medida** pelo `skin.js` (ele quebra em várias linhas em tela estreita), senão o aviso cobria
  os botões.

### Dock, na ordem em que está

**ver** `TOP` `BOTTOM` `AMBOS` `2 FACES` (segmentado, o ativo fica laranja) · `girar` `espelhar` ·
`FOTO/BORDAS/SEM FUNDO` — **medir** `TENSÃO` `PRÓXIMO` — **alinhar** `AJUSTE` `desfazer`

O modo AJUSTE é visivelmente um modo: o botão acende e a tela ganha moldura laranja.

---

## Atalhos que precisam continuar existindo

Quem usa isso está com a placa na bancada e uma mão só livre. O teclado importa mais que o mouse.

`Tab` recolhe o painel · `/` foca a busca ·
`A` modo ajuste · `Enter` próximo pino da malha · `V` tensão · `N` renomear · `F` face única ·
`C` cursor cruzado · `T` trocar metades · `H`/`J` espelhar · `[`/`]` girar · `S` escala ·
setas mover · `Ctrl+Z`/`Ctrl+Y` desfazer/refazer · `R` zerar metade · `Shift+R` zerar placa ·
`E` exportar

Se o redesenho criar botões novos, eles não substituem os atalhos.

---

## DUAS ARMADILHAS — leia antes de mexer

**1. Um `<select>` (ou qualquer controle) não funciona se os eventos chegarem ao p5.**
O p5 escuta o mouse na janela e chama `preventDefault()`, o que impede um `<select>` nativo de
abrir. Todo controle novo tem que ficar **dentro** de `#controls`, `#componentInfo` ou
`#componentModal` — esses três já barram a propagação (`protegerControles()` em `SCRIPT3.js`).
Fora deles, o controle nasce morto e **sem nenhum erro no console**. A barra de cima (`#topbar`) e
o puxador do painel (`#btnPainel`) ficam fora dos três, por isso o `skin.js` repete a proteção
neles — qualquer container novo precisa do mesmo tratamento.

**3. Não escreva `innerHTML` num botão do dock.** Os botões carregam um `<svg>` inline; escrever
`innerHTML` apaga o ícone. Use `rotular(botao, 'TEXTO')`, que troca só o `<span data-rot>`.

**2. Id duplicado quebra funcionalidade em silêncio.**
Já aconteceu aqui: `componentList` existia na `<datalist>` da busca e numa `<div>` do modal; o
`select('#componentList')` pegava a div e a busca ficou vazia por tempo indeterminado. Nenhum
erro, nenhum aviso.

Corolário: **testar um controle setando valor por JavaScript não prova nada** — esse caminho
passa por cima exatamente do que costuma estar quebrado. Clique de verdade.

---

## Restrições técnicas

- **Sem build, sem npm, sem framework.** HTML + CSS + JS solto, servidos como arquivo. Pode usar
  CSS moderno à vontade (roda em Chrome/Edge atual), mas nada que precise compilar.
- **p5.js 1.x** é dependência do motor de desenho; não dá para remover.
- **Offline.** Nada de CDN, Google Fonts ou qualquer coisa de rede — a bancada pode não ter
  internet. O link do Google Fonts saiu: a Orbitron foi trocada pela **RaceSport**, servida de
  `assets/RaceSport.ttf`.
- O servidor manda `Cache-Control: no-store`, então recarregar já pega a versão nova.

## Como rodar

```
cd C:\Users\usuario\Documents\Boardview
python servidor.py
```
Depois `http://127.0.0.1:8777/digital_viewer/index.html`

---

## Contexto de uso, que deveria guiar o visual

- **Ambiente de bancada**: luz forte, a pessoa alterna entre olhar a placa física e a tela.
  O tema escuro atual faz sentido; contraste alto importa mais que elegância.
- **Um pad tem poucos pixels na tela.** Nada de interface pode cobrir o centro do canvas, e as
  cores da interface não devem competir com as do overlay: ciano (pinos), amarelo (contorno),
  magenta (cursor cruzado), verde (malha selecionada).
- **A pessoa está com as mãos ocupadas.** Menos cliques, mais teclas, alvos grandes.
- O painel esquerdo de 220 px come uma fatia relevante da tela em monitor pequeno — vale pensar
  se ele deve poder recolher.

## Paleta

`--bg #0B100E` · `--painel #0F1512` · `--cartao #131A17` · `--borda #24302B` · `--borda2 #3A4A44`
`--txt #E6EDE9` · `--mudo #8A9A93` · `--ac #EF7E13` (laranja da marca) · `--ac2 #F5B072`

As cores da interface foram escolhidas para **não competir** com as do overlay no canvas: ciano
(pinos), amarelo (contorno), magenta (cursor cruzado), verde (malha selecionada).
