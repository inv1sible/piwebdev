# Installation

This guide describes the recommended Docker Compose installation for piwebdev and the host-side bridge services required for Pi chat, terminal sessions, and host command execution.

## Prerequisites

Recommended baseline:

- Linux host with systemd.
- Docker Engine and the Docker Compose plugin (`docker compose`).
- Git.
- Python 3.10+ on the host for bridge scripts.
- Node.js/npm for the system user that will run Pi.
- The `pi` CLI installed and authenticated/configured for that same user.
- A trusted network, VPN, or HTTPS reverse proxy with normal Django login protection. piwebdev is not intended for untrusted public multi-tenant use.

The examples below assume:

- Repository path: `/var/opt/piwebdev`
- Service user: `user01`
- Projects root: `/var/opt`
- Pi binary: `/home/user01/.nvm/versions/node/v20.20.2/bin/pi`

Adjust paths, users, and binary locations for your server.

## 1. Clone the repository

```bash
cd /var/opt
git clone <YOUR_GITHUB_REPO_URL> piwebdev
cd /var/opt/piwebdev
```

## 2. Configure `.env`

```bash
cp .env.sample .env
```

Edit `.env` before first start:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=0
ALLOWED_HOSTS=your.server.name,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://your.server.name:3142

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=replace-with-a-long-random-password

PROJECTS_ROOT=/var/opt
DEFAULT_PI_PROVIDER=openai-codex
DEFAULT_PI_MODEL=gpt-5.5
DEFAULT_PI_THINKING=minimal
```

For HTTPS behind a reverse proxy, use the public HTTPS origin and secure cookies:

```env
CSRF_TRUSTED_ORIGINS=https://pi.example.com
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
```

The web container bootstraps/updates the admin user from `DJANGO_SUPERUSER_*` on startup.

## 3. Review Docker Compose security

Before publishing or deploying, review `docker-compose.yml`:

- It bind-mounts host `/var/opt` into the web container. This is intentional so project paths match between Django, the host bridge scripts, Git, and the Pi CLI, but it grants the app access to that tree.
- It contains a hard-coded PostgreSQL password. Change both `postgres.environment.POSTGRES_PASSWORD` and `web.environment.DATABASE_URL` for any shared deployment.
- By default `web` binds `127.0.0.1:3142:3142`; the optional `nginx` service binds `0.0.0.0:3143:3143`.

## 4. Automated install

For a typical fresh host, run:

```bash
./install.sh
```

This installs apt prerequisites, Docker/Compose if needed, Node/npm, the Pi npm package (`@mariozechner/pi-coding-agent` by default), creates `.env` if missing, starts Docker Compose, and installs the host bridge services.

Useful overrides:

```bash
SERVICE_USER=user01 PI_NPM_PACKAGE=@mariozechner/pi-coding-agent ./install.sh
INSTALL_SERVICES=0 ./install.sh   # skip systemd bridge setup
```

If you prefer manual control, run Docker directly:

```bash
docker compose up -d --build
```

Check status and logs:

```bash
docker compose ps
docker compose logs -f web
```

On startup, the web container runs migrations, collects static files, configures Git safe directories inside the container, and bootstraps the admin user.

If you want direct LAN access to port `3142`, change the `web.ports` binding from `127.0.0.1:3142:3142` to `0.0.0.0:3142:3142`. For shared review, HTTPS through a reverse proxy is preferred.

## 5. Install host-side bridge services

The bridges run on the host, not inside Docker, and expose Unix sockets under `/var/opt/piwebdev`. The web container reaches those sockets through the `/var/opt:/var/opt` bind mount.

The automated service installer writes and enables all three units:

```bash
sudo SERVICE_USER=user01 ./install-services.sh
```

Useful overrides include `PI_BIN=/path/to/pi`, `PYTHON_BIN=/usr/bin/python3`, `TERMINAL_SHELL=/bin/bash`, and the `*_SOCKET` variables. The generated units match the examples below.

### Pi bridge

Required for Pi chat sessions.

Example `/etc/systemd/system/pi-bridge.service`:

```ini
[Unit]
Description=pi-bridge - Unix socket RPC bridge for pi agent
After=network.target

