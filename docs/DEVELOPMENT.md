# Soundlist - Development Guide

Guide for developers working on the Soundlist codebase.

## Table of Contents

- [Getting Started](#getting-started)
- [Code Organization](#code-organization)
- [Coding Standards](#coding-standards)
- [Common Development Tasks](#common-development-tasks)
- [Debugging](#debugging)
- [Git Workflow](#git-workflow)
- [Performance Considerations](#performance-considerations)

## Getting Started

### Prerequisites

Before starting development:

```bash
# 1. Python 3.11+
python --version

# 2. uv package manager
uv --version

# 3. Clone and setup
git clone <repository>
cd soundlist
uv sync

# 4. Copy environment
cp .env.example .env
# Edit .env with your Twitch credentials
```

### First Run

```bash
# Start the development server
uv run soundlist

# In another terminal, verify it's running
curl http://localhost:8000/healthz
# {"status":"ok"}

# Run tests to verify setup
uv run pytest -v

# Run linting
uv run ruff check app/ tests/
```

## Code Organization

### Module Responsibilities

#### `app/main.py`

- FastAPI application setup
- Middleware registration (sessions)
- Lifespan management (startup/shutdown)
- Router mounting

**Do not put**: Business logic, database operations

```python
# DO
@asynccontextmanager
async def lifespan(app):
    create_db_and_tables()
    yield
    # cleanup if needed

# DON'T
@asynccontextmanager
async def lifespan(app):
    # Don't query database here
    # Don't process requests here
```

#### `app/models.py`

- SQLModel ORM definitions
- Database schema
- Relationships
- Field constraints

**Do not put**: Business logic, HTTP handling, database queries

```python
# DO
class Sound(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    default_volume: float = 0.5

# DON'T
class Sound(SQLModel, table=True):
    @property
    def linked_count(self):  # This is computed logic, not schema
        ...
```

#### `app/auth.py`

- Twitch OAuth implementation
- Session management
- User authentication
- RBAC dependencies (`require_auth`, `require_channel_access`)

**Do not put**: JSON endpoints, library logic, admin panel logic

#### `app/db.py`

- Database connection/engine setup
- Schema initialization
- Database utilities

**Do not put**: Business logic, specific queries (put in routers)

#### `app/serializer.py`

- JSON output formatting
- Legacy format enforcement
- Data transformation for JSON

**Single responsibility**: Ensure JSON matches the contract exactly.

```python
def serialize_channel_sound(cs: ChannelSound) -> dict:
    """Convert DB model to JSON trigger object.
    
    Enforces exact format:
    - enabled as string "true"/"false"
    - chance as string with "%"
    - sound as string (single) or array (multi)
    """
```

#### `app/lists.py`, `app/panel.py`, `app/library.py`

- HTTP route handlers
- Request validation
- Response generation
- Dependency injection declarations

**Organization**: Group related endpoints

```python
# Good: related endpoints together
@router.get("/")
async def library(...):
    ...

@router.post("/")
async def create_sound(...):
    ...

# Separate routers by domain
# auth.py has auth endpoints
# lists.py has public JSON
# panel.py has channel editor
# library.py has sound library
```

### File Size Guidelines

- **Keep modules under 300 lines** (single responsibility)
- **Keep functions under 30 lines** (extract helpers)
- **Split large routers** into separate modules if >250 lines

### Import Organization

All imports must be at module level (top of file). Global imports required by CLAUDE.md:

```python
"""Module docstring."""

from __future__ import annotations

# Standard library
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

# Third-party
from fastapi import FastAPI, Depends
from sqlmodel import Session, select

# Local
from app.models import User, Channel
from app.auth import require_auth

if TYPE_CHECKING:
    from app.settings import Settings

# No local imports inside functions
# No circular imports
```

## Coding Standards

### Style Guide

- **PEP 8**: Full compliance (enforced by ruff)
- **Type hints**: Required on all functions and variables
- **Line length**: 79 characters max
- **Docstrings**: One line per function/class (what it does, not how)

### Type Hints

```python
# DO
def get_channel(slug: str) -> Channel | None:
    """Fetch channel by slug; None if not found."""
    return db.query(Channel).filter_by(slug=slug).first()

# DON'T
def get_channel(slug):  # Missing type hints
    """This function gets a channel."""  # Redundant docstring
    return db.query(Channel).filter_by(slug=slug).first()
```

### Function Docstrings

One sentence describing what the function does:

```python
# DO
def hash_password(plain: str) -> str:
    """Hash a password for secure storage."""

def parse_chance_percentage(chance: str) -> float:
    """Extract numeric percentage from string like '50%'."""

# DON'T
def hash_password(plain: str) -> str:
    """
    This function takes a plain text password and hashes it
    using the bcrypt algorithm with a salt. It returns the
    hashed value which can be stored in the database.
    """

# DON'T
def hash_password(plain: str) -> str:
    """Hashes plain."""  # Too terse, unclear
```

### Exception Handling

Catch specific exceptions only:

```python
# DO
try:
    user = db.query(User).get(user_id)
except NoResultFound:
    raise HTTPException(status_code=404)
except IntegrityError:
    raise HTTPException(status_code=409, detail="duplicate email")

# DON'T
try:
    user = db.query(User).get(user_id)
except:  # Never use bare except
    pass
```

### Error Messages

Use clear, actionable error messages:

```python
# DO
raise ValueError(f"chance must be 0-100%, got '{chance}'")
raise HTTPException(
    status_code=409,
    detail="trigger_word already exists for this channel"
)

# DON'T
raise ValueError("Invalid chance")
raise HTTPException(status_code=400, detail="Error")
```

### Comments

Minimal comments. Only add when the WHY is non-obvious:

```python
# DO - explains why, not what
# Store as string to preserve legacy format (e.g., "3.3%" not 0.033)
chance: str

# DO - explains a hidden constraint
# Must check enabled status here, not in serializer
# (serializer is also used for draft queries)
if not sound.enabled:
    continue

# DON'T - explains what the code does (obvious from reading)
# Increment counter
counter += 1

# DON'T - redundant
# Get the user (of course it gets the user)
user = db.query(User).get(user_id)
```

### Naming Conventions

```python
# Constants: UPPER_SNAKE_CASE
MAX_VOLUME = 1.0
DEFAULT_COOLDOWN = 0

# Functions/variables: lower_snake_case
def get_channel_by_slug(slug: str) -> Channel:
    pass

# Classes: PascalCase
class ChannelSound:
    pass

# Private/internal: leading underscore
def _serialize_sound_clip(clip: SoundClip) -> str:
    """Internal helper, not part of public API."""
    pass

# Boolean functions: is_*, has_*, can_*
def is_admin(user: User) -> bool:
    return user.is_admin

def has_channel_access(user: User, channel: Channel) -> bool:
    return channel.owner_id == user.id or user.is_admin

def can_edit_sound(user: User, sound: Sound) -> bool:
    return sound.created_by == user.id or user.is_admin
```

## Common Development Tasks

### Adding a New Endpoint

1. **Define the route** in the appropriate router (panel.py, library.py, etc.)
2. **Add dependencies** (require_auth, etc.)
3. **Implement handler** (query DB, transform data)
4. **Add tests** in tests/

```python
# Example: Add endpoint to library.py
@router.post("/library/{id}/publish")
async def publish_sound(
    id: int,
    current_user: User = Depends(require_auth),
):
    """Publish a sound to all channels."""
    sound = db.query(Sound).filter_by(id=id).first()
    if not sound:
        raise HTTPException(status_code=404)
    
    # Check permission (user created it or is admin)
    if sound.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403)
    
    # Business logic
    sound.published = True
    db.commit()
    
    return {"published": True}
```

### Adding a Database Field

1. **Update model** in models.py
2. **Create migration** (manual SQL or Alembic, future)
3. **Update serializer** if affects JSON
4. **Update tests** if affects validation

```python
# Example: Add enabled field to Channel
class Channel(SQLModel, table=True):
    # ... existing fields ...
    enabled: bool = True  # New field
    
# Test it
def test_channel_enabled_default():
    channel = Channel(slug="test")
    assert channel.enabled is True
```

### Fixing a Bug

1. **Write a failing test** that reproduces the bug
2. **Fix the code**
3. **Test passes**
4. **Verify no regressions** (run full test suite)

```bash
# Step 1: Write test
# tests/test_panel.py
def test_duplicate_trigger_word_rejected():
    # Create a channel with a trigger
    # Try to add another with same trigger_word
    # Expect 409 Conflict

# Step 2: Run test (fails)
uv run pytest tests/test_panel.py::test_duplicate_trigger_word_rejected

# Step 3: Fix code
# app/panel.py - validate trigger_word uniqueness

# Step 4: Run test (passes)
uv run pytest tests/test_panel.py::test_duplicate_trigger_word_rejected

# Step 5: Full suite
uv run pytest
```

### Refactoring Code

When refactoring:

1. **Preserve all functionality** (no feature changes)
2. **Run full test suite** before and after
3. **Keep commits atomic** (one refactor per commit)
4. **Use meaningful commit message**

```bash
# BAD refactor (multiple unrelated changes)
git add .
git commit -m "cleanup"

# GOOD refactor (focused)
git add app/serializer.py tests/test_serializer.py
git commit -m "refactor: consolidate sound clipping logic in serializer

Extracts repeated clip handling into _format_sound_field() helper.
Tests verify no behavior change."
```

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

log.debug(f"User attempting to access channel: {channel_id}")
log.info(f"Channel {channel_id} updated by user {user_id}")
log.warning(f"Sound asset not reachable: {url}")
log.error(f"Database commit failed: {exc}", exc_info=True)
```

### Using Print Statements

For quick debugging, use print but remove before commit:

```python
# Temporary debug print
print(f"DEBUG: channel={channel}, user={user}")

# Should be removed or converted to log
log.debug(f"Channel {channel.id} access by user {user.id}")
```

### Interactive Debugging

Using the Python debugger:

```python
import pdb

# In code where you want to inspect
pdb.set_trace()

# Then continue manually
# (c)ontinue, (n)ext line, (s)tep into function, (l)ist code
# (p <var>) print variable, (pp <var>) pretty print
```

Or use an IDE debugger:

- **VS Code**: Install Python extension, set breakpoints, F5 to debug
- **PyCharm**: Set breakpoints, Run > Debug

### Testing Database Queries

In pytest:

```python
def test_channel_queries(db_session):
    # Inspect database state
    channels = db_session.query(Channel).all()
    print(f"Total channels: {len(channels)}")
    
    # Verify relationships
    channel = channels[0]
    assert channel.owner is not None
    assert len(channel.channel_sounds) > 0
```

## Git Workflow

### Branch Naming

```
feature/<feature-name>   # New feature
fix/<bug-description>    # Bug fix
refactor/<what>          # Refactoring
docs/<what>              # Documentation
test/<what>              # Tests
chore/<what>             # Maintenance
```

### Commit Messages

Follow Conventional Commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**: feat, fix, refactor, docs, test, chore, style, perf

**Scope**: app module name (auth, panel, library, models, db)

**Subject**: Imperative, under 50 chars, no period

```bash
# Good commits
git commit -m "feat(panel): add sound reordering via drag-and-drop"
git commit -m "fix(serializer): ensure chance always has % suffix"
git commit -m "refactor(auth): extract session loading to helper"
git commit -m "test(library): add validation for duplicate sound names"
git commit -m "docs: add architecture guide"

# Bad commits
git commit -m "fixed stuff"
git commit -m "WIP: trying something"
git commit -m "Update models.py"
```

### Push Workflow

1. **Make changes**
2. **Test locally** (`uv run pytest`, `uv run ruff check --fix`)
3. **Commit** with good message
4. **Push** to feature branch
5. **Open PR** or merge to main (if authorized)

```bash
# Create feature branch
git checkout -b feature/add-reordering

# Make changes, commit, push
git add app/panel.py tests/test_panel.py
git commit -m "feat(panel): add sound reordering"
git push origin feature/add-reordering

# Open PR or merge
git checkout main
git merge feature/add-reordering
git push origin main
```

### Code Review Checklist

Before committing:

- [ ] Code runs locally (`uv run soundlist`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check app/ tests/`)
- [ ] No commented-out code
- [ ] No debug print statements
- [ ] Type hints on new functions
- [ ] Docstrings on public functions
- [ ] Error messages are clear
- [ ] No secrets in code

## Performance Considerations

### Database Queries

```python
# DO - use SQLAlchemy query optimization
channels = db.query(Channel)\
    .options(joinedload(Channel.owner))\
    .all()

# DON'T - N+1 queries (loads owner for each channel separately)
channels = db.query(Channel).all()
for channel in channels:
    owner = channel.owner  # Triggers new query per channel
```

### JSON Serialization

```python
# Current: Generate fresh JSON on each request
# Pro: Always up-to-date
# Con: Slower for large datasets

# Future optimization: Cache JSON for 60 seconds
# Cache invalidates on channel update
```

### Memory Usage

For large sound libraries:

```python
# BAD - loads all sounds into memory
sounds = db.query(Sound).all()

# GOOD - iterate/paginate
for page in paginate(db.query(Sound), page_size=50):
    # Process page
    pass
```

### Async Considerations

Currently all code is synchronous (database blocking).

For future async support:

```python
# Current (sync)
def get_channel(slug: str) -> Channel:
    return db.query(Channel).filter_by(slug=slug).first()

# Future (async)
async def get_channel(slug: str) -> Channel:
    result = await db.execute(
        select(Channel).where(Channel.slug == slug)
    )
    return result.scalar_one_or_none()
```

---

See [SETUP.md](SETUP.md) for environment setup and [ARCHITECTURE.md](ARCHITECTURE.md) for system design details.
