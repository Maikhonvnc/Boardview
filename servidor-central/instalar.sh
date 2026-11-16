#!/bin/sh
# Instala ou atualiza o Boardview central neste servidor Linux (fase 2).
# Rodar como root DEPOIS de extrair o pacote em /opt/boardview:
#   sudo sh /opt/boardview/servidor-central/instalar.sh
# Pode rodar de novo a cada atualizacao: nao mexe no banco nem no /etc/boardview.env.
set -eu
DEST=/opt/boardview

[ "$(id -u)" = 0 ] || { echo "rode com sudo"; exit 1; }
[ -f "$DEST/servidor.py" ] || { echo "nao achei $DEST/servidor.py — extraia o pacote em $DEST primeiro"; exit 1; }
if [ -f "$DEST/central.txt" ]; then
    echo "ERRO: $DEST/central.txt existe. Ele e so de PC de bancada: no servidor faria o"
    echo "central mandar as leituras para outro. Apague esse arquivo e rode de novo."
    exit 1
fi

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "falta o python3 (ex.: apt install python3)"; exit 1; }
"$PY" - <<'EOF'
import sys, sqlite3
assert sys.version_info >= (3, 8), 'precisa de Python 3.8+, tem ' + sys.version.split()[0]
assert sqlite3.sqlite_version_info >= (3, 24), 'precisa de SQLite 3.24+, tem ' + sqlite3.sqlite_version
print('python', sys.version.split()[0], '/ sqlite', sqlite3.sqlite_version, ': ok')
EOF
if [ "$PY" != /usr/bin/python3 ]; then
    echo "AVISO: python3 esta em $PY; os .service usam /usr/bin/python3 — ajuste o ExecStart se preciso."
fi

# usuario sem login, so para rodar o servico
NOLOGIN=$(command -v nologin || echo /bin/false)
id boardview >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /var/lib/boardview --shell "$NOLOGIN" boardview

mkdir -p /var/lib/boardview /var/backups/boardview "$DEST/digital_viewer/build/ajustes"
chown boardview:boardview /var/lib/boardview /var/backups/boardview
chown -R boardview:boardview "$DEST/digital_viewer/build/ajustes"
chmod 750 /var/lib/boardview /var/backups/boardview

NOVO_ENV=0
if [ ! -f /etc/boardview.env ]; then
    cp "$DEST/servidor-central/boardview.env.exemplo" /etc/boardview.env
    NOVO_ENV=1
fi

install -m 644 "$DEST/servidor-central/boardview.service" \
               "$DEST/servidor-central/boardview-backup.service" \
               "$DEST/servidor-central/boardview-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable boardview.service boardview-backup.timer >/dev/null
systemctl restart boardview.service
systemctl start boardview-backup.timer
sleep 2

if "$PY" -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8777/api/sync', timeout=5).read().decode())"; then
    echo ">> servidor no ar em 127.0.0.1:8777"
else
    systemctl --no-pager status boardview.service | head -20
    echo ">> o servidor NAO respondeu; veja: journalctl -u boardview -n 50"
    exit 1
fi

if [ "$NOVO_ENV" = 1 ]; then
    echo
    echo ">> FALTA: ponha o nome deste servidor na tailnet em /etc/boardview.env"
    echo "   (BOARDVIEW_HOSTS=<maquina>.<tailnet>.ts.net) e rode: systemctl restart boardview"
fi
echo ">> publicar na tailnet (uma vez): tailscale serve --bg 8777    (NUNCA 'tailscale funnel')"
