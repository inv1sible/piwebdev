# General Memory

- Project root `/var/opt/piwebdev` is a Django/Channels web UI for the `pi` coding agent, intended to run from Docker at `http://SERVER:3142` behind Nginx Proxy Manager if desired.
- Project root `/var/opt/piwebdev` was not a Git repository initially; initialized Git before the baseline commit.
- Added `.gitignore` to keep secrets/runtime artifacts out of version control: `.env`, virtualenvs, `data/`, collected `app/staticfiles/`, sockets, Pi session data, and local Claude settings.
- Runtime stack: Django + Daphne/Channels, PostgreSQL, Redis, WhiteNoise static files, Docker Compose, plus host-side Unix socket bridges (`pi-bridge.py`, `terminal-bridge.py`, and `exec-bridge.py`).
- Main Django app is `app/core`; project settings live in `app/piwebdev/settings.py`. URL routes are in `app/piwebdev/urls.py`; websocket routes are in `app/core/routing.py`.
- Projects are discovered from and created under `settings.PROJECTS_ROOT` (default `/var/opt`). The container bind-mounts `/var/opt:/var/opt` so paths match host paths and the Pi CLI.
- The web container relies on Unix sockets at `/var/opt/piwebdev/pi-bridge.sock`, `/var/opt/piwebdev/terminal-bridge.sock`, and `/var/opt/piwebdev/exec-bridge.sock` to run host-side `pi` RPC sessions, PTY terminal sessions, and direct host command execution.
- `PiConsumer` always injects the project root `MEMORY.md` into prompts, regardless of the `ProjectPiSettings.inject_memory` field; if changing this behavior, update both code and UX wording.
- Project memory is stored in the filesystem at `<project>/MEMORY.md` by the memory view/API, not primarily in the `ProjectMemory` database model.
- Path safety helpers in `app/core/utils.py` prevent project file operations and zip extraction from escaping the project root/workspace.
- File tree intentionally hides `.git`, `.pi-sessions`, `node_modules`, and `__pycache__`.
- Git operations are simple API wrappers around `git -c safe.directory=*`: init, status/diff, add/commit, and push.
- Terminal access is gated per user via `UserPiSettings.terminal_access`, set in Django admin; terminal sessions remember last size and can persist/resume briefly through `terminal-bridge.py`.
- PWA support is implemented directly in Django views (`manifest`, `offline`, `service_worker`) with cached core assets.
- Login uses `PiLoginView` with username-or-email auth and POST rate limiting. Project creation is also rate limited.
- Admin currently registers Project, ProjectMemory, UserPiSettings, ProjectPiSettings, PiSession, and ChatMessage; TerminalSession exists but is not registered in admin.
- Chat working/Stop UX gotcha: frontend task groups must be finalised not only on raw `agent_end` events but also on explicit `status: idle` or websocket close; `pi-bridge.py` treats web UI `{"type":"abort"}` frames as a hard termination of the persistent pi process/session because blindly forwarding abort to pi stdin was not reliable.
- Documentation treats Docker Compose as the recommended install path. `install.sh` is now a Docker-oriented bootstrapper: installs apt prerequisites, Docker/Compose as needed, Node/npm, the Pi npm package (`@mariozechner/pi-coding-agent` by default), creates `.env` if missing, runs `docker compose up -d --build`, and optionally calls `install-services.sh`.
- `install-services.sh` automates host-side systemd setup for `pi-bridge`, `terminal-bridge`, and `exec-bridge`; key overrides include `SERVICE_USER`, `PI_BIN`, `PYTHON_BIN`, `TERMINAL_SHELL`, and bridge socket environment variables. The old host virtualenv/Daphne `install.sh` flow was removed.
- Removed obsolete `finish-install.sh`; it was a legacy one-off installer for only `pi-bridge` plus rebuilding the `web` container, hard-coded to `/var/opt/piwebdev`, `user01`, and a specific NVM Node path. Current installs use `install.sh` and `install-services.sh`.
- GitHub-facing docs were expanded in `README.md` (features, architecture, security, quick start) and `INSTALL.md` (prereqs, Compose setup, bridge services, verification, reverse proxy, updating, troubleshooting).

# Todos

- Consider removing or wiring up the unused `ProjectPiSettings.inject_memory` flag so UI matches behavior.
- Consider registering `TerminalSession` in Django admin if operators need visibility into terminal sessions.
- Avoid committing generated files such as `__pycache__` or collected `app/staticfiles/` if they are currently tracked.
- Review `docker-compose.yml`: it contains a hard-coded Postgres password and grants the web container access to host `/var/opt` and Docker-related deployment power; keep deployment access tightly controlled.

# Ideas For Later

- Add richer session management (multiple named Pi sessions per project, archive/restore UI).
- Add stronger file editor features (syntax highlighting, binary file handling, safer large-file limits).
- Add model/provider discovery or admin-configurable choices instead of hard-coded form choices.
- Add tests around path traversal, zip extraction safety, websocket auth, and git API error cases.
