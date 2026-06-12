# Soundlist - Security Model and Invariants

How Soundlist protects secrets and data, and the invariants that must
stay true. Read this before touching `app/main.py`, `app/settings.py`,
or anything that serves files or handles credentials.

## Table of Contents

- [Threat Model](#threat-model)
- [Static File Serving (Allowlist)](#static-file-serving-allowlist)
- [Secrets Handling](#secrets-handling)
- [Authentication and Authorization](#authentication-and-authorization)
- [CSRF Protection](#csrf-protection)
- [Invariants to Preserve](#invariants-to-preserve)
- [Hardening Log](#hardening-log)

## Threat Model

The app runs a public board (anonymous read) alongside an authenticated
management panel (Twitch OAuth). The same process serves both. The main
risks are:

- Leaking server-side secrets (Twitch client secret, session signing
  key) or the SQLite database over HTTP.
- A logged-in streamer reading or writing another streamer's channel.
- Cross-site request forgery against the panel's state-changing POSTs.

## Static File Serving (Allowlist)

The public board needs exactly four files from the project root:
`index.html`, `styles.css`, `app.js`, `marquee.html`. They are served
by an explicit allowlist route in `app/main.py`:

```python
_PUBLIC_FILES = frozenset(
    {"index.html", "styles.css", "app.js", "marquee.html"}
)

@app.get("/{filename}", include_in_schema=False)
async def public_asset(filename: str) -> FileResponse:
    if filename not in _PUBLIC_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_ROOT / filename)
```

Why an allowlist and not `StaticFiles(directory=root)`:

- Mounting the whole project root would serve `.env`, `soundlist.db`,
  `.git/`, `uv.lock`, `pyproject.toml`, and every file under `app/`
  to any anonymous visitor. That is a full secret and database leak.
- The single-segment route `/{filename}` is registered after all API
  routers and after `/healthz`, so it never shadows them. It cannot
  match slashed paths, so `lists/*.json` stays with the lists router.
- The fixed `frozenset` has no slashes, so there is no path traversal.

Regression coverage lives in `tests/test_static.py`: board files return
200, secrets and source return 404, and `/healthz` is not shadowed.

Do NOT reintroduce a directory mount. To expose a new public file, add
its name to `_PUBLIC_FILES` and add a case to `tests/test_static.py`.

## Secrets Handling

- `TWITCH_CLIENT_SECRET` and `SESSION_SECRET_KEY` are typed as Pydantic
  `SecretStr` in `app/settings.py`. `SecretStr` masks the value as
  `**********` in any `repr`, log line, or traceback, so an accidental
  `log.info(settings)` or an exception dump cannot leak them.
- Read the real value only at the point of use with
  `.get_secret_value()`. Current call sites: Authlib registration in
  `app/auth.py`, the app-token grant in `app/admin.py`, and the session
  middleware in `app/main.py`. Do not store the unwrapped value in a
  module global or pass it to anything that logs.
- Secrets come from the environment / `.env` only; `.env` is in
  `.gitignore` and must never be committed. `.env.example` documents
  the required keys with placeholder values.
- The static allowlist above is what keeps `.env` and `soundlist.db`
  off the wire; the two protections work together.

## Authentication and Authorization

- Identity is Twitch OAuth (`/login`, `/auth/callback`). The session is
  a signed cookie; the user row is reloaded per request in
  `current_user`, so a demoted or deleted user loses access immediately.
- Authorization is enforced at the route layer, never in business
  logic:
  - `require_user` - any authenticated user.
  - `require_channel_access` - admin or the channel owner; 403/404.
  - `_require_admin` - admin only.
- `library.add_to_channel` re-checks ownership because it takes the
  channel id from the form rather than the path.

See `ARCHITECTURE.md` "Security Architecture" for the full RBAC table.

## CSRF Protection

Every state-changing POST carries a hidden `csrf` field validated by
`require_csrf` (`app/csrf.py`) using `secrets.compare_digest` against a
per-session token. JSON endpoints (for example `/c/{slug}/reorder`)
carry the token in the request body. `csrf_enabled` can be turned off
only for tests.

## Invariants to Preserve

These are load-bearing. Breaking one is a security regression:

1. The project root is never served as a directory. Public files go
   through the `_PUBLIC_FILES` allowlist, with a matching test.
2. Secret settings stay `SecretStr`; unwrap only at the call site with
   `.get_secret_value()`, never into a logged value.
3. `.env` and `soundlist.db` stay untracked by git.
4. Every state-changing route keeps its auth dependency
   (`require_user` / `require_channel_access` / `_require_admin`) and
   its `require_csrf` call.
5. `database_url` stays SQLite (`Settings._sqlite_only` enforces this).

## Hardening Log

- D6 - Replaced the root `StaticFiles` mount (which served `.env`,
  `soundlist.db`, `.git/`, and all source, and shadowed `/healthz`)
  with the `_PUBLIC_FILES` allowlist route. Added `tests/test_static.py`.
- D7 - Moved `twitch_client_secret` and `session_secret_key` to
  `SecretStr` so they are masked in reprs and tracebacks; call sites use
  `.get_secret_value()`.
- D8 - New-trigger `position` is computed as `max(position) + 1` rather
  than `len(rows)`, which could reuse a position after a mid-list delete
  (not a security issue, but a correctness one tracked here for context).
