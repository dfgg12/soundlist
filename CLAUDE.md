# CLAUDE.md - Agent guide for the Soundlist repo

Guidance for an LLM agent working in this repository. Read this and
`docs/SECURITY.md` before changing `app/main.py`, `app/settings.py`, or
anything that serves files or handles credentials.

## What this is

FastAPI app (Python 3.11+, SQLModel, SQLite) with two faces in one
process: an anonymous public board (`index.html` + `app.js`, fed by
`/lists/*.json`) and a Twitch-OAuth management panel. Sounds live in a
shared library; channels wire trigger words to sounds via `ChannelSound`.

## Hard invariants - do not break these

1. Never serve the project root as a directory. The root holds `.env`,
   `soundlist.db`, `.git/`, and all source. Public files are served by
   the `_PUBLIC_FILES` allowlist route in `app/main.py`. To expose a new
   public file: add its name to `_PUBLIC_FILES` AND add a case to
   `tests/test_static.py`. Do not add `StaticFiles(directory=...)` on
   the root.
2. `twitch_client_secret` and `session_secret_key` are `SecretStr`.
   Unwrap with `.get_secret_value()` only at the call site (Authlib in
   `auth.py`, app token in `admin.py`, session middleware in `main.py`).
   Never put the unwrapped value where it could be logged.
3. The single-segment route `/{filename}` in `main.py` must stay
   registered after the routers and after `/healthz` so it shadows
   nothing. Routers are included before it in `main.py`.
4. Keep auth + CSRF on every state-changing route: a `require_user` /
   `require_channel_access` / `_require_admin` dependency plus a
   `require_csrf(...)` call. RBAC lives at the route layer, not in
   business logic.
5. `database_url` is SQLite only (`Settings._sqlite_only` rejects
   anything else). Do not add another database backend casually.
6. New-trigger `position` is `max(position) + 1` (see `_next_position`
   in `panel.py` and the inline copy in `library.add_to_channel`). Do
   not revert to `len(rows)` - it collides after a mid-list delete.

## House style (from the global dev prompt)

- ASCII only. No emojis, smart quotes, or `->` arrows in code, comments,
  logs, or commit messages.
- All imports at module top. No imports inside functions.
- Max 79 columns. Full type hints. One-sentence docstring per public
  module/class/function. `from __future__ import annotations` where
  needed.
- No bare `except`; catch specific exceptions.
- Conventional Commits, subject under 50 chars, terse.

## Workflow

- Tests: `uv run pytest -q`. Lint: `uv run ruff check app tests`. Both
  must be clean before committing. Tests treat warnings as errors.
- Import legacy data: `uv run python scripts/import_json.py` (idempotent;
  parses `lists/*.json` into SQLite).
- Run the app: `uv run soundlist` (uvicorn on :8000).
- Commit after each logical unit; push when done.

## Where things live

- `app/main.py` - app wiring, static allowlist, `/healthz`, middleware.
- `app/settings.py` - env-backed config (`SecretStr` secrets).
- `app/auth.py` - Twitch OAuth, session, RBAC dependencies, admin seed.
- `app/panel.py` - dashboard and channel trigger editor.
- `app/library.py` - shared sound library CRUD.
- `app/admin.py` - admin panel (users, channels, avatar refresh).
- `app/lists.py` - read-only legacy JSON endpoints for the board.
- `app/serializer.py` - DB to legacy JSON shape (keep the contract).
- `app/models.py` - SQLModel schema (canonical).
- `scripts/import_json.py` - legacy JSON importer.
- `docs/SECURITY.md` - security model and the invariants above in full.
- `docs/ARCHITECTURE.md`, `docs/API.md` - design and endpoint reference.

## Gotchas

- The legacy JSON contract in `serializer.py` is consumed by `app.js`;
  changing field names or the random-sound shape breaks the board.
- `chance` is stored as a string ("100%", "3.3%") on purpose to preserve
  the legacy format exactly. Do not coerce it to a float.
- `volume` on `ChannelSound` is `None` to mean "inherit
  `Sound.default_volume`"; resolve it only at serialization time.
