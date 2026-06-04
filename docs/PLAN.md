# Soundlist Management Panel - Plan

## 1. Problem

Today every streamer soundboard is a hand-edited JSON file in `lists/`.
The public board (`index.html` + `app.js`) loads those files directly.
Editing is manual, error-prone, and only the repo owner can do it.

Goal: a small Python web app that lets each Twitch streamer log in and
manage their own sounds, lets a site admin manage everyone, and lets
common sounds be shared (linked) across streamers instead of copy-pasted.

Constraint from owner: keep it simple, keep it sane.

## 2. Scope

In scope:
- Twitch OAuth login.
- RBAC: `admin` (all channels) and `streamer` (own channels only).
- Per-channel sound editor: add/edit/delete/enable triggers, set volume,
  chance, cooldown.
- Shared sound library: link the same sound asset to many channels; add
  new assets (by streamer or admin).
- Testing/setup view: play a sound in-browser before saving; preview a
  channel as the public board sees it.
- Backward compatibility: keep serving the existing JSON shape so the
  current public board keeps working unchanged.

Out of scope (later, noted but not built now):
- Direct audio file upload / hosting (keep URL-based, assets live on R2 /
  catbox as today). Upload is a stretch task.
- Editing emote icon triggers (`IconTriggers2.json`) and avatars via UI -
  read-only import first, admin CRUD later.
- Public board redesign. Untouched except it now reads from the API.

## 3. Key decisions

### 3.1 Source of truth: SQLite, JSON generated
The linking requirement (one sound, many channels) is relational. Keeping
hand-edited JSON canonical makes linking and RBAC awkward. So:
- SQLite is canonical (via SQLModel / SQLAlchemy 2.0).
- The app exposes `GET /lists/<channel>.json` and `GET /lists/index.json`
  that render the exact legacy shape from the DB.
- One-time importer loads existing `lists/*.json` into the DB.

This preserves the public board (it just points at the API) while giving
us a sane model for linking and permissions.

### 3.2 Server-rendered panel, not an SPA
FastAPI + Jinja2 templates + a little vanilla JS for the test player.
A new team member understands a form post in 30 seconds; an SPA build
chain is overkill for ~25 streamers.

### 3.3 Auth
Twitch OAuth Authorization Code flow (Authlib). Session in a signed
cookie (Starlette `SessionMiddleware`). No passwords stored.
Admins listed by Twitch login in config/env on first run; thereafter a
DB flag. Login matched to channels by Twitch user id.

### 3.4 Stack (version-specific)
- Python 3.11+, FastAPI (latest 0.1xx), Uvicorn.
- SQLModel on SQLAlchemy 2.0, SQLite.
- Authlib for Twitch OAuth, httpx for Twitch API calls.
- Jinja2 templates.
- uv for packages, ruff + pylint, config in `pyproject.toml`.
- Alembic deferred; start with `create_all`, add migrations when schema
  stabilizes.

## 4. Data model

```
User
  id            (pk)
  twitch_id     (unique)        # stable Twitch user id
  login         (unique)        # lowercase twitch login
  display_name
  avatar_url
  is_admin      (bool)
  created_at

Channel                         # a soundboard belonging to a streamer
  id            (pk)
  slug          (unique)        # e.g. "RadiantSoul_Tv", used in JSON/url
  display_name
  owner_id      -> User.id      # nullable until claimed via OAuth
  avatar_url                    # imported from avatars.json
  is_sub_board  (bool)          # e.g. RadiantSoul_Tv_Sub
  created_at

Sound                           # shared library asset (the audio itself)
  id            (pk)
  name          (unique label)  # human name for the library
  default_volume
  is_random     (bool)          # true => use SoundClip rows
  url           (nullable)      # single-clip sounds
  created_by    -> User.id
  created_at

SoundClip                       # one weighted clip of a random Sound
  id            (pk)
  sound_id      -> Sound.id
  url
  volume
  chance        (e.g. "3.3%")

ChannelSound                    # a trigger on a channel, links a Sound
  id            (pk)
  channel_id    -> Channel.id
  sound_id      -> Sound.id     # the link; shared across channels
  trigger_word
  volume        (override, nullable -> Sound.default_volume)
  chance        (default "100%")
  trigger_cooldown (default 0)
  enabled       (bool, default true)
  position      (int, for ordering)
  unique(channel_id, trigger_word)
```

