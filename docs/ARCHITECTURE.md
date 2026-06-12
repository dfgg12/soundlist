# Soundlist - Architecture and Design Guide

Comprehensive overview of Soundlist's system design, module organization, and architectural decisions.

## Table of Contents

- [System Overview](#system-overview)
- [Module Organization](#module-organization)
- [Key Design Decisions](#key-design-decisions)
- [Data Model](#data-model)
- [Request Handling Pipeline](#request-handling-pipeline)
- [Security Architecture](#security-architecture)
- [Testing Architecture](#testing-architecture)
- [Deployment Architecture](#deployment-architecture)

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HTTP Client Layer                       │
│  - Web Browser (panel UI)                                   │
│  - Public Board (app.js)                                    │
│  - External API Consumers                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────v────────────────────────────────────────┐
│                   Nginx / Reverse Proxy                      │
│              (Production only, optional)                     │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────v────────────────────────────────────────┐
│                  FastAPI Application                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │        HTTP Routing & Middleware                      │ │
│  │  - SessionMiddleware (auth)                           │ │
│  │  - CORS middleware (if needed)                        │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Route Handlers                           │ │
│  │  - auth.py router                                     │ │
│  │  - lists.py router (public JSON)                      │ │
│  │  - panel.py router (channel editor)                   │ │
│  │  - library.py router (sound assets)                   │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │        Dependency Injection Layer                     │ │
│  │  - current_user (session-based)                       │ │
│  │  - require_channel_access (RBAC)                      │ │
│  │  - get_db (database session)                          │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────v────────────────────────────────────────┐
│              Business Logic Layer                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  db.py - Database operations                          │ │
│  │  serializer.py - JSON format enforcement              │ │
│  │  auth.py - Twitch OAuth, session mgmt                 │ │
│  │  csrf.py - CSRF token generation/validation           │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────v────────────────────────────────────────┐
│               Data Access Layer                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  SQLModel ORM                                         │ │
│  │  - models.py (SQLModel definitions)                   │ │
│  │  - Relationships between entities                     │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────v────────────────────────────────────────┐
│                  SQLite Database                            │
│  - user, channel, sound, soundclip, channelsound tables    │
└─────────────────────────────────────────────────────────────┘
```

### Information Flow

1. **Request Arrival**: HTTP request with session cookie
2. **Middleware Processing**: SessionMiddleware extracts user_id
3. **Route Matching**: FastAPI dispatches to appropriate router
4. **Dependency Resolution**: Load current_user, validate permissions
5. **Handler Execution**: Business logic queries/updates database
6. **Response Generation**: Serialize data (JSON or HTML)
7. **Response Delivery**: Send to client

## Module Organization

### Core Modules

```
app/
├── __init__.py              # Package marker
├── __main__.py              # Entry point (python -m app)
├── main.py                  # FastAPI app setup, lifespan
├── models.py                # SQLModel ORM definitions
├── db.py                    # Database initialization
├── settings.py              # Configuration from env
│
├── auth.py                  # Twitch OAuth, sessions, RBAC
├── csrf.py                  # CSRF token generation/validation
├── serializer.py            # JSON output formatting
│
├── lists.py                 # Public JSON endpoints
├── panel.py                 # Channel editor routes
├── library.py               # Sound library routes
│
├── flash.py                 # Flash message utilities
└── templates/               # Jinja2 templates (future)
    ├── base.html
    ├── dashboard.html
    ├── editor.html
    └── library.html

tests/
├── conftest.py              # Test fixtures, db setup
├── test_auth.py             # Authentication tests
├── test_importer.py         # JSON importer tests
├── test_library.py          # Library CRUD tests
├── test_panel.py            # Channel editor tests
├── test_parity.py           # JSON round-trip tests
└── test_serializer.py       # JSON format tests

scripts/
└── import_json.py           # Legacy JSON importer

docs/
├── SETUP.md                 # Installation & setup
├── INTEGRATION.md           # Component integration
├── API.md                   # Endpoint documentation
├── ARCHITECTURE.md          # This file
├── PLAN.md                  # High-level design
├── REQUIREMENTS.md          # Functional requirements
└── TASKLIST.md              # Implementation milestones
```

### Dependency Graph

```
main.py (entry point)
  |
  +-- SessionMiddleware
  +-- auth.py router
  +-- lists.py router
  +-- panel.py router
  +-- library.py router

auth.py
  +-- models.py (User, Channel, Sound)
  +-- db.py (database connection)
  +-- settings.py (config)
  +-- csrf.py (token management)

lists.py
  +-- models.py
  +-- serializer.py
  +-- db.py

panel.py
  +-- models.py
  +-- db.py
  +-- auth.py (RBAC guards)
  +-- csrf.py

library.py
  +-- models.py
  +-- db.py
  +-- auth.py (RBAC guards)
  +-- csrf.py

serializer.py
  +-- models.py

db.py
  +-- models.py
  +-- settings.py

No circular dependencies - acyclic graph
```

## Key Design Decisions

### 1. SQLite as Primary Storage

**Decision**: Use SQLite for local development and production (small scale).

**Rationale**:
- Single file database, no server setup needed
- Full ACID compliance
- Good performance for <100 channels
- Can migrate to PostgreSQL later without code changes

**Implications**:
- Lock contention under high concurrency (acceptable for this scale)
- No distributed transactions
- Backup is simple (copy file)

### 2. SQLModel + SQLAlchemy 2.0

**Decision**: Use SQLModel for ORM (SQLAlchemy 2.0 with Pydantic integration).

**Rationale**:
- Type hints throughout
- Pydantic validation on model creation
- Async support for future
- Relationships with lazy loading control

**Code**:
```python
class Channel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    owner_id: int | None = Field(foreign_key="user.id")
    owner: User | None = Relationship(back_populates="owned_channels")
```

### 3. Server-Rendered HTML, Not SPA

**Decision**: FastAPI + Jinja2 templates for panel UI; minimal vanilla JS.

**Rationale**:
- Faster development (no build chain)
- Easier to understand for new developers
- Session management automatic with forms
- Form validation on server

**Implications**:
- No real-time updates (refresh page)
- Form submissions are full POST (no AJAX)
- Good for internal admin tools

### 4. Public JSON is Generated, Not Stored

**Decision**: JSON output is dynamically generated from DB on every request.

**Rationale**:
- Always fresh - edit DB, JSON updates immediately
- Single source of truth (SQLite)
- No cache invalidation complexity
- Small dataset makes it fast

**Implications**:
- Slower on large datasets (acceptable here: ~25 channels, <100 sounds each)
- Every JSON request hits DB

**Future**: Add caching layer if needed.

### 5. Hard Contract on JSON Format

**Decision**: Enforce exact JSON shape via serializer module.

**Rationale**:
- Public board (app.js) consumes this without modification
- Legacy format has quirks (string "true", "100%" format)
- Round-trip parity required (import then export equals input)

**Enforcement**:
- Single `serialize_channel_sound()` function in serializer.py
- Unit tests verify exact format
- Parity test compares original JSON to exported JSON

### 6. RBAC via Dependencies

**Decision**: Use FastAPI dependency injection for authorization checks.

**Rationale**:
- Declarative (readable at endpoint definition)
- Reusable across endpoints
- Testable independently

**Code**:
```python
@app.get("/c/{slug}")
async def channel_editor(
    slug: str,
    current_user = Depends(require_auth),
    channel = Depends(require_channel_access(slug)),
):
    # Handler code here
    # Both dependencies are validated before this runs
```

### 7. Signed Session Cookies, Not JWT

**Decision**: Use Starlette SessionMiddleware with signed cookies.

**Rationale**:
- Session state in cookie (no server state needed)
- Signed to prevent tampering
- HTTP-only flag (CSRF safe)
- Built into Starlette

**Implications**:
- User data loaded from DB on every request (not in token)
- Token expiry is max_age (7 days)
- Logout just clears the cookie

### 8. Twitch OAuth, Not Local Auth

**Decision**: Twitch OAuth Authorization Code flow; no local passwords.

**Rationale**:
- Simplest for streamers (use Twitch login)
- No password storage/reset needed
- Twitch provides user profile (avatar, display name)
- Per-user channel ownership via Twitch ID

**Flow**:
1. User clicks "Login with Twitch"
2. Redirected to Twitch for authorization
3. Twitch redirects back with code
4. App exchanges code for access token
5. App fetches user info (twitch_id, login, etc.)
6. Create/update User record
7. Attempt channel claim (if Channel.slug.lower() == User.login)

### 9. Channels Claimed by Slug Matching

**Decision**: Channels are claimed by matching URL slug to Twitch login.

**Rationale**:
- No Twitch ID stored on Channel at import time
- Slug (from JSON filename) matches streamer login
- On login, auto-claim any channels where slug.lower() == login
- Admin can reassign manually if login changes

**Limitations**:
- If streamer renames Twitch account, slug doesn't auto-update
- Workaround: admin reassignment (M6/T6.1)

### 10. CSRF Protection on All Forms

**Decision**: All POST forms include CSRF token.

**Rationale**:
- Prevent cross-site request forgery
- Standard web security practice

**Implementation**:
```python
# In handler
csrf_token = generate_csrf_token(request)

# In template
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">

# On POST
csrf.verify_token(request, form_data.csrf_token)
```

## Data Model

### Entity Relationship Diagram

```
User (1)
  |
  +-- is_owner_of --> Channel (Many)
  |
  +-- creates --> Sound (Many)

Channel (1)
  |
  +-- has --> ChannelSound (Many)
              |
              +-- links_to --> Sound (1)

Sound (1)
  |
  +-- has --> SoundClip (Many, only if is_random=True)
```

### Key Constraints

- `User.twitch_id` - Unique, indexed (OAuth identity)
- `User.login` - Unique, indexed (Twitch login, lowercase)
- `Channel.slug` - Unique, indexed (URL key)
- `Sound.name` - Unique, indexed (library asset name)
- `ChannelSound.unique(channel_id, trigger_word)` - Composite unique (one trigger word per channel)

### Field Defaults

| Entity | Field | Default | Notes |
|--------|-------|---------|-------|
| User | is_admin | False | Must be explicitly granted |
| Channel | owner_id | None | Nullable until claimed via OAuth |
| Channel | is_sub_board | False | Sub-boards (e.g., _Sub suffix) |
| Sound | default_volume | 0.5 | Used if ChannelSound.volume is None |
| Sound | is_random | False | True means use SoundClip rows |
| ChannelSound | volume | None | If None, inherit Sound.default_volume |
| ChannelSound | chance | "100%" | Can be overridden per-trigger |
| ChannelSound | trigger_cooldown | 0 | No cooldown by default |
| ChannelSound | enabled | True | Triggers enabled by default |

## Request Handling Pipeline

### Typical Request Lifecycle

```
1. HTTP Request arrives at FastAPI
   GET /c/Amedoll/sound/42/toggle

2. SessionMiddleware processes
   Extracts user_id from signed cookie
   Stores in request.session["user_id"]

3. Route matches
   Handler: async def toggle_sound(
       slug: str,
       sound_id: int,
       current_user = Depends(require_auth),
       channel = Depends(require_channel_access(slug))
   )

4. Dependency resolution
   a) Depends(require_auth)
      - Load User by ID from DB
      - If not found, raise 401
   
   b) Depends(require_channel_access(slug))
      - Load Channel by slug from DB
      - Check: channel.owner_id == user.id OR user.is_admin
      - If not, raise 403
   
   c) Variables: slug, sound_id, current_user, channel

5. Handler executes
   cs = db.query(ChannelSound)\
     .filter_by(id=sound_id, channel_id=channel.id)\
     .first()
   cs.enabled = not cs.enabled
   db.commit()

6. Response generation
   Return {"enabled": cs.enabled}

7. FastAPI JSON serializes and sends
   Content-Type: application/json
   {"enabled": true}
```

### Exception Handling

```
Handler raises HTTPException(status_code=403)
  |
  v
FastAPI catches exception
  |
  v
Serialize to JSON: {"detail": "forbidden"}
  |
  v
Return 403 with JSON body
```

## Security Architecture

### Authentication

1. **Twitch OAuth** - User identity
2. **Signed Session Cookie** - Session state
3. **Per-Request User Load** - Freshness

### Authorization (RBAC)

```
User Model
  is_admin: bool

Channel Model
  owner_id: FK -> User.id

Permission Rules:
- Admin can: read/write all channels and library
- Streamer can: read/write only owned channels
- Public can: read JSON endpoints only

Enforcement:
- Every protected endpoint has require_auth or require_channel_access
- No permission checks in business logic (all at endpoint level)
```

### CSRF Protection

```
GET /c/<slug>
  |
  v
Generate CSRF token
Include in form as <input type="hidden" name="csrf_token">

POST /c/<slug>/sound
  |
  v
Extract csrf_token from request
Verify against session
If invalid, reject with 400
```

### Secrets Management

```
Required Secrets (from environment):
- TWITCH_CLIENT_SECRET - Never logged
- SESSION_SECRET_KEY - Never logged

In code:
- All loaded via settings.py
- Never hardcoded
- Settings class uses SecretStr from Pydantic
- .env file in .gitignore
```

### SQL Injection Prevention

```
All database queries use SQLAlchemy/SQLModel
Parameterized queries prevent injection

Example:
# SAFE: parameterized
channel = db.query(Channel).filter_by(slug=slug).first()

# UNSAFE: string interpolation (NOT in codebase)
# query(f"SELECT * FROM channel WHERE slug = '{slug}'")
```

### Static File Serving

```
Public board assets are served from the project root via an explicit
allowlist, NOT a directory mount:

_PUBLIC_FILES = {index.html, styles.css, app.js, marquee.html}

GET /<filename>
  |
  v
If filename not in _PUBLIC_FILES -> 404
Else -> FileResponse(root / filename)

Rationale:
- Mounting the whole project root (StaticFiles(directory=root)) would
  expose .env, soundlist.db, .git/, uv.lock, and all app/ source over
  HTTP. The allowlist keeps only the four board files reachable.
- The single-segment route /<filename> is registered after all API
  routers and after /healthz, so it never shadows them; it also cannot
  match slashed paths (lists/*.json stays with the lists router).
- Regression coverage: tests/test_static.py asserts the board files
  return 200 and that secrets/source return 404.
```

## Testing Architecture

### Test Structure

```
tests/
├── conftest.py
│   ├── db_session fixture
│   │   Creates in-memory SQLite
│   │   Populates with sample data
│   │   Cleans up after each test
│   │
│   └── app_client fixture
│       TestClient with test database
│
├── test_auth.py
│   - OAuth redirect
│   - Session creation
│   - User lookup
│
├── test_library.py
│   - Sound CRUD
│   - Multi-clip handling
│   - Validation
│
├── test_panel.py
│   - Channel editor endpoints
│   - Permission checks
│   - Trigger CRUD
│
├── test_serializer.py
│   - JSON format enforcement
│   - Legacy format rules
│
└── test_parity.py
    - Import then export equals original
```

### Test Database Setup

```python
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Populate test data
        user = User(twitch_id="123", login="testuser")
        session.add(user)
        session.commit()
        
        yield session
    
    SQLModel.metadata.drop_all(engine)
```

### Test Client

```python
@pytest.fixture
def client(db_session):
    def get_session():
        return db_session
    
    app.dependency_overrides[get_session] = get_session
    
    yield TestClient(app)
    
    app.dependency_overrides.clear()
```

## Deployment Architecture

### Development

```
Developer's Machine
  |
  +-- app source code
  +-- .env (local secrets)
  +-- soundlist.db (SQLite)
  |
  +-- uv run soundlist
      |
      +-- uvicorn on localhost:8000
      +-- auto-reload on code change
```

### Production

```
Internet
  |
  v
TLS Termination (acme.sh certificate)
  |
  v
Reverse Proxy (Nginx)
  | - Route / and /lists/* to backend
  | - Route /api/docs to 403 (internal only)
  |
  v
Systemd Service (soundlist)
  | - Runs: uv run soundlist
  | - Restart on failure
  | - User: www-data
  |
  v
FastAPI (uvicorn)
  | - IS_PRODUCTION=true
  | - DATABASE_URL=postgresql://...
  | - SESSION_SECRET_KEY=<random>
  |
  v
PostgreSQL Database (or SQLite + rsync backup)
```

### Configuration Management

```
Environment Variables (systemd service or cloud platform):
- TWITCH_CLIENT_ID
- TWITCH_CLIENT_SECRET
- SESSION_SECRET_KEY
- IS_PRODUCTION
- DATABASE_URL
- ADMIN_LOGINS

File-based config:
- None (all config via environment)

Secrets:
- Never in git
- Never in docker images
- Passed at runtime via environment
```

### Monitoring

```
Health Check:
- GET /healthz returns {"status": "ok"}
- Used by load balancer to detect failures
- Does not check DB connectivity

Logging:
- Structured logs with [INFO]/[WARN]/[ERROR] prefixes
- Output to stdout (captured by systemd journal)
- Future: send to logging aggregator

Metrics:
- Not currently collected
- Future: Prometheus endpoint
```

See [SETUP.md](SETUP.md) for deployment instructions and [API.md](API.md) for endpoint contracts.
