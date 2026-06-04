# Soundlist Management Panel - Tasklist

Ordered, each task is one commit-sized unit. Test before moving on.
Maps to milestones M1-M6 in PLAN.md.

## M1 - Skeleton, DB, importer (JSON parity)

- [ ] T1.1 Init Python project: `pyproject.toml`, `uv`, deps (fastapi,
      uvicorn, sqlmodel, authlib, httpx, jinja2, itsdangerous,
      python-multipart), ruff + pylint config. ASCII, 79 cols.
- [ ] T1.2 App skeleton: `app/main.py` FastAPI instance, settings from
      env (pydantic-settings), `.env.example`, healthcheck route.
- [ ] T1.3 Models: User, Channel, Sound, SoundClip, ChannelSound
      (SQLModel) + `create_all` on startup.
- [ ] T1.4 JSON serializer: DB -> legacy shape (single vs random sound,
      string `enabled`, "%"-`chance`). Pure function, unit-tested.
- [ ] T1.5 Importer script: parse `lists/*.json`, `index.json`,
      `internals/avatars.json`, dedupe identical sound URLs into shared
      Sound rows, populate DB. Idempotent.
- [ ] T1.6 Read-only endpoints: `/lists/index.json`, `/lists/<slug>.json`,
      `/lists/internals/avatars.json`, `/lists/internals/IconTriggers2.json`.
- [ ] T1.7 Parity test: import then export each channel equals original
      JSON (content-equal, key order ignored). Must pass for all 25.

## M2 - Auth, sessions, RBAC

- [ ] T2.1 Twitch OAuth via Authlib: `/login`, `/auth/callback`; fetch
      user id/login/display/avatar; upsert User.
- [ ] T2.2 Sessions: `SessionMiddleware` signed cookie; `/logout`.
- [ ] T2.3 Admin seeding: env `ADMIN_LOGINS` sets `is_admin` on startup.
- [ ] T2.4 Auth dependencies: `current_user`, `require_user`,
      `require_channel_access(slug)` (admin or owner). Server-side only.
- [ ] T2.5 Owner matching: link User to Channel by twitch_id on login.

## M3 - Channel sound editor

- [ ] T3.1 Base layout template + nav + flash messages + CSRF token
      helper.
- [ ] T3.2 Dashboard `/`: channels current user may manage.
- [ ] T3.3 Channel editor `/c/<slug>`: table of triggers, all fields.
- [ ] T3.4 Add trigger `POST /c/<slug>/sound` (link existing or new
      inline Sound). Validate unique trigger_word per channel.
- [ ] T3.5 Edit `POST /c/<slug>/sound/<id>`, delete, toggle enabled.
- [ ] T3.6 CSRF on all forms; friendly validation errors.

## M4 - Shared library and linking

- [ ] T4.1 Library `/library`: list + search assets, usage count.
- [ ] T4.2 Create asset `POST /library` (single or random + clips).
- [ ] T4.3 Link asset to channel from editor (reuse T3.4 path).
- [ ] T4.4 Edit asset; propagates to all linked channels.
- [ ] T4.5 Block delete of an in-use asset; show using channels.

## M5 - Testing / setup view

- [ ] T5.1 `/c/<slug>/test`: in-browser player (vanilla JS, reuse public
      board audio approach) to audition each trigger.
- [ ] T5.2 Live preview of generated channel JSON on the same page.
- [ ] T5.3 (SHOULD) URL reachability + trigger-word validation helper.

## M6 - Admin, polish, deploy

- [ ] T6.1 Admin `/admin`: create channel, assign/reassign owner.
- [ ] T6.2 (SHOULD) Grant/revoke admin flag.
- [ ] T6.3 Point public board `app.js` base path at the app's `/lists/*`;
      verify board works end-to-end unchanged otherwise.
- [ ] T6.4 README: setup, env vars, `uv run`, import, deploy notes.
- [ ] T6.5 Lint/type pass: ruff + pylint clean, full type hints.
- [ ] T6.6 Deploy notes: uvicorn behind reverse proxy, persistent SQLite
      volume, env secrets.

## Stretch (LATER)

- [ ] S1 Audio upload to R2 (presigned PUT) instead of URL paste.
- [ ] S2 Admin CRUD for avatars and emote icon triggers.
- [ ] S3 Reorder triggers via drag (position field already in model).
- [ ] S4 Alembic migrations once schema stabilizes.

## Definition of done per task

- Code: ASCII, global imports, type hints, 79 cols, ruff + pylint clean.
- Tests for pure logic (serializer, importer, RBAC guard).
- `git add` + Conventional Commit + push per repo protocol.
