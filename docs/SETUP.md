# Soundlist - Setup and Installation Guide

This document covers setting up the development and production environments for the Soundlist management panel.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Environment Setup](#development-environment-setup)
- [Database Setup](#database-setup)
- [Twitch OAuth Configuration](#twitch-oauth-configuration)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Production Deployment](#production-deployment)

## Prerequisites

- Python 3.11 or later
- `uv` package manager (https://docs.astral.sh/uv/)
- Git
- Twitch Developer account (for OAuth setup)

### Verifying Python Version

```bash
python --version  # Should output 3.11 or later
```

If you need Python 3.11, use your system package manager or `pyenv`:

```bash
# macOS with Homebrew
brew install python@3.11

# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv

# Using pyenv (cross-platform)
pyenv install 3.11.x
pyenv local 3.11.x
```

### Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or using your system package manager:

```bash
# macOS with Homebrew
brew install uv

# Ubuntu/Debian
sudo apt-get install uv
```

## Development Environment Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd soundlist
```

### 2. Install Dependencies

The project uses `uv` for dependency management. Install all dependencies including dev tools:

```bash
# Install runtime and development dependencies
uv sync

# This creates a local virtual environment in .venv/
# and installs all packages from pyproject.toml
```

To verify installation:

```bash
uv pip list | grep -E "fastapi|sqlmodel|authlib"
```

### 3. Verify Installation

Ensure critical packages are installed:

```bash
python -c "import fastapi, sqlmodel, authlib; print('OK')"
```

### 4. Copy Environment Template

```bash
cp .env.example .env
```

Edit `.env` with your local configuration (see [Environment Variables](#environment-variables) section).

## Database Setup

### Local SQLite Database

The application uses SQLite for local development. The database file is automatically created on first run:

```bash
# Database location (created automatically)
soundlist.db
```

### Database Schema

The schema is automatically created on application startup via SQLModel:

- `user` table - Twitch users and admins
- `channel` table - Streamer soundboards
- `sound` table - Shared audio assets
- `soundclip` table - Multi-clip sound variants
- `channelsound` table - Channel trigger associations

### Importing Legacy Data

If you have existing `lists/*.json` files:

```bash
# Start the app first (creates empty DB)
uv run soundlist

# In a new terminal, run the importer
uv run python scripts/import_json.py

# This loads all JSON files into the database
```

The importer:
- Reads all `lists/*.json` files
- Creates `Channel` records from filenames
- Creates `Sound` records from trigger data
- Creates `ChannelSound` links
- Preserves volume, chance, cooldown, enabled status
- Round-trips perfectly (output JSON matches input)

### Resetting the Database

To start fresh (development only):

```bash
rm soundlist.db
# Next run will recreate empty schema
```

## Twitch OAuth Configuration

### Registering an Application

1. Visit https://dev.twitch.tv/console/apps
2. Click "Create Application"
3. Fill in:
   - Name: "Soundlist Dev" (for development) or "Soundlist" (production)
   - OAuth Redirect URL: `http://localhost:8000/auth/callback` (dev) or your production domain
   - Category: Any category
4. Accept terms and create

### Getting Credentials

1. In the application console, click "Manage"
2. Copy the **Client ID**
3. Click "New Secret" and copy the **Client Secret**

### Local Development Setup

```bash
# In .env or as environment variables
TWITCH_CLIENT_ID=<your-client-id>
TWITCH_CLIENT_SECRET=<your-client-secret>

# For dev environment
APP_ENV=development
IS_PRODUCTION=false

# Must set for local testing
SESSION_SECRET_KEY=<random-32-char-string>
```

Generate a random session secret:

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

### Production OAuth Setup

For production deployment:

1. Update your Twitch app's OAuth Redirect URL to your actual domain:
   - `https://yourdomain.com/auth/callback`

2. Set environment variables:

```bash
TWITCH_CLIENT_ID=<your-client-id>
TWITCH_CLIENT_SECRET=<your-client-secret>
APP_ENV=production
IS_PRODUCTION=true
SESSION_SECRET_KEY=<secure-random-key>
```

## Environment Variables

Create a `.env` file in the project root with these variables:

```bash
# Twitch OAuth
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here

# Session security
SESSION_SECRET_KEY=your_random_secret_key_here

# Environment
APP_ENV=development  # or 'production'
IS_PRODUCTION=false  # or 'true'

# Database (optional, defaults to soundlist.db)
DATABASE_URL=sqlite:///./soundlist.db

# Admin users (comma-separated Twitch login names)
# These are seeded on first run; can be edited in the UI later
ADMIN_LOGINS=your_twitch_login

# Server (optional)
HOST=0.0.0.0
PORT=8000
```

### Environment Variable Details

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `TWITCH_CLIENT_ID` | Yes | - | From Twitch Developer Console |
| `TWITCH_CLIENT_SECRET` | Yes | - | From Twitch Developer Console |
| `SESSION_SECRET_KEY` | Yes | - | 32+ random characters |
| `APP_ENV` | No | development | `development` or `production` |
| `IS_PRODUCTION` | No | false | Disables debug features if true |
| `ADMIN_LOGINS` | No | - | Comma-separated user IDs for initial admin |
| `DATABASE_URL` | No | sqlite:///./soundlist.db | SQLite path (local) or PostgreSQL (production) |
| `HOST` | No | 0.0.0.0 | Server bind address |
| `PORT` | No | 8000 | Server port |

## Running the Application

### Development Mode

```bash
# Start the development server with auto-reload
uv run soundlist

# Server runs at http://localhost:8000
```

The app includes:
- Auto-reload on code changes
- API documentation at `http://localhost:8000/api/docs`
- Structured logging with `[INFO]`/`[WARN]`/`[ERROR]` prefixes

### Manual Uvicorn Invocation

If you need custom parameters:

```bash
uv run uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

### Checking Health

```bash
curl http://localhost:8000/healthz
# Response: {"status":"ok"}
```

## Testing

### Running Tests

```bash
# Run all tests with pytest
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_auth.py

# Run a specific test
uv run pytest tests/test_auth.py::test_login_redirect
```

### Test Coverage

```bash
# Run with coverage report
uv run pytest --cov=app --cov-report=html

# View coverage in browser
open htmlcov/index.html
```

### Test Organization

- `tests/test_auth.py` - Authentication and session tests
- `tests/test_importer.py` - JSON importer tests
- `tests/test_library.py` - Sound library CRUD tests
- `tests/test_panel.py` - Channel editor tests
- `tests/test_serializer.py` - JSON output format tests
- `tests/test_parity.py` - Round-trip import/export verification
- `tests/conftest.py` - Shared test fixtures and database setup

## Code Quality

### Linting

```bash
# Check code with ruff (formatter + linter)
uv run ruff check app/ tests/

# Auto-fix simple issues
uv run ruff check --fix app/ tests/

# Check formatting
uv run ruff format --check app/ tests/

# Format code
uv run ruff format app/ tests/
```

### Type Checking with Pylint

```bash
# Run pylint on app
uv run pylint app/

# Individual modules
uv run pylint app/main.py app/models.py
```

### Pre-commit

All commits should pass linting and tests:

```bash
# Before committing
uv run ruff check --fix app/ tests/
uv run ruff format app/ tests/
uv run pytest
```

## Production Deployment

### Environment Checklist

- [ ] Twitch OAuth redirect URL configured for your domain
- [ ] `SESSION_SECRET_KEY` set to a cryptographically secure value
- [ ] `IS_PRODUCTION=true` in environment
- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite) for production
- [ ] `ADMIN_LOGINS` set to initial admin user list

### Running as a Service

For systemd (Linux):

```ini
# /etc/systemd/system/soundlist.service
[Unit]
Description=Soundlist Management Panel
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/soundlist
Environment="PATH=/opt/soundlist/.venv/bin"
ExecStart=/opt/soundlist/.venv/bin/uv run soundlist
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
systemctl enable soundlist
systemctl start soundlist
systemctl status soundlist
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name soundlist.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/docs {
        # Optionally restrict docs to internal network
        deny all;
    }
}
```

### Database Migration (SQLite to PostgreSQL)

For scaling to production, consider migrating from SQLite:

```bash
# This is a manual process involving:
# 1. Exporting data from SQLite
# 2. Setting up PostgreSQL
# 3. Running migrations
# 4. Updating DATABASE_URL in environment

# For now, the app supports both via SQLAlchemy
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
uv run uvicorn app.main:app --port 8001
```

### Database Lock (SQLite)

If you see "database is locked" errors:

```bash
# Ensure no other processes are using the database
ps aux | grep soundlist

# Check for leftover lock files
ls -la soundlist.db*
```

### OAuth Callback Errors

Verify:
1. Twitch app OAuth Redirect URL matches your deployment URL exactly
2. `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` are correct
3. Internet connectivity (the app makes external calls to Twitch API)

### Importer Fails

```bash
# Check JSON file format
python -m json.tool lists/MyChannel.json

# Verify schema matches (check for "sounds" key)
# See REQUIREMENTS.md Section 5 for expected structure
```

## Next Steps

Once setup is complete:

1. **Create Admin User** - Set `ADMIN_LOGINS` to your Twitch login
2. **Test OAuth** - Click "Login with Twitch" at `http://localhost:8000`
3. **Import Legacy Data** - Run `scripts/import_json.py` to load existing soundboards
4. **Add Sounds** - Create library sounds and link them to channels
5. **Verify JSON Output** - Check `http://localhost:8000/lists/index.json`

See [ARCHITECTURE.md](ARCHITECTURE.md) for how components fit together and [API.md](API.md) for endpoint details.
