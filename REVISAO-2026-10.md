# Revisão de outubro/2026 — achados consolidados

Gerada por 6 revisores (rotas, sync, viewer, deploy, dados, carga) e conferida por verificadores
independentes. As linhas citadas são do código de outubro. "Conferido" = o que os verificadores
concluíram; "antes" = quantos deles disseram que convém resolver antes de instalar o central.

**Situação em 2026-11-16:** os itens marcados ✔ foram corrigidos; o resto está aberto.


## Crítico

| | Área | Achado | Conferido | Antes | Arquivo |
|---|---|---|---|---|---|
| ✔ | dados | Valor igual ao anterior é descartado mesmo quando muda a condição (boot→15 s, fonte→bateria) ou o técnico: a leitura que vota não é gravada | confirmed | 2/2 | `digital_viewer/medicoes.js` |
| ✔ | viewer | Leitura em outra condição com o mesmo valor é descartada sem aviso (bateria e 15 s depois de fonte e boot) | confirmed | 2/2 | `digital_viewer/medicoes.js` |

## Médio

| | Área | Achado | Conferido | Antes | Arquivo |
|---|---|---|---|---|---|
|  | carga | A cópia em cada PC só acontece com o Viewer.bat aberto, mas o LEIAME manda o técnico usar o link do central | nao verificado |  | `servidor-central/LEIAME.md` |
|  | carga | /api/backup (e o CSV) vão numa única escrita: no Linux, o timeout = 15 vira prazo TOTAL para a resposta inteira | nao verificado |  | `servidor.py` |
|  | carga | /api/consenso relê e recalcula todas as leituras da placa a cada pedido, inclusive as de reparo; sob carga a bancada mostra 'cópia, central fora' com o central no ar | nao verificado |  | `servidor.py` |
|  | carga | Cópia do banco central: quando falha, a bancada baixa o banco inteiro de novo a cada leitura, e a falha não aparece na tela | nao verificado |  | `servidor.py` |
|  | dados | 'Última leitura do par' segue a ordem de chegada no central: uma leitura velha que sincroniza tarde vence a correção | confirmed | 0/1 | `consenso.py` |
|  | dados | Nome do técnico e OS sem normalizar: uma placa conta como 2 OS e uma pessoa como 2 votos | confirmed | 0/1 | `consenso.py` |
|  | dados | Restaurar o central perde as leituras feitas pelo link do central, e 'reenviar' não as recupera | confirmed | 0/1 | `servidor-central/LEIAME.md` |
|  | dados | 'ESTA PLACA ⚠' compara o consenso com valor de outra placa (outra OS) e de outra condição | confirmed/partly | 2/2 | `digital_viewer/medicoes.js` |
|  | dados | Não há como retirar os votos de uma placa que não era boa (a moderação 'só o dono' não tem ferramenta) | nao verificado |  | `medicoes_db.py` |
|  | dados | Apagar depois de corrigir faz o valor errado voltar a valer como voto | partly | 0/2 | `consenso.py` |
|  | dados | Diodo digitado em mV (550) entra como 550 V e trava a validação; a partir de 1000 mV é recusado | partly | 1/2 | `medicoes_db.py` |
|  | deploy | Na restauração, o `reenviar` não devolve o que foi medido pelo link do central, e o espelho JSONL fica com seq repetido | confirmed | 0/1 | `servidor-central/LEIAME.md` |
|  | deploy | Expiração da chave do Tailscale (180 dias por padrão) tira o central do ar para todos | confirmed | 1/1 | `servidor-central/LEIAME.md` |
|  | deploy | O pacote padrão vai sem PDFs: o menu 'mapas e fotos' do viewer e os links do HUB dão 404 no central, e o env/LEIAME dizem que só o HUB perde | confirmed | 1/1 | `servidor-central/boardview.env.exemplo` |
| ✔ | deploy | Se o .bvr do PC for de outra versão que o do central, a leitura é recusada para sempre e o painel mostra "central em dia" | partly | 1/2 | `medicoes_db.py` |
|  | rotas | CSV com ponto decimal e separador ';' é lido errado pelo Excel em pt-BR | confirmed | 0/1 | `medicoes_db.py` |
| ✔ | rotas | Central recusa leitura por .bvr diferente, a bancada conta como entregue e mostra "central em dia"; depois de atualizar o central as leituras nunca sobem | partly | 3/3 | `servidor.py` |
|  | sync | Cópias (PC e servidor) aceitam banco menor ou vazio e a rotação apaga as boas; central zerado ou restaurado não é detectado pelas bancadas | confirmed | 0/1 | `servidor.py` |
|  | sync | A "cópia em cada PC" só acontece com o Viewer.bat aberto; no fluxo do LEIAME (técnico usa o link do central) ela nunca roda, e nada mostra que falta | partly | 2/2 | `servidor.py` |
| ✔ | sync | Leitura que o central recusa (placa ou fp desconhecido) some do central em silêncio: o ponteiro anda, o CADERNO diz "central em dia" e ela não volta nem depois de atualizar o central | partly | 2/2 | `servidor.py` |
|  | viewer | Malha renomeada com a tecla M que colide com apelido do malhas.json grava a leitura na malha ERRADA | confirmed | 0/1 | `digital_viewer/medicoes.js` |
|  | viewer | 'ESTA PLACA' e 'ref' são por modelo, não por OS: o painel acusa a placa nova com o valor da anterior, e apagar o valor velho cancela o voto da placa anterior | confirmed/partly | 2/2 | `digital_viewer/medicoes.js` |
| ✔ | viewer | CADERNO diz 'central em dia' quando o central RECUSOU a leitura, e a recusa nunca é reenviada | confirmed/partly | 2/2 | `digital_viewer/medicoes.js` |
|  | viewer | Painel e cartão não se atualizam depois do V: o alerta 'ESTA PLACA ⚠' só aparece no próximo clique | partly | 0/1 | `digital_viewer/SCRIPT3.js` |
|  | viewer | Nome do técnico e OS sem normalização: a mesma pessoa na mesma placa vira 2 votos e 2 OS | partly | 0/1 | `digital_viewer/medicoes.js` |
|  | viewer | Alerta 'ESTA PLACA fora' compara leitura de outra condição (fonte x bateria, boot) | partly | 0/2 | `digital_viewer/medicoes.js` |
|  | viewer | Trocar entre 127.0.0.1 e o link do central traz OS, condição e nome velhos daquela origem; leitura vai para a OS errada e substitui o voto dela | partly | 1/2 | `digital_viewer/medicoes.js` |

