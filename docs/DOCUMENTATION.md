# Soundlist - Documentation Index

Complete documentation for the Soundlist management panel. Start here to find what you need.

## For Different Audiences

### I'm New - Where Do I Start?

1. **[SETUP.md](SETUP.md)** - Get the app running locally
   - Prerequisites
   - Installation steps
   - Twitch OAuth setup
   - Running tests

2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Understand the big picture
   - System overview
   - Module organization
   - Key design decisions
   - Data model

3. **[INTEGRATION.md](INTEGRATION.md)** - See how pieces fit together
   - Component interactions
   - Request flow
   - Database relationships

### I'm Implementing a Feature

1. **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development workflow
   - Getting started
   - Code standards
   - Common tasks (add endpoint, fix bug, refactor)
   - Git workflow

2. **[API.md](API.md)** - Endpoint reference
   - All HTTP endpoints
   - Request/response formats
   - Auth requirements
   - Error codes

3. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Design context
   - Module responsibilities
   - Data model
   - Security architecture

### I'm Debugging a Problem

1. **[DEVELOPMENT.md](DEVELOPMENT.md#debugging)** - Debug techniques
   - Logging
   - Print statements
   - Interactive debugging
   - Database inspection

2. **[INTEGRATION.md](INTEGRATION.md)** - Component interactions
   - Request flow
   - Data layer integration
   - Authentication flow

3. **[REQUIREMENTS.md](REQUIREMENTS.md)** - Original requirements
   - Functional specs
   - JSON contract
   - Acceptance criteria

### I'm Setting Up Production

1. **[SETUP.md](SETUP.md#production-deployment)** - Production checklist
   - Environment variables
   - Database migration
   - Running as a service
   - Reverse proxy setup

2. **[ARCHITECTURE.md](ARCHITECTURE.md#deployment-architecture)** - Deployment design
   - Architecture diagram
   - Service setup
   - Monitoring
   - Configuration management

3. **[SECURITY.md](SECURITY.md)** - Security model and invariants
   - Static file allowlist (keeps secrets off the wire)
   - Secrets handling (SecretStr)
   - Auth, RBAC, and CSRF
   - Invariants to preserve and hardening log

### I'm an AI Agent Working in This Repo

1. **[../CLAUDE.md](../CLAUDE.md)** - Agent guide
   - Hard invariants not to break
   - House style and workflow
   - Where things live and known gotchas

2. **[SECURITY.md](SECURITY.md)** - Full security invariants

### I Need API Details

1. **[API.md](API.md)** - Complete endpoint documentation
   - All endpoints organized by category
   - Request/response examples
   - Status codes
   - Error responses

2. **[REQUIREMENTS.md](REQUIREMENTS.md#5-json-output-contract)** - JSON contract
   - Exact JSON format
   - Field types and rules
   - Examples
   - Legacy format requirements

## Document Overview

### Setup

**[SETUP.md](SETUP.md)** - Installation and configuration

- Prerequisites and version requirements
- Development environment setup
- Database setup and migration
- Twitch OAuth configuration
- Environment variables reference
- Running locally and in production
- Troubleshooting common issues
- Testing setup

### Architecture & Design

**[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and structure

- High-level system architecture with diagrams
- Module organization and responsibilities
- Key design decisions and rationale
- Data model and relationships
- Request handling pipeline
- Security architecture (auth, RBAC, CSRF)
- Testing architecture
- Deployment architecture

**[PLAN.md](PLAN.md)** - Original project plan (historical reference)

- Problem statement and scope decisions
- Key design decisions and rationale
- Data model and JSON compatibility contract
- Implementation milestones (all complete as of M6)

**[REQUIREMENTS.md](REQUIREMENTS.md)** - Functional and non-functional requirements

- Functional requirements by feature
- Non-functional requirements
- Data integrity rules
- JSON output contract (non-negotiable)
- Acceptance criteria for v1

### Integration & APIs

**[INTEGRATION.md](INTEGRATION.md)** - How components work together

- Architecture overview
- Request flow (authenticated and public)
- Authentication and OAuth flow
- Data layer integration
- JSON output generation
- Frontend integration
- Admin panel integration
- Testing integrations

**[API.md](API.md)** - HTTP endpoint reference

- Complete endpoint documentation
- Authentication requirements
- Request/response examples
- Status codes and errors
- Public JSON contract
- Health check endpoint
- CSRF protection
- Rate limiting notes

### Development

**[DEVELOPMENT.md](DEVELOPMENT.md)** - Developer workflow

- Getting started for developers
- Code organization and standards
- Module responsibilities
- Coding conventions (style, naming, etc.)
- Common development tasks
- Debugging techniques
- Git workflow and commit messages
- Performance considerations

### Tracking

**[TASKLIST.md](TASKLIST.md)** - Implementation progress

- Milestone breakdown
- Task status (done/in progress/pending)
- Technical debt items (D1-D5)
- Follow-ups for future phases

## Quick Reference

### Setting Up

```bash
git clone <repo>
cd soundlist
uv sync
cp .env.example .env
# Edit .env with Twitch credentials
uv run soundlist
```

### Running Tests

```bash
uv run pytest              # All tests
uv run pytest -v           # Verbose
uv run pytest tests/test_auth.py  # Specific file
uv run pytest --cov        # With coverage
```

### Code Quality

```bash
uv run ruff check --fix app/ tests/  # Lint and fix
uv run ruff format app/ tests/        # Format
uv run pylint app/                    # Type check
```

### Starting Development

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Test: `uv run pytest`
4. Lint: `uv run ruff check --fix app/`
5. Commit: `git commit -m "feat(scope): description"`
6. Push: `git push origin feature/my-feature`

## Key Concepts

### Request Flow

1. HTTP request arrives at FastAPI
2. SessionMiddleware extracts user from signed cookie
3. Route handler resolves dependencies (require_auth, require_channel_access)
4. Business logic executes (query/update database)
5. Response generated (JSON or HTML)
6. Sent to client

See [INTEGRATION.md - Request Flow](INTEGRATION.md#request-flow) for details.

### Authentication

- Users log in via **Twitch OAuth** (no passwords stored)
- Session stored in **signed cookie** (7-day expiry)
- Per-request user load ensures **freshness**
- Channels are **claimed by slug matching** (automatic on first login)

See [ARCHITECTURE.md - Security Architecture](ARCHITECTURE.md#security-architecture) for details.

### Authorization (RBAC)

- **Admin**: Can read/write all channels and library
- **Streamer**: Can read/write only owned channels
- **Public**: Can read JSON endpoints only

Enforced via FastAPI dependencies on every protected endpoint.

### Database

- **SQLite** for local dev/production (scale up to PostgreSQL if needed)
- **SQLModel** ORM (SQLAlchemy 2.0 + Pydantic)
- **Automatic schema creation** on startup
- **Relationships** for channel ownership and sound linking

### JSON Contract

Four public endpoints generate JSON from the database:

1. `GET /lists/index.json` - Channel index
2. `GET /lists/<slug>.json` - Channel sounds
3. `GET /lists/internals/avatars.json` - Avatar URLs
4. `GET /lists/internals/IconTriggers2.json` - Icon mappings

**Non-negotiable format rules** (enforced by serializer):
- `enabled` must be string "true" or "false" (not boolean)
- `chance` must be string with "%" (e.g. "50%")
- `sound` must be string (single-clip) or array of strings (multi-clip)

See [REQUIREMENTS.md - JSON Contract](REQUIREMENTS.md#5-json-output-contract) for full details.

## Document Relationships

```
DOCUMENTATION.md (this file)
    |
    +-- SETUP.md (installation)
    |
    +-- ARCHITECTURE.md (design)
    |   |
    |   +-- PLAN.md (planning)
    |   +-- DEVELOPMENT.md (coding)
    |
    +-- INTEGRATION.md (interactions)
    |   |
    |   +-- API.md (endpoints)
    |   +-- REQUIREMENTS.md (contracts)
    |
    +-- TASKLIST.md (progress)
    +-- REQUIREMENTS.md (specs)
```

## Conventions Used

### Status Keys

In requirement and task documents:

- **MUST** - Required for v1
- **SHOULD** - Wanted for v1
- **LATER** - Deferred to future phase
- **DONE** - Completed and shipped
- **IN_PROGRESS** - Currently being worked on

### File References

When referencing code locations:

`path/to/file.py:line_number` - Used to point to specific code

Example: `app/panel.py:123` points to line 123 of the panel router

### Database Diagram Notation

```
Entity (1)
  |
  +-- relationship --> OtherEntity (Many)
```

Indicates:
- Entity has one of the relationships
- Each OtherEntity is related to one Entity
- Multiple OtherEntity can relate to one Entity

## Getting Help

### Common Questions

**Q: Where do I add a new API endpoint?**
A: See [DEVELOPMENT.md - Adding a New Endpoint](DEVELOPMENT.md#adding-a-new-endpoint). Choose appropriate router file (panel.py, library.py, etc.)

**Q: How is authentication implemented?**
A: See [ARCHITECTURE.md - Security Architecture](ARCHITECTURE.md#security-architecture) and [INTEGRATION.md - Authentication Flow](INTEGRATION.md#authentication-flow)

**Q: What's the JSON format contract?**
A: See [REQUIREMENTS.md - JSON Output Contract](REQUIREMENTS.md#5-json-output-contract) and [API.md - Public JSON Endpoints](API.md#public-json-endpoints)

**Q: How do I run tests?**
A: See [SETUP.md - Testing](SETUP.md#testing)

**Q: How are modules organized?**
A: See [ARCHITECTURE.md - Module Organization](ARCHITECTURE.md#module-organization)

**Q: How does the request flow work?**
A: See [INTEGRATION.md - Request Flow](INTEGRATION.md#request-flow) and [ARCHITECTURE.md - Request Handling Pipeline](ARCHITECTURE.md#request-handling-pipeline)

**Q: How do I add a new database field?**
A: See [DEVELOPMENT.md - Adding a Database Field](DEVELOPMENT.md#adding-a-database-field)

**Q: What are the coding standards?**
A: See [DEVELOPMENT.md - Coding Standards](DEVELOPMENT.md#coding-standards)

### When Stuck

1. Check relevant documentation (use this index)
2. Search for similar code in the codebase
3. Check tests for example usage
4. Review git history for related commits
5. Ask in team discussion/chat

### Reporting Issues

When reporting a bug or issue:

1. Describe what you expected to happen
2. Describe what actually happened
3. Include steps to reproduce
4. Include relevant error messages
5. Check [DEVELOPMENT.md - Debugging](DEVELOPMENT.md#debugging) first

## Contributing

See [DEVELOPMENT.md](DEVELOPMENT.md) for:

- Code standards and conventions
- Commit message format
- Testing requirements
- Git workflow
- Common development tasks

### Before Opening a PR

- [ ] Tests pass: `uv run pytest`
- [ ] Linting passes: `uv run ruff check app/`
- [ ] No secrets in code
- [ ] Commit messages follow conventions
- [ ] Documentation updated if needed

## Document Maintenance

These documents should stay in sync with the code:

- When adding a feature, update relevant documentation
- When changing architecture, update ARCHITECTURE.md
- When adding endpoints, update API.md
- When changing database schema, update ARCHITECTURE.md and INTEGRATION.md
- When completing a task, update TASKLIST.md

Last updated: 2026-06-04. All M1-M6 milestones complete.
