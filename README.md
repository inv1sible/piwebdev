# π webui

Django rewrite of the Pi Web UI.

## Run

```bash
cp .env.sample .env
# edit secrets, hosts and CSRF origins
docker compose up -d --build
```

Open:

```text
http://SERVER:3142
```

The initial admin user is created from:

```env
DJANGO_SUPERUSER_USERNAME
DJANGO_SUPERUSER_EMAIL
DJANGO_SUPERUSER_PASSWORD
```

## Storage

This project uses bind mounts under `./data`:

- `./data/postgres`
- `./data/redis`
- `./data/media`
- `./data/pi-sessions`
- `./data/uploads`

Projects are mounted from host `/var/opt` into the container as `/var/opt`, so paths match the host and the CLI.

The Docker socket is mounted into the web container so `pi.dev` can run `docker` / `docker compose` for project deployments. This is powerful and security-sensitive: access to π webui effectively means access to the host Docker daemon.

## Nginx Proxy Manager

Forward to port `3142`, enable WebSocket support, and use HTTPS.

Set `.env` appropriately:

```env
ALLOWED_HOSTS=your.domain,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://your.domain
```