## Baixo

| | Área | Achado | Conferido | Antes | Arquivo |
|---|---|---|---|---|---|
|  | carga | Disco cresce sem limite: 30 backups completos no servidor, 14 por PC e espelho JSONL sem rotação | nao verificado |  | `medicoes_db.py` |
|  | carga | GET /api/leituras corta em 5000 sem avisar | nao verificado |  | `medicoes_db.py` |
|  | dados | A leitura de 'boot' e o consenso da outra alimentação nunca aparecem para o técnico | nao verificado |  | `consenso.py` |
|  | dados | CSV usa ';' para o Excel pt-BR mas escreve número com ponto: '1.123' vira 1123 | nao verificado |  | `medicoes_db.py` |
|  | dados | recebido_em é gravado sem fuso (hora local do servidor) e criado_em em UTC: o JSONL do dia e o Grafana ficam deslocados | nao verificado |  | `medicoes_db.py` |
|  | dados | Agrupamento encadeado: valores que avançam aos poucos viram um grupo só, 'validado' com faixa larga e valor que nenhuma placa mostrou | partly | 0/1 | `consenso.py` |
|  | dados | Trocar o .bvr (fp novo) apaga da tela todo o consenso da placa, e o central recusa o fp antigo | partly | 0/1 | `consenso.py` |
|  | dados | OS e 'boot' ficam gravados de uma placa para a outra: a placa nova substitui os votos da anterior ou deixa de votar | partly | 0/1 | `digital_viewer/medicoes.js` |
|  | dados | O Grafana não vai conseguir ler o banco em /var/lib/boardview (pasta 750 + WAL), e liberar escrita para ele derruba as gravações | partly | 0/1 | `servidor-central/instalar.sh` |
|  | deploy | O pacote não tem entradas de diretório: o modo das pastas fica dependendo do umask de quem extrai | confirmed | 0/1 | `empacotar_central.py` |
|  | deploy | A linha de comando do medicoes_db no servidor, sem BOARDVIEW_DADOS, trabalha num banco vazio novo em /opt/boardview/dados | confirmed | 0/1 | `medicoes_db.py` |
|  | deploy | useradd sem --user-group: o grupo boardview depende da configuração da distro | confirmed | 0/1 | `servidor-central/instalar.sh` |
|  | deploy | 421 do BOARDVIEW_HOSTS e erro de certificado aparecem na bancada só como "central fora do ar" | partly | 0/1 | `servidor-central/LEIAME.md` |
|  | deploy | Atualizar com o serviço no ar: a leitura que chega enquanto o tar recria o .bvr é recusada para sempre | partly | 0/1 | `servidor-central/LEIAME.md` |
|  | deploy | `tailscale serve --bg 8777` substitui sem aviso o que já estiver publicado na 443 (ex.: Grafana) | partly | 0/1 | `servidor-central/LEIAME.md` |
|  | deploy | Falha de backup passa calada (no servidor e na cópia dos PCs) | partly | 0/1 | `servidor-central/boardview-backup.service` |
|  | rotas | Falha da cópia do banco central no PC não aparece no painel e repete o download inteiro a cada 30 s | confirmed | 0/1 | `digital_viewer/medicoes.js` |
|  | rotas | HEAD nas rotas /api manda o corpo inteiro e executa a rota (HEAD /api/backup copia o banco todo) | confirmed | 0/1 | `servidor.py` |
|  | rotas | Redirecionamento de /digital_viewer/ descarta a query (?board=) | confirmed | 0/1 | `servidor.py` |
|  | rotas | POST /ajuste aceito no central confirma 'salvo', mas a próxima atualização sobrescreve o arquivo sem cópia | partly | 0/1 | `servidor.py` |
|  | rotas | Respostas 4xx/5xx não vão para o journal; 503 'banco ocupado' esconde erro permanente; o teste do instalar.sh não abre o banco | partly | 0/1 | `servidor.py` |
|  | rotas | central.txt com endereço fora do formato desliga a sincronização em silêncio: /api/sync diz papel 'local' e o consenso local aparece sem aviso | partly | 0/1 | `servidor.py` |
|  | sync | 'python medicoes_db.py reenviar' com o servidor rodando perde o efeito se a thread estiver no meio de um lote | confirmed | 0/1 | `medicoes_db.py` |
|  | sync | Valor com /v/ < 0,0001 é gravado na bancada como '5e-05' e o central recusa ('valor invalido') | confirmed | 0/1 | `medicoes_db.py` |
|  | sync | Atualizar o central com 'tar -xzf' por cima do serviço rodando (passo 5) abre uma janela em que .bvr some ou está pela metade, e os lotes que chegam nessa hora são recusados para sempre | partly | 0/1 | `servidor-central/LEIAME.md` |
|  | sync | Cópia do banco central que falha é baixada inteira de novo a cada ~30 s, sem pausa | partly | 0/1 | `servidor.py` |
|  | sync | Proxy de consenso corta a resposta em 2 MB; numa placa grande e muito medida a bancada passa a mostrar a cópia velha como '(cópia, central fora)' | partly | 0/1 | `servidor.py` |
|  | sync | Servidor cujo central é ele mesmo (central.txt ou BOARDVIEW_CENTRAL com o próprio endereço): um único /api/consenso vira uma cadeia infinita de pedidos, com milhares de threads | partly | 0/1 | `servidor.py` |
|  | sync | central.txt com o link copiado do navegador (/HUB.html), com http:// ou salvo como central.txt.txt desliga a sincronização sem aviso no CADERNO | partly | 0/1 | `servidor.py` |
|  | sync | central.txt salvo em UTF-16 (PowerShell 5.1: echo URL > central.txt) impede o servidor da bancada de subir, e o PC fica sem viewer | partly | 0/1 | `servidor.py` |
|  | sync | Python no Windows só confia nas raízes já baixadas no repositório local: PC sem ISRG Root X1 falha no TLS do *.ts.net e o CADERNO diz só 'central fora do ar' | refuted | 0/1 | `servidor.py` |
|  | viewer | Link CSV da bancada diz 'todas as leituras desta placa', mas só traz as deste PC | confirmed | 0/1 | `digital_viewer/index.html` |
|  | viewer | Ajuste de foto feito pelo link do central é sobrescrito na próxima atualização, embora o viewer diga 'salvo' | partly | 0/1 | `digital_viewer/ajuste_fundo.js` |
|  | viewer | Leituras na fila do link do central ficam presas naquela origem e o 127.0.0.1 mostra 'tudo salvo no disco' | partly | 0/1 | `digital_viewer/medicoes.js` |
| ✔ | viewer | Renomeações de malha (M) e de componente (N) ficam presas em um navegador/origem; a exportação de nomes apaga as outras placas | partly | 0/1 | `digital_viewer/renomear.js` |