Notes:
- "Linking" = two `ChannelSound` rows pointing at the same `Sound`. Edit
  the asset URL once, every channel using it updates.
- Per-channel `volume`/`chance`/`cooldown` stay per-row so streamers tune
  a shared sound without affecting others.
- Random/multi-clip sounds (already in the data) map to `is_random` +
  `SoundClip` rows.

## 5. JSON compatibility layer (hard contract)

SQLite is the internal store. The four endpoints below regenerate the
legacy JSON on every request. The output shape is a HARD CONTRACT because
the public board (app.js) and any downstream tools consume it without
change.

The serializer (T1.4) is the single place that enforces these rules:
- `enabled`  -> string "true"/"false", never boolean
- `chance`   -> string with "%" suffix
- `sound`    -> plain string for single-clip, flat string array for multi

Endpoints:

  GET /lists/index.json
    { "<slug>": "lists/<slug>.json", ... }

  GET /lists/<slug>.json
    { "sounds": [ { "trigger_word": str, "sound": str|[str,...],
      "volume": float, "chance": "N%", "trigger_cooldown": int,
      "enabled": "true"|"false" }, ... ] }

  GET /lists/internals/avatars.json
    { "<slug>": "<avatar_url>", ... }

  GET /lists/internals/IconTriggers2.json
    { "<trigger_word>": "<image_or_7tv_url>", ... }

All four are public (no auth). Unknown slug -> 404.
See REQUIREMENTS.md Section 5 for full field rules and annotated examples.

The public board's `app.js` only changes its base path (or nothing, if we
mount the app at the same origin and route `/lists/*`).

## 6. Views / routes

- `GET /login` -> Twitch OAuth redirect.
- `GET /auth/callback` -> create/lookup user, set session, redirect.
- `GET /logout`.
- `GET /` -> dashboard: channels the user may manage.
- `GET /c/<slug>` -> sound editor table for a channel.
- `POST /c/<slug>/sound` -> add trigger (link existing Sound or new).
- `POST /c/<slug>/sound/<id>` -> edit.
- `POST /c/<slug>/sound/<id>/delete`, `.../toggle`.
- `GET /library` -> shared sound library, search, add asset.
- `POST /library` -> create Sound (+ clips).
- `GET /c/<slug>/test` -> testing/setup view (in-browser player + live
  preview of generated JSON).
- Admin-only: `GET /admin`, manage channels, assign owners, set admins.

RBAC guard: a dependency that loads the session user and asserts
`is_admin or channel.owner_id == user.id` for channel routes.

## 7. Milestones

M1 Skeleton + DB + importer (read-only JSON parity with today).
M2 Twitch OAuth + sessions + RBAC.
M3 Channel sound editor (CRUD).
M4 Shared library + linking.
M5 Testing/setup view.
M6 Admin panel + polish + deploy.

See TASKLIST.md for the breakdown.

## 8. Risks / assumptions

- Assumption: assets stay URL-hosted (R2/catbox). Upload is later.
- Assumption: a channel has one owner; admin overrides. Multi-mod per
  channel is not requested - skip.
- Risk: legacy JSON has quirks (`enabled` is the string "true", `chance`
  is a string with "%"). Importer and exporter must round-trip these
  exactly. Covered by a parity test.
- Risk: Twitch login casing. Store lowercase `login`, keep display name
  separate; match channels by `twitch_id`, not name.
