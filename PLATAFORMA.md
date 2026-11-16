# Plataforma interna de medições — decisões

Decisões do dono (out/2026) para a plataforma em que os técnicos registram e validam
tensões e leituras de diodo. O desenho completo está no Dossiê Boardview (artefato
"Dossiê Boardview"); aqui fica o que foi decidido e o que muda por causa disso.

## Decisões

| Assunto | Decisão |
|---|---|
| Onde roda | Servidor próprio da empresa, o mesmo onde roda o Grafana. |
| Acesso | Por link, **sem login**, **pelo Tailscale** (nenhuma porta aberta para a internet). Na primeira vez o técnico digita o nome; fica guardado no navegador e vai em cada leitura. |
| Arquivo oficial | O arquivo original de cada revisão de placa é o padrão. |
| Arquivos de placa | Podem ficar no servidor e ser servidos aos técnicos. |
| Time | 3 técnicos. Raramente usam ao mesmo tempo. |
| Placas físicas | Não haverá placa-padrão etiquetada: as placas são de clientes. Placa boa → mede e devolve; placa ruim → estuda. A placa física é identificada pela **OS**. |
| Validação | **3 leituras concordantes já validam.** O mesmo técnico pode contar mais de uma vez, desde que em placas físicas diferentes (OS diferentes). |
| Condições de tensão | Fonte (a placa reconhece que não há bateria, mas funciona) ou bateria. USB não liga o drone. Padrão: ligada há 15 s; também registrar a leitura "no boot" como informativa, porque alguns setores demoram a subir. |
| Leitura sem login | Vota — basta o nome digitado. |
| Moderação | Só o dono. |
| Backup | Cópia em cada PC de bancada. |
| GalvaoDrones | Não precisa integrar; se um dia for cômodo, pode. |

## O que muda em relação ao desenho original

- **Regra de validação.** O desenho pedia 3 *pessoas* e 2 *placas*. Com 3 técnicos e o
  mesmo modelo voltando várias vezes, o voto passa a ser por **(técnico, OS)**: a mesma
  pessoa medindo duas placas de clientes diferentes conta duas vezes; medindo a mesma
  placa de novo, substitui o voto anterior. **Validado = 3 votos concordantes**, em pelo
  menos 2 OS diferentes, sem grupo divergente com 2 votos ou mais.
- **Placa física = OS.** O campo "placa física" vira o número da OS, obrigatório nas
  leituras de placa boa. Sem OS, a leitura fica guardada mas não vota.
- **Acesso sem login exige rede fechada.** Sem login, qualquer um que alcance o link lê e
  grava. O central precisa ficar acessível só pela rede da loja ou pelo Tailscale —
  nunca exposto na internet, mesmo atrás do proxy do Grafana. O nome digitado identifica,
  mas não autentica: serve para saber quem mediu, não para impedir alguém de se passar
  por outro. Dentro de um time de 3, é aceitável.
- **Relógio do PC.** Com uso raramente simultâneo, a ordem dos votos pode usar a hora de
  chegada no central sem a sequência por bancada; a sequência continua útil para não
  perder leitura, não para ordenar.
- **Backup** vai para cada PC de bancada (além do próprio servidor), com uma restauração
  testada.

## Tailscale (como o central vai ficar acessível)

- Instalar o Tailscale no servidor da empresa e nos PCs de bancada, todos na mesma rede
  (tailnet), entrando com a mesma conta da empresa.
- No servidor, o `servidor.py` continua escutando só em `127.0.0.1`. O Tailscale publica
  ele para a tailnet com HTTPS: `tailscale serve --bg 8777`. O endereço fica
  `https://<nome-da-maquina>.<tailnet>.ts.net/`.
- O `servidor.py` só atende nomes conhecidos. Pôr o nome do Tailscale em
  `BOARDVIEW_HOSTS` antes de iniciar, sem porta (o HTTPS do `serve` usa a 443):
  `BOARDVIEW_HOSTS=<nome-da-maquina>.<tailnet>.ts.net`. Se o navegador mostrar erro 421
  ("host nao reconhecido"), é este nome que está faltando ou escrito diferente.
- Não usar `tailscale funnel`: ele abre para a internet, e o acesso é sem login.

## Fase 1 — caderno de bancada (feita, out/2026)

Cada V / Shift+V e D / Shift+D vira uma leitura gravada em `dados/medicoes.sqlite3`
(mais um espelho legível `dados/leituras-AAAA-MM-DD.jsonl`), com técnico, OS, papel
(reparo/referência), condição (fonte/bateria, 15 s/boot) e a malha original. Bloco
**CADERNO** no topo do painel: nome do técnico, OS, condição, situação da fila e CSV.

- Nada se perde: a leitura entra primeiro numa fila no navegador e só sai quando o
  servidor confirma que gravou em disco. Sem servidor, espera e reenvia sozinha; reenvio
  não duplica. Leitura recusada fica registrada no banco (tabela `recusa`).
- O nome é pedido antes do valor, na primeira vez. Enter num valor já anotado (mesma OS)
  não cria leitura nova. Apagar grava um "retira" que aponta para a leitura apagada.
- Referência (Shift+V) e placa da bancada (V) têm valores separados na tela.
- Exportar: link CSV no painel, ou `python medicoes_db.py csv [placa]`.
- Ainda local em cada PC; a fase 2 junta tudo no servidor da empresa.

