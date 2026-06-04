# Soundlist

Management panel for Twitch soundboard channels. Each streamer logs in
with Twitch OAuth, edits their own soundboard, and sounds are served
at `/lists/<slug>.json` in the legacy format so the public board
(`app.js` + `index.html`) keeps working unchanged.

Built with Python 3.11, FastAPI 0.115, SQLModel + SQLite, Twitch OAuth.

## Quick start

```bash
uv sync
cp .env.example .env
$EDITOR .env           # fill in Twitch credentials
uv run soundlist       # starts at http://localhost:8000
```

On first run with existing data:

```bash
uv run python scripts/import_json.py   # import lists/*.json into DB (idempotent)
```

API docs (dev only): http://localhost:8000/api/docs

## Environment variables

### Required

| Variable | Description |
|---|---|
| `TWITCH_CLIENT_ID` | Client ID from dev.twitch.tv/console/apps |
| `TWITCH_CLIENT_SECRET` | Client secret from same page |
| `TWITCH_REDIRECT_URI` | Must match Twitch app; default `http://localhost:8000/auth/callback` |
| `SESSION_SECRET_KEY` | Random hex: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_LOGINS` | Comma-separated Twitch logins seeded as admins on first startup |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./soundlist.db` | SQLite file path |
| `APP_ENV` | `development` | Set `production` for strict cookies, no API docs |
| `CSRF_ENABLED` | `true` | Set `false` to bypass CSRF in dev |
| `ALLOW_SELF_REGISTER` | `true` | Let users create a channel for their Twitch login from the dashboard |

## Tests and linting

```bash
uv run pytest
uv run ruff check app/
uv run pylint app/
```

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
- `SESSION_SECRET_KEY` is a secure random value
- `CSRF_ENABLED=true` (default)
- SQLite file on a persistent volume
- TLS handled by Nginx or Caddy
- Twitch app redirect URL matches production domain

## Documentation

| Document | Purpose |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Full installation, Twitch OAuth setup, troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, module layout, RBAC, data model |
| [docs/API.md](docs/API.md) | Every HTTP endpoint with request/response examples |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | Component interactions, request flow, auth flow |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Coding standards, common tasks, git workflow |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Functional requirements and JSON output contract |
| [docs/TASKLIST.md](docs/TASKLIST.md) | Milestone progress and tech-debt items |

Start at [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) for a guided overview by role (new dev, deploying, debugging, etc.).
