# Soundlist Management Panel - Tasklist

Ordered, each task is one commit-sized unit. Test before moving on.
Maps to milestones M1-M6 in PLAN.md.

Status: M1-M6 done. Stretch/debt items remain.

## M1 - Skeleton, DB, importer (JSON parity)

- [x] T1.1 Init Python project: `pyproject.toml`, `uv`, deps (fastapi,
      uvicorn, sqlmodel, authlib, httpx, jinja2, itsdangerous,
      python-multipart), ruff + pylint config. ASCII, 79 cols.
- [x] T1.2 App skeleton: `app/main.py` FastAPI instance, settings from
      env (pydantic-settings), `.env.example`, healthcheck route.
- [x] T1.3 Models: User, Channel, Sound, SoundClip, ChannelSound
      (SQLModel) + `create_all` on startup.
- [x] T1.4 JSON serializer: DB -> legacy shape (single vs random sound,
      string `enabled`, "%"-`chance`). Pure function, unit-tested.
- [x] T1.5 Importer script: parse `lists/*.json`, `index.json`,
      `internals/avatars.json`, dedupe identical sound URLs into shared
      Sound rows, populate DB. Idempotent.
- [x] T1.6 Read-only endpoints: `/lists/index.json`, `/lists/<slug>.json`,
      `/lists/internals/avatars.json`, `/lists/internals/IconTriggers2.json`.
- [x] T1.7 Parity test: import then export each channel equals original
      JSON (content-equal, key order ignored). Must pass for all 25.

## M2 - Auth, sessions, RBAC

- [x] T2.1 Twitch OAuth via Authlib: `/login`, `/auth/callback`; fetch
      user id/login/display/avatar; upsert User.
- [x] T2.2 Sessions: `SessionMiddleware` signed cookie; `/logout`.
- [x] T2.3 Admin seeding: env `ADMIN_LOGINS` sets `is_admin` on startup.
- [x] T2.4 Auth dependencies: `current_user`, `require_user`,
      `require_channel_access(slug)` (admin or owner). Server-side only.
- [x] T2.5 Owner matching: link User to Channel by login slug on login.

## M3 - Channel sound editor

- [x] T3.1 Base layout template + nav + flash messages + CSRF token
      helper.
- [x] T3.2 Dashboard `/`: channels current user may manage.
- [x] T3.3 Channel editor `/c/<slug>`: table of triggers, all fields.
- [x] T3.4 Add trigger `POST /c/<slug>/sound` (link existing or new
      inline Sound). Validate unique trigger_word per channel.
- [x] T3.5 Edit `POST /c/<slug>/sound/<id>`, delete, toggle enabled.
- [x] T3.6 CSRF on all forms; friendly validation errors.

## M4 - Shared library and linking

- [x] T4.1 Library `/library`: list + search assets, usage count.
- [x] T4.2 Create asset `POST /library` (single or random + clips).
- [x] T4.3 Link asset to channel from editor (reuse T3.4 path).
- [x] T4.4 Edit asset; propagates to all linked channels.
- [x] T4.5 Block delete of an in-use asset; show using channels.

## M5 - Testing / setup view

- [x] T5.1 `/c/<slug>/test`: in-browser player (vanilla JS, reuse public
      board audio approach) to audition each trigger.
- [x] T5.2 Live preview of generated channel JSON on the same page.
- [x] T5.3 (SHOULD) URL reachability + trigger-word validation helper.

## M6 - Admin, polish, deploy

- [x] T6.1 Admin `/admin`: create channel, assign/reassign owner.
- [x] T6.2 (SHOULD) Grant/revoke admin flag.
- [x] T6.3 Point public board `app.js` base path at the app's `/lists/*`;
      verify board works end-to-end unchanged otherwise.
- [x] T6.4 README: setup, env vars, `uv run`, import, deploy notes.
- [x] T6.5 Lint/type pass: ruff + pylint clean, full type hints.
- [x] T6.6 Deploy notes: uvicorn behind reverse proxy, persistent SQLite
      volume, env secrets.

## Stretch (LATER)

- [ ] S1 Audio upload to R2 (presigned PUT) instead of URL paste.
- [ ] S2 Admin CRUD for avatars and emote icon triggers.
- [x] S3 Reorder triggers via drag (position field already in model).
- [ ] S4 Alembic migrations once schema stabilizes.

## Tech debt / follow-ups (from M1-M4 code review)

- [x] D1 pyright added to dev deps; all col-attr `type: ignore` replaced
      with `col()` in panel, library, auth. selectinload arg-type kept
      (SQLModel relationship type-stub limitation, not a column attr).
- [x] D2 httpx2 added to dev deps (silences StarletteDeprecationWarning);
      `filterwarnings = ["error", ignore::StarletteDeprecationWarning]`
      in pytest config so future deprecations fail loudly.
- [x] D3 All `created_at` fields now use `DateTime(timezone=True)` so
      SQLite stores and round-trips the UTC offset correctly.
- [x] D4 Form fields folded into `_AddSoundForm`, `_EditSoundForm`,
      `_CreateAssetForm`, `_EditAssetForm` bound via `Depends()`.
      `max-args` reverted from 15 to 9 (form DI class init ceiling).
- [x] D5 T6.5 lint pass complete: ruff + pylint 10.00/10, 79-col enforced,
      `on_event` -> lifespan, `func.count` false positive suppressed inline.

## Definition of done per task

- Code: ASCII, global imports, type hints, 79 cols, ruff + pylint clean.
- Tests for pure logic (serializer, importer, RBAC guard).
- `git add` + Conventional Commit + push per repo protocol.
