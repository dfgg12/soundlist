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
- Table of current triggers
- Form to add new trigger
- Edit/delete buttons for each trigger
- Test button to play sounds

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
- `sound_id` (integer, optional) - Link to existing library Sound
- `sound_url` (string, optional) - Create new single-clip Sound
- `sound_name` (string, optional) - Name for new Sound
- `volume` (float, 0.0-1.0, optional) - Default: Sound.default_volume
- `chance` (string, optional) - Probability, e.g. "50%". Default: "100%"
- `trigger_cooldown` (integer, optional) - Seconds between triggers. Default: 0
- `csrf_token` (string, required) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "trigger_word=meow" \
  -F "sound_url=https://example.com/meow.ogg" \
  -F "sound_name=Meow Sound" \
  -F "volume=0.7" \
  -F "csrf_token=<token>" \
  http://localhost:8000/c/Amedoll/sound
```

**Validation**:
- `trigger_word` must be unique per channel
- Must provide either `sound_id` (existing) or both `sound_url` and `sound_name`
- `volume` must be 0.0-1.0
- `chance` must match pattern /^\d+%$/
- `trigger_cooldown` must be non-negative

**Errors**:
- 400: Validation error
- 401: Not authenticated
- 403: Not owner or admin
- 409: Duplicate trigger_word for this channel

---

#### `POST /c/<slug>/sound/<id>`

Edit an existing trigger.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug
- `id` (integer) - ChannelSound ID

**Form Parameters**:
- `trigger_word` (string) - Updated trigger word
- `volume` (float, 0.0-1.0) - Updated volume
- `chance` (string) - Updated probability, e.g. "50%"
- `trigger_cooldown` (integer) - Updated cooldown
- `enabled` (checkbox) - "on" if enabled, absent if disabled
- `csrf_token` (string) - CSRF protection

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
  -F "csrf_token=<token>" \
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
- `csrf_token` (string) - CSRF protection

**Response**: 302 Redirect to `/c/<slug>`

**Notes**:
- Only removes the channel trigger
- Does not delete the underlying Sound asset
- Sound remains available for other channels

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "csrf_token=<token>" \
  http://localhost:8000/c/Amedoll/sound/123/delete
```

---

#### `POST /c/<slug>/sound/<id>/toggle`

Toggle enabled status without full edit.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug
- `id` (integer) - ChannelSound ID

**Response**: JSON
```json
{"enabled": true}
```

**Example**:
```bash
curl -X POST -b cookies.txt \
  http://localhost:8000/c/Amedoll/sound/123/toggle
# Returns: {"enabled": false}
```

---

#### `GET /c/<slug>/test`

Testing and preview view for a channel.

**Auth**: Required (owner or admin)

**Path Parameters**:
- `slug` (string) - Channel slug

**Response**: HTML page with:
- List of all triggers
- Play buttons for testing sounds
- Live preview of generated JSON
- Volume slider for testing

**Example**:
```bash
curl -b cookies.txt http://localhost:8000/c/Amedoll/test
# Returns: HTML test page
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
- `sound_type` (string, required) - "single" or "multi"
- For single-clip: `url` (string) - Audio URL
- For multi-clip: `clips[0][url]`, `clips[0][volume]`, `clips[0][chance]`, etc.
- `csrf_token` (string) - CSRF protection

**Response**: 302 Redirect to `/library`

**Example (single-clip)**:
```bash
curl -X POST -b cookies.txt \
  -F "name=Meow Sound" \
  -F "default_volume=0.7" \
  -F "sound_type=single" \
  -F "url=https://example.com/meow.ogg" \
  -F "csrf_token=<token>" \
  http://localhost:8000/library
```

**Example (multi-clip)**:
```bash
curl -X POST -b cookies.txt \
  -F "name=Groan Sounds" \
  -F "default_volume=0.6" \
  -F "sound_type=multi" \
  -F "clips[0][url]=https://example.com/groan1.ogg" \
  -F "clips[0][volume]=1.0" \
  -F "clips[0][chance]=50%" \
  -F "clips[1][url]=https://example.com/groan2.ogg" \
  -F "clips[1][volume]=0.8" \
  -F "clips[1][chance]=50%" \
  -F "csrf_token=<token>" \
  http://localhost:8000/library
```

**Validation**:
- `name` must be unique
- At least one clip required for multi-clip
- All clips need URL and chance

**Errors**:
- 400: Validation error
- 409: Sound name already exists

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
- List of all channels
- Owner assignment controls
- Admin toggle switches for users
- Create channel form

**Errors**:
- 403: User is not admin

**Example**:
```bash
curl -b cookies.txt http://localhost:8000/admin
```

---

#### `POST /admin/channel`

Create a new channel.

**Auth**: Required (admin only)

**Form Parameters**:
- `slug` (string, required) - Unique channel slug
- `display_name` (string, required) - Display name
- `owner_id` (integer, optional) - User ID to assign as owner
- `is_sub_board` (checkbox, optional) - "on" if sub-board
- `csrf_token` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

**Example**:
```bash
curl -X POST -b cookies.txt \
  -F "slug=NewStreamer" \
  -F "display_name=New Streamer" \
  -F "csrf_token=<token>" \
  http://localhost:8000/admin/channel
```

---

#### `POST /admin/channel/<id>/owner`

Reassign channel owner.

**Auth**: Required (admin only)

**Path Parameters**:
- `id` (integer) - Channel ID

**Form Parameters**:
- `owner_id` (integer, optional) - New owner User ID (or None to unassign)
- `csrf_token` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

---

#### `POST /admin/user/<id>/admin`

Grant or revoke admin privileges.

**Auth**: Required (admin only)

**Path Parameters**:
- `id` (integer) - User ID

**Form Parameters**:
- `is_admin` (checkbox, optional) - "on" to grant, absent to revoke
- `csrf_token` (string) - CSRF protection

**Response**: 302 Redirect to `/admin`

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
