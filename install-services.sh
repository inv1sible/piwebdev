#!/usr/bin/env bash
set -euo pipefail

PIWEBDEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[install-services]${NC} $*"; }
warn()  { echo -e "${YELLOW}[install-services]${NC} $*"; }
error() { echo -e "${RED}[install-services]${NC} $*" >&2; exit 1; }

if [ "${EUID}" -ne 0 ]; then
  echo -e "${YELLOW}This script installs systemd services and requires root. Re-running with sudo...${NC}"
  exec sudo -E bash "$0" "$@"
fi

SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(logname 2>/dev/null || echo root)}}"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  error "SERVICE_USER '$SERVICE_USER' does not exist. Re-run with SERVICE_USER=<user>."
fi

SERVICE_HOME="${SERVICE_HOME:-$(getent passwd "$SERVICE_USER" | cut -d: -f6)}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
[ -n "$PYTHON_BIN" ] || error "python3 not found. Install Python 3 first."

PI_BIN="${PI_BIN:-}"
if [ -z "$PI_BIN" ]; then
  PI_BIN="$(sudo -H -u "$SERVICE_USER" bash -lc 'command -v pi 2>/dev/null || true')"
fi
if [ -z "$PI_BIN" ]; then
  warn "Could not find 'pi' for $SERVICE_USER. pi-bridge will be installed with PI_BIN=pi; install/configure Pi or re-run with PI_BIN=/path/to/pi."
  PI_BIN="pi"
fi

PI_DIR="$(dirname "$PI_BIN" 2>/dev/null || echo /usr/local/bin)"
BASE_PATH="${PATH_PREFIX:-${PI_DIR}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"

PI_SOCKET="${PI_BRIDGE_SOCKET:-${PIWEBDEV_DIR}/pi-bridge.sock}"
TERMINAL_SOCKET="${TERMINAL_BRIDGE_SOCKET:-${PIWEBDEV_DIR}/terminal-bridge.sock}"
EXEC_SOCKET="${EXEC_BRIDGE_SOCKET:-${PIWEBDEV_DIR}/exec-bridge.sock}"
TERMINAL_SHELL="${TERMINAL_SHELL:-/bin/bash}"

install_unit() {
  local name="$1"
  local content="$2"
  local path="/etc/systemd/system/${name}.service"
  info "Writing ${path}"
  printf '%s\n' "$content" > "$path"
}

install_unit "pi-bridge" "[Unit]
Description=pi-bridge - Unix socket RPC bridge for pi agent
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PIWEBDEV_DIR}
ExecStart=${PYTHON_BIN} ${PIWEBDEV_DIR}/pi-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=${SERVICE_HOME}
Environment=PATH=${BASE_PATH}
Environment=PI_BIN=${PI_BIN}
Environment=PI_BRIDGE_SOCKET=${PI_SOCKET}

[Install]
WantedBy=multi-user.target"

install_unit "terminal-bridge" "[Unit]
Description=terminal-bridge - PTY bridge for piwebdev
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PIWEBDEV_DIR}
ExecStart=${PYTHON_BIN} ${PIWEBDEV_DIR}/terminal-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=${SERVICE_HOME}
Environment=TERMINAL_BRIDGE_SOCKET=${TERMINAL_SOCKET}
Environment=TERMINAL_SHELL=${TERMINAL_SHELL}

[Install]
WantedBy=multi-user.target"

install_unit "exec-bridge" "[Unit]
Description=Exec Bridge for piwebdev (host-side command runner)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PIWEBDEV_DIR}
ExecStart=${PYTHON_BIN} ${PIWEBDEV_DIR}/exec-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=${SERVICE_HOME}
Environment=EXEC_BRIDGE_SOCKET=${EXEC_SOCKET}

[Install]
WantedBy=multi-user.target"

info "Reloading systemd and enabling bridge services"
systemctl daemon-reload
systemctl enable --now pi-bridge terminal-bridge exec-bridge

info "Service status:"
systemctl --no-pager --full status pi-bridge terminal-bridge exec-bridge || true

info "Done. Socket paths:"
echo "  ${PI_SOCKET}"
echo "  ${TERMINAL_SOCKET}"
echo "  ${EXEC_SOCKET}"
