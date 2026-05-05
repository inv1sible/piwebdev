#!/usr/bin/env bash
set -euo pipefail

PIWEBDEV_DIR="/var/opt/piwebdev"
SERVICE_FILE="/etc/systemd/system/pi-bridge.service"
NVM_BIN="/home/user01/.nvm/versions/node/v20.20.2/bin"

echo "[1/3] Installing pi-bridge systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=pi-bridge - Unix socket RPC bridge for pi agent
After=network.target

[Service]
Type=simple
User=user01
WorkingDirectory=${PIWEBDEV_DIR}
ExecStart=/usr/bin/python3 ${PIWEBDEV_DIR}/pi-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=/home/user01
Environment=PATH=${NVM_BIN}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PI_BIN=${NVM_BIN}/pi
Environment=PI_BRIDGE_SOCKET=${PIWEBDEV_DIR}/pi-bridge.sock

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pi-bridge
systemctl restart pi-bridge

sleep 2
if systemctl is-active --quiet pi-bridge; then
    echo "✓ pi-bridge running — socket at ${PIWEBDEV_DIR}/pi-bridge.sock"
else
    echo "pi-bridge failed to start. Check: journalctl -u pi-bridge -n 30"
    exit 1
fi

echo "[2/3] Building and starting Docker web container..."
cd "$PIWEBDEV_DIR"
sudo -u user01 docker compose up -d --build web

sleep 5
if docker inspect piwebdev-web --format '{{.State.Status}}' 2>/dev/null | grep -q "running"; then
    echo "✓ piwebdev-web container is running"
else
    echo "Web container may still be starting. Check: docker compose logs web"
fi

echo "[3/3] Done."
echo ""
echo "  App:      http://localhost:3142"
echo "  Logs:     docker compose -f ${PIWEBDEV_DIR}/docker-compose.yml logs -f web"
echo "  Bridge:   journalctl -u pi-bridge -f"
