# Soundlist

Management panel for Twitch soundboard channels. Streams JSON at
`/lists/<slug>.json` in the exact legacy shape; the public board
(`app.js`) points at the same origin and works unchanged.

Built with Python 3.11, FastAPI 0.115, SQLModel + SQLite, Twitch OAuth.

## Quick start

```bash
# 1. install dependencies
uv sync

# 2. copy and fill in env vars
cp .env.example .env
$EDITOR .env

# 3. run (auto-reloads in dev)
uv run soundlist

# 4. (optional) import legacy lists/*.json into the DB
uv run python scripts/import_json.py
```

App runs at http://localhost:8000.  
API docs (dev only): http://localhost:8000/api/docs

## Required environment variables

| Variable | Description |
|---|---|
| `TWITCH_CLIENT_ID` | Client ID from dev.twitch.tv/console/apps |
| `TWITCH_CLIENT_SECRET` | Client secret from same page |
| `TWITCH_REDIRECT_URI` | Must match Twitch app config; default `http://localhost:8000/auth/callback` |
| `SESSION_SECRET_KEY` | Random hex string; generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_LOGINS` | Comma-separated Twitch login names to seed as admins on startup |

## Optional variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./soundlist.db` | SQLite file path |
| `APP_ENV` | `development` | Set to `production` for stricter cookie flags and no API docs |
| `CSRF_ENABLED` | `true` | Set `false` to bypass CSRF (dev only) |

## Running tests

```bash
uv run pytest
uv run ruff check app/
uv run pylint app/
```

## Importing legacy JSON

```bash
# Start the app once to create the DB schema, then:
uv run python scripts/import_json.py
```

Reads all `lists/*.json` files plus `lists/internals/avatars.json`.
Idempotent - safe to run multiple times.

## Deploy (uvicorn behind Nginx)

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Systemd unit (minimal):

```ini
[Unit]
Description=Soundlist
After=network.target

[Service]
WorkingDirectory=/opt/soundlist
EnvironmentFile=/opt/soundlist/.env
ExecStart=/opt/soundlist/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Production checklist:
- `APP_ENV=production`
- `SESSION_SECRET_KEY` set to a secure random value
- `CSRF_ENABLED=true` (default)
- SQLite file on a persistent volume
- Nginx or Caddy handles TLS
- Twitch app redirect URL matches production domain

See `docs/` for architecture, API reference, and full setup guide.