[Service]
Type=simple
User=user01
WorkingDirectory=/var/opt/piwebdev
ExecStart=/usr/bin/python3 /var/opt/piwebdev/pi-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=/home/user01
Environment=PATH=/home/user01/.nvm/versions/node/v20.20.2/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PI_BIN=/home/user01/.nvm/versions/node/v20.20.2/bin/pi
Environment=PI_BRIDGE_SOCKET=/var/opt/piwebdev/pi-bridge.sock

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pi-bridge
sudo systemctl status pi-bridge
```

Sanity-check the Pi binary as the service user:

```bash
sudo -u user01 /home/user01/.nvm/versions/node/v20.20.2/bin/pi --version
```

### Terminal bridge

Required only for browser terminal sessions. Terminal access is also gated per user in Django admin via `UserPiSettings.terminal_access`.

Create `/etc/systemd/system/terminal-bridge.service`:

```ini
[Unit]
Description=terminal-bridge - PTY bridge for piwebdev
After=network.target

[Service]
Type=simple
User=user01
WorkingDirectory=/var/opt/piwebdev
ExecStart=/usr/bin/python3 /var/opt/piwebdev/terminal-bridge.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=HOME=/home/user01
Environment=TERMINAL_BRIDGE_SOCKET=/var/opt/piwebdev/terminal-bridge.sock
Environment=TERMINAL_SHELL=/bin/bash

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now terminal-bridge
sudo systemctl status terminal-bridge
```

### Exec bridge

`exec-bridge.py` provides direct host command execution for integrations that need it. `install-services.sh` generates this unit with the selected `SERVICE_USER`, paths, and socket location. Review permissions before enabling host command execution on shared systems.

## 6. Verify the installation

Open the app:

```text
http://SERVER:3142
```

Then verify:

1. Log in with the bootstrap admin credentials from `.env`.
2. Open Django admin and configure user/Pi settings as needed.
3. Create or open a project under `/var/opt`.
4. Start a Pi chat and confirm `pi-bridge` logs show activity.
5. If terminal access is enabled, open a terminal and confirm `terminal-bridge` logs show activity.

Useful checks:

```bash
ls -l /var/opt/piwebdev/*.sock
journalctl -u pi-bridge -n 50 --no-pager
journalctl -u terminal-bridge -n 50 --no-pager
journalctl -u exec-bridge -n 50 --no-pager
docker compose logs -n 100 web
```

## Reverse proxy notes

For Nginx Proxy Manager or another reverse proxy:

- Forward to the host/port where the app is exposed (`3142` by default, or your chosen binding).
- Enable WebSocket support.
- Use HTTPS for shared deployments.
- Match `.env` to the public hostname:

```env
ALLOWED_HOSTS=pi.example.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://pi.example.com
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
```

Restart after `.env` changes:

```bash
docker compose up -d
```

## Updating

```bash
cd /var/opt/piwebdev
git pull
docker compose up -d --build
sudo systemctl restart pi-bridge terminal-bridge exec-bridge
```

## Installer script reference

`install.sh` is now the recommended bootstrap entry point for Docker Compose installs. It is intentionally not a host virtualenv/Daphne installer.

`install-services.sh` can be re-run independently after changing bridge scripts, moving the repo, changing users, or changing the Pi binary path:

```bash
sudo SERVICE_USER=user01 PI_BIN=/home/user01/.nvm/versions/node/v20.20.2/bin/pi ./install-services.sh
sudo systemctl restart pi-bridge terminal-bridge exec-bridge
```

## Troubleshooting

### Chat does not start

Check that `pi-bridge` is running and that `PI_BIN` points to a working Pi executable for the service user:

```bash
sudo -u user01 /home/user01/.nvm/versions/node/v20.20.2/bin/pi --version
journalctl -u pi-bridge -f
```

### Terminal does not open

Confirm terminal access is enabled for the user in Django admin and that `terminal-bridge` is running:

```bash
journalctl -u terminal-bridge -f
```

### Login or CSRF errors behind HTTPS

Verify `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and cookie secure settings in `.env`, then restart the web container.

### Permission issues on projects

The bridge services run as their configured systemd `User`. Ensure that user can read/write the projects under `PROJECTS_ROOT`, and remember the web container also sees `/var/opt` through the bind mount.
