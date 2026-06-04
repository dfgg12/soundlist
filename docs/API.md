# Soundlist - API Documentation

Complete reference for all HTTP endpoints exposed by the Soundlist management panel.

## Base URL

- Development: `http://localhost:8000`
- Production: `https://your-domain.com`

## Authentication

### Session-Based Auth

Most endpoints use signed session cookies:

```
GET /lists/<slug>.json
  (No auth required - public endpoint)

GET /c/<slug>
  (Auth required - must have valid session cookie)
  HTTP 401 if unauthenticated
  HTTP 403 if user not owner or admin
```

Session cookies are set on successful OAuth:

```
Set-Cookie: soundlist_session=<signed-value>; Path=/; Max-Age=604800; HttpOnly; SameSite=Lax
```

### Headers

```
Cookie: soundlist_session=<value>
Content-Type: application/json (for JSON POST bodies)
Content-Type: application/x-www-form-urlencoded (for form submissions)
```

## Endpoints

### Authentication Endpoints

#### `GET /login`

Redirects to Twitch OAuth authorization.

**Parameters**: None

**Response**: 302 Redirect to Twitch

**Example**:
```bash
curl -L http://localhost:8000/login
# Redirected to https://id.twitch.tv/oauth2/authorize?...
```

**Notes**:
- This is where the user is directed from the login button
- Twitch redirects back to `/auth/callback`

---

#### `GET /auth/callback?code=<code>`

OAuth callback from Twitch. Exchanges auth code for user info.

**Parameters**:
- `code` (query) - Authorization code from Twitch

**Response**: 302 Redirect to `/` (dashboard)

**Side Effects**:
- Creates or updates User record
- Creates session cookie
- Attempts to claim channels matching user's login

**Example**:
```bash
# User's browser is redirected here by Twitch
GET /auth/callback?code=abc123def456
# Response: 302 to / with Set-Cookie
```

**Errors**:
- Invalid code: 400 Bad Request
- Twitch API error: 500 Internal Server Error

---

#### `GET /logout`

Clears the session cookie and logs out the user.

**Parameters**: None

**Response**: 302 Redirect to `/`

**Example**:
```bash
curl -c cookies.txt -b cookies.txt http://localhost:8000/logout
```

---

### Dashboard & UI Endpoints

#### `GET /`

Main dashboard - shows channels the user can manage.

**Auth**: Required (session cookie)

**Response**: HTML page (server-rendered Jinja2)

**Response Content**:
- List of channels owned by user
- List of all channels if user is admin
- Links to edit each channel
- Link to library
- Link to admin panel (if admin)

**Example**:
```bash
curl -b cookies.txt http://localhost:8000/
# Returns: HTML page
```

---

### Channel Management Endpoints

#### `GET /c/<slug>`

Sound editor for a specific channel.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug (e.g., "Amedoll")

**Response**: HTML page with:
- Table of current triggers with play-preview buttons
- Form to add new trigger
- Edit/delete/toggle buttons for each trigger
- Live preview of the generated channel JSON

**Example**:
```bash
curl -b cookies.txt http://localhost:8000/c/Amedoll
# Returns: HTML editor page
```

**Errors**:
- 401: Not authenticated
- 403: Not owner or admin
- 404: Channel not found

---

#### `POST /c/<slug>/sound`

Add a new trigger to a channel.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug

**Form Parameters**:
- `trigger_word` (string, required) - Word that triggers the sound
- `sound_mode` (string, required) - `"new"` to create a Sound, `"existing"` to link one
- `sound_name` (string, optional) - Name for the Sound (new: used as name; existing: looked up by name)
- `sound_url` (string, required if `sound_mode=new`) - Audio URL for new Sound
- `volume` (float, 0.0-1.0, optional) - Per-trigger override; blank inherits Sound.default_volume
- `chance` (string, optional) - Probability, e.g. "50%". Default: "100%"
- `trigger_cooldown` (integer, optional) - Seconds between triggers. Default: 0
- `csrf` (string, required) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "trigger_word=meow" \
  -F "sound_mode=new" \
  -F "sound_url=https://example.com/meow.ogg" \
  -F "sound_name=Meow Sound" \
  -F "volume=0.7" \
  -F "csrf=<token>" \
  http://localhost:8000/c/Amedoll/sound