## Fase 2 — central e "validado por N" (código pronto, out/2026; falta instalar)

Servidor da empresa: **Linux, Grafana instalado direto (systemd)**, pelo Tailscale.
Passo a passo de instalação: **`servidor-central/LEIAME.md`**.

- [x] `consenso.py`: a regra, num lugar só. Voto = (técnico, OS); só placa boa com OS;
  "boot" e placa em reparo não votam; última leitura do par vale; "retira" cancela.
  Validado = 3 votos concordantes em 2 OS ou mais, 80% no grupo principal, sem outro
  grupo com 2 votos. 21 testes (`teste_consenso.py`, no scratchpad da sessão).
- [x] `GET /api/consenso?placa=` → `{fp, origem, tolerancia, versoes: {fp: {alvo: {tipo:
  {condicao: resultado}}}}}`. Na bancada vem do central (e fica uma cópia em
  `dados/consenso/`); central fora → a cópia; sem cópia → só as leituras do PC, com aviso.
- [x] Servidor com uma thread por conexão e `timeout = 15` (uma conexão presa não congela
  mais os outros); serviço systemd + `instalar.sh` + `empacotar_central.py`.
- [x] Sincronização: `servidor.py` vira **bancada** quando tem o endereço do central em
  `central.txt` (ou `BOARDVIEW_CENTRAL`). Uma thread manda as leituras novas em ordem de
  `seq` (tabela `sync` guarda até onde o central confirmou; reenviar não duplica), logo
  após cada leitura e a cada 30 s (até 5 min com o central fora). Leitura que o central
  recusa fica na tabela `recusa` dele. `python medicoes_db.py reenviar` manda tudo de novo
  (depois de restaurar o central). Situação: `GET /api/sync` e o bloco CADERNO.
- [x] Viewer: linhas **REF FONTE/BATERIA** e **REF DIODO** no painel ("0,55 · validado ·
  3 votos (2 OS) · 0,549–0,552"); verde validado, âmbar divergente, vermelho quando a
  leitura DESTA placa cai fora da faixa ("ESTA PLACA 1.300 ⚠").
- [x] Backup: no central, todo dia às 03:00 (`boardview-backup.timer`, 30 cópias); em cada
  PC, cópia do banco central a cada 6 h em `dados/copia-central/` (14 dias). Toda cópia é
  aberta e tem o consenso recalculado antes de ser guardada (restauração de teste).
- [ ] **Instalar no servidor** (falta: Tailscale nos PCs e no servidor; `instalar.sh` ainda
  não rodou num Linux de verdade — só a sintaxe foi conferida, e o pacote foi testado
  extraído e rodando no Windows).
- [ ] `central.txt` em cada um dos 3 PCs.

Testes (scratchpad da sessão): `teste_central.py` sobe um central e uma bancada de verdade
— sincronização, consenso, retira, central fora/voltando, cópia, restauração + reenviar,
conexão presa —, e `rodar_regressao.py` repassa os 48 testes de segurança e os do caderno
no servidor com threads.

## Pré-requisito já feito (out/2026)

Correções de segurança antes de pôr o servidor na rede:
- `servidor.py`: lista branca de caminhos, sem fuga de pasta, sem listagem, checagem de
  Host (`BOARDVIEW_HOSTS` para o nome do servidor da empresa), POST só JSON da mesma
  origem, para placa existente e com campos validados; guarda a versão anterior.
- Viewer: nada que vem de dado entra como HTML (`escHTML`/`textContent`); tensão e diodo
  validados na digitação.

Dois atacantes testaram as correções. A leitura de arquivo fora da lista branca resistiu a
mais de 20 variações (dupla codificação, nomes 8.3, UNC, ponto/espaço no fim, junctions,
`/_drones/`), a gravação vinda de outro site não passou, e o viewer digital não executou
nada vindo de `.bvr` malicioso nem do localStorage.

## Pendências de segurança (decidido: não urgentes)

O dono decidiu não ir além de impedir a leitura de arquivos da máquina. O que os
atacantes acharam e ficou para depois:

- ~~Servidor de uma thread só, sem timeout~~ — resolvido na fase 2 (thread por conexão,
  `timeout = 15`).
- ~~JSON muito aninhado no POST derruba o servidor~~ e ~~mensagem de erro com quebra de
  linha vira cabeçalho~~ — resolvidos junto com o caderno (fase 1).
- **Páginas geradas com dado dentro de `<script>`**: `Malhas/*.html` (`gen_malhas.py`) e
  `HUB.html` (`gen_hub.py`) não escapam `</`, então um nome de malha malicioso num `.pcb`
  rodaria código na mesma origem. Escapar `<`, `>` e `&` no `json.dumps`.
- **`/_drones/` entrega `.html`/`.js` como página ativa.** Um HTML que estiver na pasta de
  dados roda na mesma origem. Servir só PDF, imagem e `.pcb` dali, ou com
  `Content-Disposition: attachment`.
- **`viewer.html` antigo** monta HTML cru e aceita `?board=../`. Hoje o script dele nem
  roda (falta o `</script>`); a revisão já recomenda aposentá-lo.
- **Menu do modelo** abre URL do `modelos.json` sem conferir o esquema (`javascript:`).
- **Sem Content-Security-Policy.** O `eval` do `skin.js` e os scripts inline impedem uma
  política estrita.
