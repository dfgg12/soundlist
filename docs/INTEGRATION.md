# Soundlist - Component Integration Guide

This document explains how different components of the Soundlist application integrate with each other.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Request Flow](#request-flow)
- [Authentication Flow](#authentication-flow)
- [Data Layer Integration](#data-layer-integration)
- [JSON Output Generation](#json-output-generation)
- [Frontend Integration](#frontend-integration)
- [Admin Panel Integration](#admin-panel-integration)

## Architecture Overview

Soundlist follows a layered architecture:

```
HTTP Request
     |
     v
FastAPI Application (app/main.py)
     |
     +-- Routers (auth, lists, panel, library)
     |
     v
Request Handlers / Endpoints
     |
     +-- Dependency Injection (auth guard, session)
     |
     v
Business Logic (db, serializer, etc.)
     |
     +-- Database Layer (SQLModel / SQLAlchemy)
     |
     v
SQLite Database
     |
     +-- User, Channel, Sound, SoundClip, ChannelSound tables
```

### Key Layers

1. **Application Layer** (`main.py`)
   - FastAPI app setup
   - Middleware registration (sessions, logging)
   - Lifespan management (startup/shutdown)
   - Router mounting

2. **HTTP Layer** (routers)
   - `auth.py` - Authentication endpoints
   - `lists.py` - JSON output endpoints (public)
   - `panel.py` - Management UI endpoints (protected)
   - `library.py` - Sound library endpoints (protected)

3. **Dependency Layer** (`auth.py`, `csrf.py`)
   - Session authentication
   - RBAC guards
   - CSRF token validation

4. **Business Logic** (`db.py`, `serializer.py`)
   - Database operations
   - JSON format enforcement
   - Data transformation

5. **Data Layer** (`models.py`, database)
   - SQLModel ORM definitions
   - SQLite schema
   - Relationships

## Request Flow

### Typical Authenticated Request

```
1. HTTP POST /c/MyChannel/sound
   Headers: Cookie with session_id

2. FastAPI receives request
   |
   v

3. SessionMiddleware extracts session
   |
   v

4. Route handler calls current_user dependency
   |
   v

5. current_user loads User from database
   If session invalid -> 401 Unauthorized

6. Route handler calls require_channel_access(slug) dependency
   |
   v

7. Channel loaded and ownership checked
   If user not owner and not admin -> 403 Forbidden

8. Handler executes business logic
   - Validates input
   - Updates database
   - Returns response

9. Response sent to client
```

### Public JSON Endpoint Request

```
1. HTTP GET /lists/MyChannel.json
   (No authentication required)

2. Route handler in lists.py
   |
   v

3. Load Channel by slug
   If not found -> 404

4. Query all ChannelSound records for channel
   Ordered by position

5. Serialize each ChannelSound
   - Via serializer.py
   - Enforces legacy JSON format
   - Converts boolean -> "true"/"false"
   - Ensures sound field is string or array

6. Return {"sounds": [...]}
   Content-Type: application/json
```

## Authentication Flow

### Twitch OAuth Login

```
1. User clicks "Login with Twitch"

2. GET /login
   |
   Redirects to Twitch OAuth authorization URL
   |
   https://id.twitch.tv/oauth2/authorize
     ?client_id=...
     &redirect_uri=http://localhost:8000/auth/callback
     &response_type=code
     &scope=user:read:email

3. User logs in at Twitch
   Grants permission
   Redirects back to /auth/callback?code=...

4. GET /auth/callback?code=...
   |
   Backend exchanges code for token
   | (via authlib)
   |
   Backend fetches user info from Twitch API
   | (twitch_id, login, display_name, avatar)
   |
   Database lookup: User.twitch_id == twitch_id
   |
   If not exists:
     Create new User
     Attempt channel claim (Channel.slug.lower() == login)
   |
   If exists:
     Load existing User
     Update avatar/display_name
   |
   Create session
   Set signed session cookie
   Redirect to / (dashboard)

5. GET / (with valid session cookie)
   |
   current_user dependency loads User from session
   |
   Show dashboard with user's channels
```

### Session Persistence

- **Storage**: Signed cookie (`soundlist_session`)
- **Signing**: Uses `SESSION_SECRET_KEY` from environment
- **Expiry**: 7 days of inactivity
- **Secure Flags**: `https_only=True` in production, `same_site="lax"`

### Logout

```
GET /logout
 |
 v
Clear session cookie
 |
 v
Redirect to / (shows login button)
```

## Data Layer Integration

### Database Initialization

On application startup (`lifespan` in `main.py`):

```python
create_db_and_tables()
  |
  v
SQLModel.metadata.create_all(engine)
  |
  v
SQLAlchemy creates tables for all SQLModel classes
  - user
  - channel
  - sound
  - soundclip
  - channelsound
```

### Key Relationships

```
User (1)
  |
  +-- owns --> Channel (Many)
  |              |
  |              +-- has --> ChannelSound (Many)
  |                           |
  |                           +-- links to --> Sound (1)
  |
  +-- creates --> Sound (Many)
                   |
                   +-- has --> SoundClip (Many, if is_random)
```

### Entity Interactions

#### When Creating a Channel Trigger

```
1. User submits form:
   trigger_word, sound_id (existing), volume, chance, cooldown

2. Validation:
   - Channel.owner_id == current_user.id or is_admin
   - Sound.id exists
   - trigger_word unique per channel (unique constraint)

3. Create ChannelSound:
   - channel_id = <channel.id>
   - sound_id = <sound.id>
   - trigger_word = <from form>
   - volume = <from form> (or None to inherit Sound.default_volume)
   - chance = <from form> (or "100%")
   - trigger_cooldown = <from form> (or 0)
   - enabled = True (default)
   - position = <next seq number>

4. Save to database

5. Redirect to channel editor
```

#### When Editing a Shared Sound Asset

```
1. Admin edits Sound.url (or SoundClip.url)

2. Update in database

3. All ChannelSound records linking this Sound.id
   automatically reflect the change
   (no per-channel update needed)

4. Next time any channel's JSON is fetched:
   - Serializer reads Sound.url
   - Returns new URL in response
   - Public board automatically plays new clip
```

#### When Importing Legacy JSON

```
1. Script reads lists/*.json files

2. For each file:
   a. Create Channel (if not exists)
      slug = filename
      display_name = filename
      owner_id = None (unclaimed)

   b. For each trigger in sounds array:
      - Lookup Sound by name (trigger_word)
      - If not exists: create Sound
      - Create ChannelSound linking Channel to Sound

3. Data round-trips perfectly:
   - Fetch /lists/<slug>.json
   - Format matches original JSON
```

## JSON Output Generation

### Serializer (`app/serializer.py`)

The serializer is the single source of truth for JSON format. It enforces:

```python
def serialize_channel_sound(cs: ChannelSound) -> dict:
    """Convert ChannelSound to JSON trigger object."""
    
    # Get the Sound asset
    sound = cs.sound
    
    # Determine 'sound' field value
    if sound.is_random:
        # Multi-clip: array of URLs
        sound_field = [clip.url for clip in sound.clips]
    else:
        # Single-clip: plain string
        sound_field = sound.url
    
    # Resolve volume (per-channel override or default)
    volume = cs.volume if cs.volume is not None else sound.default_volume
    
    # Convert to legacy JSON format
    return {
        "trigger_word": cs.trigger_word,
        "sound": sound_field,
        "volume": float(volume),
        "chance": cs.chance,  # Already formatted as "100%"
        "trigger_cooldown": cs.trigger_cooldown,
        "enabled": "true" if cs.enabled else "false",  # String, not bool
    }
```

### Four Public Endpoints

All generate JSON from the database:

#### 1. GET /lists/index.json

```python
def index_json():
    """Map channel slug to its JSON path."""
    channels = db.query(Channel).all()
    return {
        "Amedoll": "lists/Amedoll.json",
        "RadiantSoul_Tv": "lists/RadiantSoul_Tv.json",
        # ...
    }
```

#### 2. GET /lists/<slug>.json

```python
def channel_json(slug):
    """Fetch all triggers for a channel."""
    channel = db.query(Channel).filter_by(slug=slug).first()
    if not channel:
        return 404 {"detail": "not found"}
    
    sounds = []
    for cs in channel.channel_sounds:
        sounds.append(serialize_channel_sound(cs))
    
    return {"sounds": sounds}
```

#### 3. GET /lists/internals/avatars.json

```python
def avatars_json():
    """Map channel slug to Twitch avatar URL."""
    channels = db.query(Channel).all()
    return {
        "Amedoll": "https://static-cdn.jtvnw.net/...",
        # ...
    }
```

#### 4. GET /lists/internals/IconTriggers2.json

```python
def icon_triggers_json():
    """Map trigger_word to image/7tv URL."""
    # This is imported from legacy file, read-only for now
    # Future: admin UI to edit
    return {...}
```

### Format Contract

**Non-negotiable rules** (enforced in serializer):

| Field | Type | Example | Rule |
|-------|------|---------|------|
| `trigger_word` | string | "meow" | UTF-8, any length |
| `sound` | string or array | "https://..." or ["...", "..."] | String for single-clip, array for multi |
| `volume` | float | 0.4 | 0.0 to 1.0 |
| `chance` | string | "100%" | Must have "%" suffix |
| `trigger_cooldown` | integer | 5 | Non-negative seconds |
| `enabled` | string | "true" or "false" | **String, never boolean** |

## Frontend Integration

### Public Board (app.js)

The existing public board (`app.js`, `index.html`) depends on the JSON contract:

```javascript
// app.js loads the channel list
fetch('/lists/index.json')
  .then(r => r.json())
  .then(index => {
    // index = { "ChannelSlug": "lists/ChannelSlug.json", ... }
    // Iterate and load each channel's sounds
    for (const [slug, path] of Object.entries(index)) {
      fetch(`/${path}`)
        .then(r => r.json())
        .then(data => {
          // data = { "sounds": [...] }
          // Render triggers, set up audio players
        })
    }
  })
```

**Key dependency**: The JSON output must exactly match the shape above.

### Management UI (Panel)

Server-rendered Jinja2 templates in `app/templates/`:

```
GET /
  |
  v
Render dashboard.html (Jinja2)
  - List channels user owns
  - Links to /c/<slug>

GET /c/<slug>
  |
  v
Render editor.html (Jinja2)
  - Table of current triggers
  - Form to add trigger
  - Form to edit each trigger
  - Delete buttons

POST /c/<slug>/sound
  |
  v
Create ChannelSound
  |
  v
Redirect to GET /c/<slug>
  |
  v
Re-render with new trigger in table
```

### Test Player (Vanilla JS)

In-browser audio player for testing sounds before save:

```html
<button onclick="testSound('https://example.com/sound.ogg', 0.5)">
  Play
</button>

<script>
function testSound(url, volume) {
  const audio = new Audio();
  audio.src = url;
  audio.volume = volume;
  audio.play();
}
</script>
```

## Admin Panel Integration

### Admin-Only Routes

```
GET /admin
  -> List all channels
  -> Show owner assignments
  -> Grant/revoke admin status

POST /admin/channel
  -> Create new channel
  -> Set owner
  -> Set as sub-board

POST /admin/channel/<id>/owner
  -> Reassign channel owner

POST /admin/user/<id>/admin
  -> Grant/revoke admin privileges
```

### RBAC Guards

Every protected endpoint uses a dependency:

```python
@app.get("/c/{slug}")
async def channel_editor(
    slug: str,
    current_user = Depends(require_auth),
    channel = Depends(require_channel_access(slug)),
):
    """Only owner or admin can edit."""
    return channel
```

**Current user** dependency:

```python
async def require_auth(request: Request) -> User:
    """Load user from session; 401 if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    return db.query(User).get(user_id)
```

**Channel access** dependency:

```python
async def require_channel_access(slug: str):
    def inner(current_user: User, request: Request) -> Channel:
        """Load channel; 403 if user has no permission."""
        channel = db.query(Channel).filter_by(slug=slug).first()
        if not channel:
            raise HTTPException(status_code=404)
        
        is_owner = channel.owner_id == current_user.id
        is_admin = current_user.is_admin
        
        if not (is_owner or is_admin):
            raise HTTPException(status_code=403)
        
        return channel
    return inner
```

## Testing Integrations

### Test Setup

Each test uses a temporary in-memory SQLite database:

```python
# conftest.py
@pytest.fixture
def db_session():
    """Create temporary test database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
```

### Integration Tests

```python
def test_create_sound_and_link_to_channel():
    """Verify Sound -> ChannelSound linking."""
    
    # Setup
    user = User(twitch_id="123", login="testuser")
    channel = Channel(slug="TestUser", owner_id=user.id)
    sound = Sound(name="test_sound", url="https://example.com/sound.ogg")
    
    # Action
    cs = ChannelSound(
        channel_id=channel.id,
        sound_id=sound.id,
        trigger_word="meow"
    )
    
    # Verify
    assert cs.sound == sound
    assert cs.channel == channel
    
    # Serialize and check JSON
    json_out = serialize_channel_sound(cs)
    assert json_out["trigger_word"] == "meow"
    assert json_out["sound"] == "https://example.com/sound.ogg"
```

See [REQUIREMENTS.md](REQUIREMENTS.md) for the complete JSON contract and [SETUP.md](SETUP.md) for running tests.