```

**Validation**:
- `trigger_word` must be unique per channel
- `sound_mode=existing` requires a matching Sound name in the library
- `sound_mode=new` requires `sound_url`; name defaults to `trigger_word` if blank
- `trigger_cooldown` must be non-negative

**Errors**:
- 401: Not authenticated
- 403: Not owner or admin
- Flash error on duplicate trigger_word or missing URL (redirect, not 4xx)

---

#### `POST /c/<slug>/sound/<id>`

Edit an existing trigger.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug
- `id` (integer) - ChannelSound ID

**Form Parameters**:
- `trigger_word` (string) - Updated trigger word
- `volume` (float, 0.0-1.0) - Updated volume (blank to inherit default)
- `chance` (string) - Updated probability, e.g. "50%"
- `trigger_cooldown` (integer) - Updated cooldown
- `enabled` (checkbox) - present if enabled, absent if disabled
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Notes**:
- Does not change the linked Sound asset
- Only updates per-channel settings
- Other channels linking same Sound are unaffected

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "trigger_word=meow_updated" \
  -F "volume=0.8" \
  -F "chance=75%" \
  -F "csrf=<token>" \
  http://localhost:8000/c/Amedoll/sound/123
```

---

#### `POST /c/<slug>/sound/<id>/delete`

Delete a trigger from a channel.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug
- `id` (integer) - ChannelSound ID

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Notes**:
- Only removes the channel trigger
- Does not delete the underlying Sound asset
- Sound remains available for other channels

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "csrf=<token>" \
  http://localhost:8000/c/Amedoll/sound/123/delete
```

---

#### `GET /c/<slug>/validate`

Check URL reachability and trigger-word uniqueness (used by in-page JS).

**Auth**: Required (owner or admin)

**Query Parameters**:
- `url` (string, optional) - Audio URL to probe with HEAD request
- `trigger_word` (string, optional) - Word to check for uniqueness in the channel
- `exclude_id` (integer, optional) - ChannelSound ID to exclude from the uniqueness check (for edits)

**Response**: JSON
```json
{"url_ok": true, "url_status": 200, "trigger_unique": true}
```

**Example**:
```bash
curl -b cookies.txt \
  "http://localhost:8000/c/Amedoll/validate?url=https://example.com/meow.ogg&trigger_word=meow"
```

---

#### `POST /c/<slug>/sound/<id>/toggle`

Toggle enabled flag on a trigger.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug
- `id` (integer) - ChannelSound ID

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "csrf=<token>" \
  http://localhost:8000/c/Amedoll/sound/123/toggle
```

---

### Library Endpoints

#### `GET /library`

Browse and search the shared sound library.

**Auth**: Required

**Query Parameters**:
- `q` (string, optional) - Search query for sound name

**Response**: HTML page with:
- List of library sounds
- Search box
- Link to create new sound
- Usage counts (how many channels use each)

**Example**:
```bash
curl -b cookies.txt 'http://localhost:8000/library?q=meow'
# Returns: HTML library page with search results
```

---

#### `POST /library`

Create a new sound asset in the library.

**Auth**: Required

**Form Parameters**:
- `name` (string, required) - Unique name for the sound
- `default_volume` (float, 0.0-1.0, optional) - Default: 0.5
- `is_random` (checkbox, optional) - Present for a multi-clip random asset; absent for single-clip
- For single-clip: `url` (string) - Audio URL
- For multi-clip: `clip_url[]`, `clip_volume[]`, `clip_chance[]` (parallel lists, one entry per clip)
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/library`

**Example (single-clip)**:
```bash
curl -X POST -b cookies.txt \
  -F "name=Meow Sound" \
  -F "default_volume=0.7" \
  -F "url=https://example.com/meow.ogg" \
  -F "csrf=<token>" \
  http://localhost:8000/library
```

**Example (multi-clip random)**:
```bash
curl -X POST -b cookies.txt \
  -F "name=Groan Sounds" \
  -F "default_volume=0.6" \
  -F "is_random=on" \
  -F "clip_url=https://example.com/groan1.ogg" \
  -F "clip_volume=1.0" \
  -F "clip_chance=50%" \
  -F "clip_url=https://example.com/groan2.ogg" \
  -F "clip_volume=0.8" \
  -F "clip_chance=50%" \
  -F "csrf=<token>" \
  http://localhost:8000/library
