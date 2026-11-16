# Servidor central — instalar, ligar as bancadas, backup

O central é o servidor da empresa (o mesmo do Grafana, Linux). Ele guarda as leituras dos
três técnicos e calcula o consenso ("validado por N"). Os técnicos abrem o viewer **pelo
link do central**; se o central estiver fora, cada PC continua funcionando sozinho pelo
`Viewer.bat` e manda as leituras quando ele voltar.

```
PC da bancada                                   servidor da empresa
navegador ── link https://<maquina>.ts.net ──►  tailscale serve ─► servidor.py :8777
   └─ Viewer.bat (127.0.0.1:8777, offline) ──►      (sync a cada 30 s)  /var/lib/boardview
```

## 1. Tailscale (uma vez)

1. Instalar o Tailscale no servidor e nos 3 PCs, todos entrando com a **mesma conta**.
2. No painel do Tailscale (admin console → DNS): ligar **MagicDNS** e **HTTPS Certificates**.
3. No servidor, `tailscale status` mostra o nome da máquina. O endereço do central fica
   `https://<maquina>.<tailnet>.ts.net` (o `<tailnet>` aparece no painel, em DNS).

Nunca usar `tailscale funnel`: ele abre para a internet, e o acesso é sem login.

## 2. Montar o pacote (no PC, Windows)

```
python empacotar_central.py
```

Gera `Documents\boardview-central-AAAA-MM-DD.tar.gz` (~40 MB: viewer, HUB, caderno).
`--pdfs` inclui os PDFs (~0,9 GB); `--drones` gera também o pacote da pasta Drones.
O banco deste PC (`dados/`) e o `central.txt` ficam de fora de propósito.

Copiar para o servidor (pelo Tailscale):

```
scp Documents\boardview-central-AAAA-MM-DD.tar.gz USUARIO@<maquina>:/tmp/
```

## 3. Instalar (no servidor)

```
sudo mkdir -p /opt/boardview
sudo tar -xzf /tmp/boardview-central-AAAA-MM-DD.tar.gz -C /opt/boardview
sudo sh /opt/boardview/servidor-central/instalar.sh
sudo nano /etc/boardview.env          # BOARDVIEW_HOSTS=<maquina>.<tailnet>.ts.net
sudo systemctl restart boardview
sudo tailscale serve --bg 8777
```

O `instalar.sh` confere Python (3.8+) e SQLite, cria o usuário `boardview` (sem login),
instala o serviço e o backup diário, liga tudo e testa. O servidor escuta só em
`127.0.0.1:8777` — quem publica para a tailnet, com HTTPS, é o `tailscale serve`. Não
conflita com o Grafana (porta 3000).

Pacote da pasta Drones (opcional, links do HUB para PDF/.pcb):

```
sudo mkdir -p /opt/boardview-drones
sudo tar -xzf /tmp/boardview-drones-AAAA-MM-DD.tar.gz -C /opt/boardview-drones
```

Testar: num PC da tailnet, abrir `https://<maquina>.<tailnet>.ts.net/`. Erro **421**
("host nao reconhecido") = o `BOARDVIEW_HOSTS` não bate com o nome do link.

## 4. Ligar cada PC de bancada

Na pasta `Boardview` do PC, criar o arquivo **`central.txt`** com uma linha:

```
https://<maquina>.<tailnet>.ts.net
```

Fechar a janela preta do servidor e abrir o `Viewer.bat` de novo. A janela mostra
"Bancada: as leituras tambem vao para o central ...", e o bloco CADERNO do viewer passa a
dizer **"central em dia"** (ou "N indo para o central"). Na primeira vez, as leituras que o
PC já tinha (fase 1) sobem todas sozinhas.

## 5. Atualizar (placas novas, correções)

Repetir os passos 2 e 3 (sem o `nano`/`tailscale serve`). O banco fica em
`/var/lib/boardview` e não é tocado. Os ajustes de foto vêm do PC e substituem os do
servidor — faça os ajustes de foto no PC.

## 6. Backup

- **No servidor:** todo dia às 03:00, `/var/backups/boardview/medicoes-AAAA-MM-DD-HHMM.sqlite3`
  (30 mais novos). Cada cópia é aberta e tem o consenso recalculado antes de ser guardada
  (restauração de teste). Ver: `systemctl list-timers boardview-backup.timer` e
  `sudo ls -l /var/backups/boardview`.
- **Em cada PC:** a bancada baixa uma cópia do banco central (refeita a cada 6 h) em
  `dados\copia-central\` (14 dias), também conferida antes de guardar.
- Conferir uma cópia à mão: `python3 medicoes_db.py conferir ARQUIVO`.

Restaurar o central a partir de um backup:

```
sudo systemctl stop boardview
sudo sh -c 'cd /var/lib/boardview && mkdir -p antes-restaurar && mv medicoes.sqlite3* antes-restaurar/'
sudo cp /var/backups/boardview/medicoes-AAAA-MM-DD-HHMM.sqlite3 /var/lib/boardview/medicoes.sqlite3
sudo chown boardview:boardview /var/lib/boardview/medicoes.sqlite3
sudo systemctl start boardview
```

(O `mv` leva junto os arquivos `-wal`/`-shm` do banco antigo: não podem ficar ao lado do
restaurado.)

Depois, em cada PC de bancada, para devolver ao central o que foi medido depois do
backup (não duplica nada): `python medicoes_db.py reenviar`, com o `Viewer.bat` aberto.

## 7. Quando algo não funciona

| Sintoma | Causa provável |
|---|---|
| 421 "host nao reconhecido" | `BOARDVIEW_HOSTS` em `/etc/boardview.env` diferente do nome do link |
| CADERNO: "esperando o central (fora do ar)" | central desligado, Tailscale do PC desligado, ou `central.txt` errado |
| Leitura recusada no central ("placa desconhecida", "fp desconhecido") | o `.bvr` do central é diferente do PC: atualizar o central (passo 5) |
| Ver o que o servidor está fazendo | `journalctl -u boardview -f` |
| Situação da sincronização de um PC | abrir `http://127.0.0.1:8777/api/sync` no PC |
