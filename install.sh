#!/usr/bin/env bash
set -euo pipefail

PIWEBDEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PIWEBDEV_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[install]${NC} $*"; }
error() { echo -e "${RED}[install]${NC} $*" >&2; exit 1; }

# Must run as root (needs apt for Python 3.11 and systemd for the service)
if [ "$EUID" -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}This script requires root. Re-running with sudo...${NC}"
    echo ""
    exec sudo bash "$0" "$@"
fi

# ── 1. Python 3.11+ ───────────────────────────────────────────────────────────
PYTHON=""
for py in python3.12 python3.11 python3.10; do
    if command -v "$py" &>/dev/null; then PYTHON="$py"; break; fi
done

if [ -z "$PYTHON" ]; then
    warn "Python 3.10+ not found. Installing python3.11 from Debian backports..."
    if [ ! -f /etc/apt/sources.list.d/bullseye-backports.list ]; then
        echo "deb http://deb.debian.org/debian bullseye-backports main" \
            > /etc/apt/sources.list.d/bullseye-backports.list
    fi
    apt-get update -qq
    apt-get install -y -t bullseye-backports python3.11 python3.11-venv python3.11-dev
    PYTHON=python3.11
fi

info "Using $PYTHON ($(${PYTHON} --version))"

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "$PIWEBDEV_DIR/venv" ]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$PIWEBDEV_DIR/venv"
fi
VENV_PY="$PIWEBDEV_DIR/venv/bin/python"
VENV_PIP="$PIWEBDEV_DIR/venv/bin/pip"

info "Installing Python dependencies..."
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet -r "$PIWEBDEV_DIR/requirements.txt"

# ── 3. .env file ─────────────────────────────────────────────────────────────
if [ ! -f "$PIWEBDEV_DIR/.env" ]; then
    info "Generating .env with random secrets..."
    SECRET_KEY=$("$VENV_PY" -c "import secrets; print(secrets.token_urlsafe(50))")
    ADMIN_PASS=$("$VENV_PY" -c "import secrets; print(secrets.token_urlsafe(16))")
    cat > "$PIWEBDEV_DIR/.env" <<EOF
SECRET_KEY=${SECRET_KEY}
DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:3142

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=${ADMIN_PASS}

PROJECTS_ROOT=/var/opt
DEFAULT_PI_PROVIDER=openai-codex
DEFAULT_PI_MODEL=gpt-5.5
DEFAULT_PI_THINKING=minimal
EOF
    echo ""
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    warn " Admin password: ${ADMIN_PASS}"
    warn " (also stored in .env — edit it to change)"
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
else
    info ".env already exists — skipping secret generation."
fi

# ── 4. Data directory ─────────────────────────────────────────────────────────
mkdir -p "$PIWEBDEV_DIR/data/media"

# ── 5. Django setup ───────────────────────────────────────────────────────────
APP_DIR="$PIWEBDEV_DIR/app"
MANAGE="$VENV_PY $APP_DIR/manage.py"

info "Running database migrations..."
$MANAGE migrate --run-syncdb

info "Collecting static files..."
$MANAGE collectstatic --noinput --clear -v 0

info "Creating/updating superuser..."
$MANAGE bootstrap_superuser

# ── 6. Systemd service ────────────────────────────────────────────────────────
SERVICE_NAME=piwebdev
SERVICE_FILE=/etc/systemd/system/${SERVICE_NAME}.service
DAPHNE="$PIWEBDEV_DIR/venv/bin/daphne"
CURRENT_USER=$(id -un)

info "Installing systemd service (${SERVICE_FILE})..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=pi WebDev
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${DAPHNE} -b 0.0.0.0 -p 3142 piwebdev.asgi:application
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "✓ piwebdev is running at http://localhost:3142"
else
    error "Service failed to start. Check: journalctl -u ${SERVICE_NAME} -n 30"
fi