```

**Validation**:
- `name` must be unique across the library
- At least one clip URL required for random assets
- Single assets require `url`

**Errors**:
- Flash error on validation failure (redirect, not 4xx)

---

#### `POST /library/{sound_id}/add`

Wire a library sound to one of the user's channels as a new trigger.

**Auth**: Required (owner of target channel, or admin)

**Path Parameters**:
- `sound_id` (integer) - Library Sound ID

**Form Parameters**:
- `channel_id` (integer, required) - Target channel ID
- `trigger_word` (string, required) - Trigger word for the new entry
- `csrf` (string, required) - CSRF protection

**Response**: 302 Redirect to `/library`

**Validation**:
- `trigger_word` must be unique within the channel
- User must own the channel or be admin

**Errors**:
- 403: Not owner or admin
- 404: Sound or channel not found

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "channel_id=3" \
  -F "trigger_word=meow" \
  -F "csrf=<token>" \
  http://localhost:8000/library/42/add
```

---

### Dashboard Endpoints

#### `POST /self-register`

Create a channel for the current user using their Twitch login as the slug. Only available when `ALLOW_SELF_REGISTER=true` and the user has no channels yet.

**Auth**: Required

**Form Parameters**:
- `csrf` (string, required) - CSRF protection

**Response**: 302 Redirect to `/`

**Errors**:
- 403: Self-registration disabled (`ALLOW_SELF_REGISTER=false`)
- 409 (flash): Channel with that slug already exists

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "csrf=<token>" \
  http://localhost:8000/self-register
```

---

### Admin Endpoints

#### `GET /admin`

Admin panel for managing channels and users.

**Auth**: Required (admin only)

**Response**: HTML page with:
- List of all users with admin toggle
- List of all channels with owner assignment
- Create channel form
- Refresh avatars button

**Errors**:
- 403: User is not admin

**Example**:
```bash
curl -b cookies.txt http://localhost:8000/admin
```

---

#### `POST /admin/channel/create`

Create a new channel.

**Auth**: Required (admin only)

**Form Parameters**:
- `slug` (string, required) - Unique channel slug (lowercased)
- `display_name` (string, optional) - Display name; defaults to slug
- `owner_login` (string, optional) - Twitch login of owner to assign
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "slug=newstreamer" \
  -F "display_name=New Streamer" \
  -F "owner_login=newstreamer" \
  -F "csrf=<token>" \
  http://localhost:8000/admin/channel/create
```

---

#### `POST /admin/channel/<slug>/assign`

Assign (or unassign) a channel owner.

**Auth**: Required (admin only)

**Path Parameters**:
- `slug` (string) - Channel slug

**Form Parameters**:
- `owner_login` (string, optional) - Twitch login of new owner; blank to unassign
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "owner_login=someuser" \
  -F "csrf=<token>" \
  http://localhost:8000/admin/channel/newstreamer/assign
