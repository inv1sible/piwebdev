#!/usr/bin/env bash
set -euo pipefail

PIWEBDEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PIWEBDEV_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[install]${NC} $*"; }
error() { echo -e "${RED}[install]${NC} $*" >&2; exit 1; }

if [ "${EUID}" -ne 0 ]; then
  echo -e "${YELLOW}This script installs packages/services and requires root. Re-running with sudo...${NC}"
  exec sudo -E bash "$0" "$@"
fi

SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(logname 2>/dev/null || echo root)}}"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  error "SERVICE_USER '$SERVICE_USER' does not exist. Re-run with SERVICE_USER=<user>."
fi

PI_NPM_PACKAGE="${PI_NPM_PACKAGE:-@mariozechner/pi-coding-agent}"
INSTALL_SERVICES="${INSTALL_SERVICES:-1}"

apt_install() {
  DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

info "Updating apt package indexes"
apt-get update

info "Installing base packages"
apt_install ca-certificates curl git python3 python3-venv python3-pip

if ! command -v docker >/dev/null 2>&1; then
  info "Installing Docker from distro packages"
  apt_install docker.io
else
  info "Docker already installed: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  info "Installing Docker Compose plugin/package"
  apt_install docker-compose-plugin || apt_install docker-compose
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
  info "Docker Compose available: $(docker compose version)"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
  info "Docker Compose available: $(docker-compose --version)"
else
  error "Docker Compose is not available after installation attempt."
fi

systemctl enable --now docker >/dev/null 2>&1 || warn "Could not enable/start docker via systemd; continuing."

# Ensure nvm + Node >=20 are available for SERVICE_USER, then install Pi CLI via nvm npm.
ensure_node20() {
  if ! sudo -H -u "$SERVICE_USER" bash -lc 'test -s "$HOME/.nvm/nvm.sh"'; then
    info "Installing nvm for ${SERVICE_USER}"
    sudo -H -u "$SERVICE_USER" bash -lc \
      'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | PROFILE=/dev/null bash'
  else
    info "nvm already present for ${SERVICE_USER}"
  fi

  NODE_MAJOR=$(sudo -H -u "$SERVICE_USER" bash -lc \
    'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; node --version 2>/dev/null | sed "s/v//" | cut -d. -f1' \
    2>/dev/null || echo 0)

  if [ "${NODE_MAJOR:-0}" -lt 20 ]; then
    info "Node ${NODE_MAJOR} detected — upgrading to Node 20 via nvm (Node 18 is not supported)"
    sudo -H -u "$SERVICE_USER" bash -lc \
      'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm install 20; nvm alias default 20'
  else
    info "Node ${NODE_MAJOR} is sufficient (>=20)"
  fi
}
ensure_node20

if ! sudo -H -u "$SERVICE_USER" bash -lc 'source ~/.nvm/nvm.sh 2>/dev/null; command -v pi >/dev/null 2>&1'; then
  info "Installing Pi CLI npm package (${PI_NPM_PACKAGE}) globally via nvm npm"
  sudo -H -u "$SERVICE_USER" bash -lc \
    "source ~/.nvm/nvm.sh 2>/dev/null; npm install -g '${PI_NPM_PACKAGE}'"
else
  info "Pi CLI already installed for ${SERVICE_USER}: $(sudo -H -u "$SERVICE_USER" bash -lc 'source ~/.nvm/nvm.sh 2>/dev/null; command -v pi')"
fi

if [ ! -f .env ]; then
  info "Creating .env from .env.sample with generated secrets"
  cp .env.sample .env
  SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(50))
PY
)"
  ADMIN_PASS="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(16))
PY
)"
  python3 - <<PY
from pathlib import Path
p = Path('.env')
s = p.read_text()
s = s.replace('SECRET_KEY=change-this-long-random-django-secret', 'SECRET_KEY=${SECRET_KEY}')
s = s.replace('DJANGO_SUPERUSER_PASSWORD=change-this-long-random-admin-password', 'DJANGO_SUPERUSER_PASSWORD=${ADMIN_PASS}')
p.write_text(s)
PY
  warn "Generated Django admin password: ${ADMIN_PASS} (stored in .env)"
else
  info ".env already exists; leaving it unchanged"
fi

info "Building and starting Docker Compose stack"
"${COMPOSE_CMD[@]}" up -d --build

if [ "$INSTALL_SERVICES" = "1" ]; then
  info "Installing host bridge services"
  SERVICE_USER="$SERVICE_USER" "$PIWEBDEV_DIR/install-services.sh"
else
  warn "Skipping bridge services because INSTALL_SERVICES=${INSTALL_SERVICES}"
fi

info "Done. App should be available at http://localhost:3142 (or your reverse proxy)."
