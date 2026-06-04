# Soundlist Management Panel - Requirements

Status keys: MUST = required for v1, SHOULD = wanted, LATER = deferred.

## 1. Functional

### Auth and identity
- FR-1 (MUST) Users log in with Twitch OAuth; no local passwords.
- FR-2 (MUST) Session persisted in a signed cookie; logout clears it.
- FR-3 (MUST) On first login, match the Twitch user id to a channel
  owner; unmatched users get a no-channels dashboard.
- FR-4 (MUST) Admins are seeded from an env list of Twitch logins on
  startup, then editable as a DB flag.

### Roles (RBAC)
- FR-5 (MUST) Role `streamer`: read/write only own channel(s).
- FR-6 (MUST) Role `admin`: read/write all channels and the library, and
  manage channels/owners/admin flags.
- FR-7 (MUST) Every channel-scoped action is authorized server-side
  (no trusting the client).

### Channel sound editor
- FR-8 (MUST) List a channel's triggers with all fields.
- FR-9 (MUST) Add a trigger: pick an existing library Sound or create a
  new one inline, set trigger_word, volume, chance, cooldown, enabled.
- FR-10 (MUST) Edit and delete a trigger.
- FR-11 (MUST) Toggle enabled without a full edit.
- FR-12 (MUST) trigger_word unique per channel; reject duplicates.
- FR-13 (SHOULD) Reorder triggers (position field).

### Shared sound library and linking
- FR-14 (MUST) Browse/search library assets.
- FR-15 (MUST) Link an existing asset to a channel as a new trigger.
- FR-16 (MUST) Both streamer and admin can add new assets.
- FR-17 (MUST) Editing an asset URL updates every channel linked to it.
- FR-18 (MUST) Per-channel volume/chance/cooldown override the asset
  default without affecting other channels.
- FR-19 (MUST) Support random multi-clip assets (weighted clips), as the
  current data already uses.
- FR-20 (SHOULD) Show how many channels use an asset before edit/delete;
  block delete while in use.

### Testing / setup view
- FR-21 (MUST) Play any sound in-browser to test before saving.
- FR-22 (MUST) Preview the channel exactly as the public board renders
  it (live generated JSON).
- FR-23 (SHOULD) Validate a trigger word and audio URL is reachable.

### Compatibility
- FR-24 (MUST) Serve `lists/index.json` and `lists/<slug>.json` in the
  exact legacy shape from the DB.
- FR-25 (MUST) Serve `internals/avatars.json` and `IconTriggers2.json`.
- FR-26 (MUST) One-time importer loads current `lists/*.json` into the DB
  with lossless round-trip.

### Admin
- FR-27 (MUST) Create a channel and assign/reassign its owner.
- FR-28 (SHOULD) Grant/revoke admin.
- FR-29 (LATER) CRUD for avatars and emote icon triggers via UI.

### Assets
- FR-30 (LATER) Upload audio files to R2 instead of pasting URLs.

## 2. Non-functional

- NFR-1 (MUST) Python 3.11+, FastAPI (latest), SQLModel + SQLite.
- NFR-2 (MUST) Server-rendered Jinja2; minimal vanilla JS only for the
  test player. No SPA build chain.
- NFR-3 (MUST) ASCII-only source/output, global imports, full type hints,
  PEP 8, max 79 cols, ruff + pylint clean (per repo standards).
- NFR-4 (MUST) Secrets (Twitch client id/secret, session key) from env,
  never committed.
- NFR-5 (MUST) CSRF protection on all state-changing POST forms.
- NFR-6 (MUST) JSON endpoints are public read-only (the public board is
  unauthenticated today); editing requires auth.
- NFR-7 (SHOULD) Round-trip parity test: import then export equals the
  original JSON (modulo key order / whitespace).
- NFR-8 (SHOULD) Runs with `uv run uvicorn ...`; single process is fine
  for this scale (~25 channels, <100 sounds each).
- NFR-9 (SHOULD) Structured logs with `[INFO]/[WARN]/[ERROR]` prefixes.

## 3. Data integrity

- DR-1 (MUST) `enabled` exported as legacy string "true"/"false".
- DR-2 (MUST) `chance` stored/exported as string with "%".
- DR-3 (MUST) Single-clip sound exports `sound` as a string; random
  exports the clip array.
- DR-4 (MUST) Deleting a Sound in use is blocked (FR-20).
- DR-5 (MUST) Channel slug stable and unique; it is the JSON filename and
  URL key.

## 4. Acceptance criteria (v1 done when)

- A streamer logs in via Twitch, sees only their channel, adds a trigger
  linked to a library sound, sets volume, saves, and the public board
  plays it.
- An admin edits another streamer's channel and the library.
- Editing one shared asset URL changes it for all linked channels.
- The test view plays a sound and shows the generated JSON.
- `lists/*.json` served from DB matches the legacy shape; the existing
  public board works pointed at the app with no board code changes beyond
  base path.