```

---

#### `POST /admin/channel/<slug>/delete`

Delete a channel and all its triggers.

**Auth**: Required (admin only)

**Path Parameters**:
- `slug` (string) - Channel slug

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

---

#### `POST /admin/user/<login>/toggle-admin`

Grant or revoke admin flag for a user.

**Auth**: Required (admin only)

**Path Parameters**:
- `login` (string) - Twitch login of target user

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Notes**:
- Admins cannot demote themselves

**Response**: 302 Redirect to `/admin`

---

#### `POST /admin/refresh-avatars`

Fetch current Twitch avatars for all channels using app credentials.

**Auth**: Required (admin only)

**Form Parameters**:
- `csrf` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

**Notes**:
- Calls Twitch helix/users in batches of 100
- Updates `avatar_url` on all matching channels

---

### Public JSON Endpoints

These endpoints are **public and unauthenticated**. They generate JSON from the database.

#### `GET /lists/index.json`

Index mapping channel slugs to their JSON files.

**Auth**: Not required

**Response**: JSON
```json
{
  "Amedoll": "lists/Amedoll.json",
  "RadiantSoul_Tv": "lists/RadiantSoul_Tv.json",
  "RadiantSoul_Tv_Sub": "lists/RadiantSoul_Tv_SubSounds.json"
}
```

**Content-Type**: `application/json`

**Example**:
```bash
curl http://localhost:8000/lists/index.json
```

**Notes**:
- Only includes channels with an assigned owner
- Used by the public board to discover channels
- Key order may vary; client must handle any order

---

#### `GET /lists/<slug>.json`

Sounds for a specific channel in legacy format.

**Auth**: Not required

**Path Parameters**:
- `slug` (string) - Channel slug

**Response**: JSON
```json
{
  "sounds": [
    {
      "trigger_word": "meow",
      "sound": "https://example.com/meow.ogg",
      "volume": 0.7,
      "chance": "100%",
      "trigger_cooldown": 0,
      "enabled": "true"
    },
    {
      "trigger_word": "groan",
      "sound": [
        "https://example.com/groan1.ogg",
        "https://example.com/groan2.ogg"
      ],
      "volume": 0.6,
      "chance": "100%",
      "trigger_cooldown": 5,
      "enabled": "true"
    }
  ]
}
```

**Content-Type**: `application/json`

**Status Codes**:
- 200: Success
- 404: Channel not found

**Example**:
```bash
curl http://localhost:8000/lists/Amedoll.json
```

**Important Format Rules**:
- `enabled` is always string "true" or "false", never boolean
- `chance` is always string with "%" suffix
- `sound` is string for single-clip, array of strings for multi-clip
- Never include additional fields

---

#### `GET /lists/internals/avatars.json`

Twitch avatars for channels.

**Auth**: Not required

**Response**: JSON
```json
{
  "Amedoll": "https://static-cdn.jtvnw.net/jtv_user_pictures/...",
  "RadiantSoul_Tv": "https://static-cdn.jtvnw.net/jtv_user_pictures/..."
}
```

**Content-Type**: `application/json`

**Example**:
```bash
curl http://localhost:8000/lists/internals/avatars.json
```

---

#### `GET /lists/internals/IconTriggers2.json`

Trigger word to icon/emote URL mappings.

**Auth**: Not required

**Response**: JSON
```json
{
  "meow": "https://cdn.example.com/icons/meow.png",
  "KEYS": "https://7tv.app/emotes/01GBRJBJMG000BS4BKZQQDARSQ"
}
```

**Content-Type**: `application/json`

**Notes**:
- Currently read-only (imported from legacy file)
- Admin UI for editing coming in future release

**Example**:
```bash
curl http://localhost:8000/lists/internals/IconTriggers2.json
```

---

### System Endpoints

#### `GET /healthz`

Health check endpoint for monitoring.

**Auth**: Not required

**Response**: JSON
```json
{"status": "ok"}
```

**Status Code**: 200 if healthy

**Example**:
```bash
curl http://localhost:8000/healthz
```

**Notes**:
- Used by load balancers and monitoring
- Does not check database connectivity
- Always returns 200 if server is running

---

#### `GET /api/docs`

Swagger UI API documentation (development only).

**Auth**: Not required in development; disabled in production

**Response**: HTML - Interactive API explorer

**Notes**:
- Available at `http://localhost:8000/api/docs` in dev
- Disabled when `IS_PRODUCTION=true`
- Use this to test endpoints interactively

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning | Cause |
|------|---------|-------|
| 200 | OK | Request succeeded |
| 302 | Found | Redirect (form submission) |
| 400 | Bad Request | Invalid input validation |
| 401 | Unauthorized | Missing or invalid session |
| 403 | Forbidden | User lacks permission |
| 404 | Not Found | Channel/sound/trigger doesn't exist |
| 409 | Conflict | Duplicate (trigger_word, sound name, etc.) |
| 500 | Internal Server Error | Server-side error |

### Example Error Response

```bash
curl http://localhost:8000/c/NonExistent

# HTTP/1.1 404 Not Found
# Content-Type: application/json
# {"detail":"not found"}
```

---

## CSRF Protection

All state-changing endpoints (POST) require CSRF tokens:

1. GET page to view form (token embedded in HTML)
2. Submit form with `csrf_token` field
3. Server validates token against session
4. Invalid token returns 400 Bad Request

The token is automatically included in all server-rendered forms via Jinja2 template.

---

## Rate Limiting

No built-in rate limiting currently. For production, consider:
- Add rate limiting middleware (e.g., slowapi)
- Limit per IP or per user
- Exceptions for static/public endpoints

---

## Pagination

Current implementation loads all records into memory. For large datasets:
- Library search results: load all sounds, filter client-side
- Channel triggers: load all per-channel (small number)

Future optimization: add limit/offset parameters.

---

## Webhooks

Not currently implemented. Future feature requests:
- Notify external services on channel changes
- Async sound asset validation

See [SETUP.md](SETUP.md) for environment configuration and [INTEGRATION.md](INTEGRATION.md) for how these endpoints interact with the database.
