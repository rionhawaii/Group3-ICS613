# Team Name

Group 3

​

# Project Title

Neighborhood Tool Sharing

## Table of Contents

1. [Description](#1-description)
2. [Team Members and Responsibilities](#2-team-members-and-responsibilities)
3. [Architecture](#3-architecture)
4. [Technologies](#4-technologies)
5. [Project Structure](#5-project-structure)
6. [Getting Started](#6-getting-started)
7. [Environment Variables](#7-environment-variables)
8. [Running the Application](#8-running-the-application)
9. [Running Tests](#9-running-tests)
10. [API Overview](#10-api-overview)
11. [Database](#11-database)
12. [Limitations](#12-limitations)

# 1. Description

This is an ICS613 Group 3 project in Summer 2026. We will collaborate to create a responsive full-stack web application. This web application enables an invite-only tool lending for members only. User accounts can be created with a valid invitation from other members. New users can make a profile and list tools. Tools can be posted with images, descriptions, condition, and, if necessary, customized lending rules. Listed tools are searched for and requested to be lent. The tool status can be updated (e.g., REQUESTED, APPROVED, PICKED_UP, RETURNED, or CANCELLED). Private messages and notifications will be enabled under each reservation. A rating/review will be added after lending ends. Admin users can inactivate lists and users.

​

# 2. Team Members and Responsibilities
​This is our team member list, along with their primary roles and secondary responsibilities.
- Rion Sawabe - Project Manager/Frontend development
- Yafei Wang - Frontend Lead/Documentation and Testing
- Ivan Wu - Backend Lead/Requirements elicitation and code reviews
- Nick Fairhart - QA/DevOps Lead/Backend development
- Loreto Coloma - Document Lead


## Main branch protection rule

The main branch is protected against direct pushing. At least 1 member should review and approve the pull request. 


## Workflow

We will use an Agile workflow. Each member posts on Discord every Monday about what they did in the past week, any blockers, and what they plan to do in the upcoming week. This is because we work online asynchronously. The progress will be noted in the document. Based on this, new tasks will be created and assigned. If there are upcoming presentations or document submissions due approaching, members will have online synchronous meetings to practice or discuss.


## Task management

Our team uses GitHub issues and the [project board (backlog)](https://github.com/orgs/ICS613-Group3/projects/1) to manage tasks. All 35 user stories are tracked on the board with statuses: Backlog, Ready, In progress, In review, Done.

Each assignee will change the task status when they start and when they complete it.


# 3. Architecture

- **Paradigm:** Object-Oriented Programming (OOP)
- **Pattern:** N-Tier architecture
- **Code structure:** Repository / Service pattern

```
API Layer (FastAPI routes)
    ↓
Service Layer (business logic)
    ↓
Repository Layer (SQLAlchemy async — database access)
    ↓
Data Layer (PostgreSQL 15)
```

The API layer calls services only, keeping business logic centralized and testable.

The application handles authentication (JWT), background scheduling (APScheduler), email notifications (SMTP), and environment-based configuration (pydantic-settings) across all layers.

### Architecture Diagram

![Architecture Diagram](docs/images/architecture.png)

### Domain Model

![Domain Model / ER Diagram](docs/images/erd.png)



# 4. Technologies

| Layer | Technology | Notes |
|-------|------------|-------|
| **Frontend** | React | 19.x |
| | React DOM | 19.x |
| | React Router DOM | 7.x (client-side routing) |
| | TypeScript | 6.x |
| | Vite | 8.x (build tool / dev server) |
| | @vitejs/plugin-react | 6.x (uses Oxc compiler) |
| | ESLint | 10.x (with react-hooks and react-refresh plugins) |
| | typescript-eslint | 8.x (type-aware lint rules) |
| **Backend** (Service/API) | Python | 3.11, 3.12, or 3.13 |
| | FastAPI | ≥0.115, <0.120 |
| | SQLAlchemy | ≥2.0, <2.1 (2.x async style) |
| | asyncpg | Async PostgreSQL driver |
| | Pydantic (Data validation) | ≥2.10, <3.0 |
| | pydantic-settings | ≥2.7, <3.0 |
| | Uvicorn | ASGI server (via `python run.py`) |
| | python-jose[cryptography] | JWT auth (HS256) |
| | bcrypt | Password hashing (12 rounds) |
| | JWT (JSON Web Tokens for user authentication) |
| | APScheduler | ≥3.10, <4.0 (background tasks) |
| | python-multipart | Photo uploads |
| | email-validator | Email format validation |
| **Database** | PostgreSQL 15 |
|  | Docker Container (for PostgreSQL) |
| **Environment / Secrets** | `.env` file (for DB passwords, API keys) | python-dotenv (loads `.env` into the app) |
| **Testing** | pytest | `backend/src/app/tests/` (385 tests: 274 acceptance + 111 auxiliary, ~92% line coverage) |
| | pytest-asyncio | Async test support |
| | pytest-cov | Coverage reporting (term/xml/html) |
| | httpx | ASGI test client |
| | Playwright | `frontend/e2e/` (121 browser E2E tests across 25 spec files) |
| **Code Quality** | ruff | Linting and import sorting |
| | mypy | Static type checking |
| | bandit | Backend SAST |
| | semgrep | Frontend SAST (React/TS/OWASP Top 10 rulesets) |
| | detect-secrets | Pre-commit secret scanning |
| **Version Control** | GitHub (branching, pull requests, code review) |
| **IDE** | VS Code or PyCharm |


# 5. Project Structure

```
/
├── backend/
│   ├── db/init/                  # SQL init for new databases
│   ├── docker-compose.yml        # PostgreSQL only — app runs on host
│   ├── Dockerfile                # Production build
│   ├── media/tool_photos/        # Uploaded photos (runtime, gitignored)
│   ├── pyproject.toml            # ruff, mypy, pytest config
│   ├── requirements.txt
│   ├── run.py                    # Cross-platform server launcher
│   ├── scripts/
│   │   ├── check_db.py           # Database connectivity check
│   │   ├── clean_dev.py          # Wipe all rows (keep tables)
│   │   ├── init_db.py            # Create all tables from ORM models
│   │   ├── seed_dev.py           # Demo data seeder (dev only)
│   │   ├── seed_photos/          # Tracked seed images
│   ├── src/
│   │   └── app/
│   │       ├── api/v1/           # REST endpoints
│   │       ├── core/             # Security, exceptions, logging
│   │       ├── db/               # Database engine and session
│   │       ├── models/           # SQLAlchemy ORM models
│   │       ├── schemas/          # Pydantic request/response schemas
│   │       ├── services/         # Business logic layer
│   │       └── tests/            # Test suite
│   ├── .env                      # Local environment config (gitignored)
│   └── .env.example              # Safe template — copy to .env
├── frontend/
│   ├── public/                   # Static assets served directly
│   ├── src/
│   │   ├── assets/               # Images, fonts, and other static files
│   │   ├── components/           # Reusable UI components
│   │   ├── types/                # TypeScript type definitions
│   │   ├── pages/                # Page-level components
│   │   ├── routes/               # Route definitions (AppRoutes.tsx)
│   │   ├── App.css               # Global app styles
│   │   ├── App.tsx               # Root application component
│   │   ├── index.css             # Base/reset styles
│   │   └── main.tsx              # Application entry point
│   ├── .gitignore
│   ├── eslint.config.js          # ESLint configuration
│   ├── index.html                # HTML entry point
│   ├── package-lock.json
│   ├── package.json
│   ├── tsconfig.app.json         # TypeScript config for app code
│   ├── tsconfig.json             # TypeScript root config
│   ├── tsconfig.node.json        # TypeScript config for Node/Vite tooling
│   └── vite.config.ts            # Vite configuration
├── docs/
│   └── images/                   # Architecture and domain model diagrams
└── README.md
```



# 6. Getting Started

> **For detailed setup instructions (Windows, macOS, Linux), see [`SETUP_AND_TEST_GUIDE.md`](SETUP_AND_TEST_GUIDE.md).**
> **For deployment, see [`Deployment_Guide.md`](Deployment_Guide.md).**

### Prerequisites
| Program | Minimum Version | Check With |
|---------|----------------|------------|
| Git | 2.30+ | `git --version` |
| Python | 3.11, 3.12, or 3.13 | `python --version` |
| Docker + Docker Compose | Docker 24+ | `docker --version` |

> **Windows users:** See `backend/Backend_Setup.md` for PowerShell vs Git Bash vs cmd.exe notes and a tip on adding Python to PATH during install.

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/ICS613-Group3/Group3-ICS613-project
cd Group3-ICS613-project

# 2. Move into the backend folder
cd backend

# 3. Start the database container (PostgreSQL only)
docker compose up -d
# Verify it is healthy before continuing:
docker compose ps

# 4. Create and activate a Python virtual environment
python -m venv venv
source venv/bin/activate               # PowerShell: .\venv\Scripts\Activate.ps1

# 5. Install dependencies
pip install -r requirements.txt

# 6. Configure environment variables
cp .env.example .env
# The defaults work for local development — no edits needed to run locally.
# See Section 7 for what each variable does.

# 7. Verify database connectivity
python scripts/check_db.py
# All 6 checks should report [OK]

# 8. Create database tables
python scripts/init_db.py

# 9. (Optional) Load seed data — development only
python scripts/seed_dev.py
# Creates 3 demo users and 12 tool listings. Passwords are printed to the terminal.

# 10. Start the backend server
python run.py --reload
```

```bash
# 11. Set up the frontend (open in a new terminal from repo root)
cd frontend
npm install
npm run dev
```

For full detail on each step — including Windows-specific commands, troubleshooting, and seed user credentials — see [`backend/Backend_Setup.md`](backend/Backend_Setup.md).


# Local security tooling setup

This repo uses [pre-commit](https://pre-commit.com/) to catch committed
secrets before they leave your machine. One-time setup after cloning:

    pip install pre-commit
    pre-commit install

This installs a git hook that runs `detect-secrets` against staged files
on every commit, checked against `.secrets.baseline`. If it flags a new
finding that's a genuine false positive, update the baseline with:

    detect-secrets scan --exclude-files 'package-lock\.json$' > .secrets.baseline

and commit the updated file — do not delete `.secrets.baseline` to make
the hook pass. If a finding looks like a real secret, treat it as an
incident (rotate/remove the credential) instead of baselining it away.


## 7. Environment Variables

`backend/.env.example` is the authoritative template. Copy it to `backend/.env` — the defaults work for local development without any edits. **Never commit `.env` to version control** (`.gitignore` already excludes it).

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://ics613user:ics613password @localhost:5432/toolsharing` | Main database connection (local dev default) |
| `TEST_DATABASE_URL` | `…/toolsharing_test` | Test database connection |
| `SECRET_KEY` | `change-me-…` (placeholder) | JWT signing key — placeholder accepted in `development`; **rejected in `production`** |
| `ENVIRONMENT` | `development` | Controls startup validations (`development`, `test`, `production`) |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed frontend origins |
| `DISABLE_SCHEDULER` | `false` | Set to `true` to skip background jobs during development |

> **Production `SECRET_KEY`:** Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and paste into `.env`. The app will refuse to start in production with the placeholder value.



## 8. Running the Application

### Backend
```bash
cd backend
source venv/bin/activate             # PowerShell: .\venv\Scripts\Activate.ps1
python run.py --reload
```
- API: `http://localhost:8000`
- Interactive API docs (Swagger UI): `http://localhost:8000/docs`

### Frontend
```bash
cd frontend
npm install        # first time only
npm run dev
```
- App: `http://localhost:5173`

### Docker containers (database only)

| Container | Image | Purpose | Port |
|-----------|-------|---------|------|
| `tool-db` | postgres:15 | Database | 5432 → 5432 |

> The FastAPI app runs **on the host** via `python run.py`, not inside Docker. If `docker ps` shows a `tool-share-backend-1` container, your `docker-compose.yml` is out of date — pull the latest changes and run `docker compose up -d --remove-orphans`.



## 9. Running Tests

### Backend (pytest)

```bash
cd backend
source venv/bin/activate
pytest src/app/tests/ -q                                    # all 385 tests
pytest src/app/tests/ -v                                    # verbose output
pytest src/app/tests/acceptance/test_us01_register.py -v    # single file
pytest src/app/tests/ --cov=app --cov-report=term-missing   # with coverage
```

> `pyproject.toml` configures `pythonpath = ["src"]` for pytest — no environment variables needed.

The suite is split into two directories:

| Directory | Count | Maps to |
|-----------|-------|---------|
| `src/app/tests/acceptance/` | 274 tests | One file per user story (`test_us##_*.py`), scenario-based, traceable to acceptance criteria |
| `src/app/tests/auxiliary/` | 111 tests | Supplementary coverage (edge cases, security, exception routing) with no direct user-story mapping |

Current backend line coverage is **~92%** (`app/` package, tests excluded). CI publishes the full `term-missing` breakdown and an HTML report as build artifacts on every run.

### Frontend E2E (Playwright)

```bash
cd frontend
npm run test:e2e              # full suite against a real backend + Postgres
npx playwright test --list    # list tests without running them
npx playwright show-report    # view the last HTML report
```

121 browser tests across 25 spec files under `frontend/e2e/`, organized by feature area (`auth/`, `tools/`, `reservations/`, `account/`, `admin/`, `misc/`) plus one isolated regression spec (`issue-141/`, run separately via `playwright.issue141.config.ts`). These drive the real Vite dev server and a live FastAPI backend — not mocks — so `LoginPage` and other flows exercise the actual `/api/v1` endpoints.

### CI pipeline

Every push and PR to `main` runs, via [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Job | What it checks |
|-----|-----------------|
| Backend tests | Full pytest suite (unit + acceptance) with coverage against a real Postgres service container |
| Backend lint | `ruff check`, `ruff format --check`, `mypy`, `bandit` (SAST) |
| Frontend checks | `eslint`, `tsc -b`, production build |
| Frontend E2E | Full Playwright suite against a live backend + seeded Postgres |
| Frontend E2E (issue #141/#197) | Isolated regression spec, mocked API, run separately from the main E2E job |
| Secrets scan | `detect-secrets` via pre-commit, run against all tracked files |
| Frontend SAST | `semgrep` (React/TypeScript/OWASP Top Ten rulesets) against `frontend/src` |

### Test coverage by owner

| Test Type | Owner | Where It Lives |
|-----------|-------|----------------|
| Unit / integration (automated) | Backend lead | `backend/src/app/tests/` (pytest, 385 tests, ~92% coverage) |
| Manual acceptance test cases | QA lead | Separate document (at least one case per user story scenario) |
| E2E browser automation | QA lead | `frontend/e2e/` (Playwright, 121 tests) |



## 10. API Overview

All endpoints are prefixed with `/api/v1`. Authentication uses a **JWT Bearer token** in the `Authorization` header.

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| Auth | `/auth` | register, verify-email, login, logout, forgot/reset-password, invites |
| Tools | `/tools` | create listing, browse/search, edit, deactivate/reactivate, photo upload |
| Reservations | `/reservations` | request, approve, deny, cancel, mark-picked-up, mark-returned, damage report |
| Messages | `/reservations/{id}/messages` | send and list thread messages |
| Notifications | `/notifications` | list, mark-read |
| Reviews | `/reviews` | create, edit (24h window), delete (24h window) |
| Categories | `/categories` | list, create, delete (admin-only) |
| Reports | `/tools/{id}/report` | report a listing, admin moderation queue |
| Admin | `/admin` | suspend/reactivate members, audit log, moderation reports, categories |

Full interactive documentation is available at `http://localhost:8000/docs` when the backend is running.



## 11. Database

**PostgreSQL 15** running in Docker. Schema is managed with `init_db.py` (SQLAlchemy `create_all()`).

### Key design decisions
- **UUID primary keys** — prevents ID enumeration.
- **PostgreSQL native ENUMs** — reservation states, tool categories, and user statuses are enforced at the database level.
- **EXCLUDE GiST constraint** on reservations — prevents double-booking at the database level with no application-level locking needed.
- **Soft deletes** — users and tools are never hard-deleted; records are preserved for audit history.
- **Async driver (asyncpg)** — all database access is non-blocking via SQLAlchemy's async interface.

### Tables (13 total)

`users`, `invite_tokens`, `email_verification_tokens`, `password_reset_tokens`, `tools`, `photos`, `reservations`, `messages`, `notifications`, `reviews`, `listing_reports`, `tool_categories`, `admin_audit_log`

### Reservation states

```
REQUESTED → APPROVED → PICKED_UP → RETURNED
         ↘ DENIED (terminal)
REQUESTED or APPROVED → CANCELLED (terminal)
```

## 12. Limitations

Known constraints and out-of-scope gaps as of 2026-08-12, verified against
current code. For the live list of confirmed bugs and test-coverage gaps
(with file/line references), see [`QA_SUMMARY.md`](QA_SUMMARY.md).

- **No SSL/TLS.** Local development runs over HTTP.
- **No automated migrations.** Tables are created with
  `CREATE TABLE IF NOT EXISTS` via SQLAlchemy `create_all()`. Schema
  changes to existing columns require a manual drop and recreate — there's
  no Alembic (or equivalent) migration chain.
- **Photo storage is the local filesystem.** Tool photos are written to
  `backend/media/tool_photos`, not object storage. Fine for local dev and
  the demo; would need to move to something like S3 before a real
  multi-instance deployment.
- **Auth-endpoint rate limits are tight by default, not generous.** Login,
  forgot-password, and resend-verification default to 10/minute per IP;
  registration defaults to 10/hour per IP. These are already
  production-sized to resist credential stuffing and email-bombing, not
  dev-friendly defaults — raise them via `RATE_LIMIT_*` env vars in
  dev/e2e environments if a test suite needs more requests from one IP.
- **Scheduler runs in-process.** Background jobs (auto-cancel, overdue
  escalation, etc.) run inside the same Uvicorn process, not a separate
  worker. Set `DISABLE_SCHEDULER=true` to disable.
- **SMTP is optional for dev.** Email failures are logged but don't block
  startup; local dev points at MailHog by default. Seed data ships with
  pre-verified accounts so registration email isn't required to log in.
- **No real-time messaging.** Messages don't appear on the receiver's
  screen live — the thread has to be reloaded/refetched to see new
  messages.
- **Deleted member profile links break.** After a member is soft-deleted,
  their public profile route (`GET /users/{id}`) 404s, so historical
  reservation/review records that reference them (e.g. old reservation
  history, US7) show a broken profile link instead of a name.
- **Tool listings have no lending-rules fields yet (US8, US9, US12,
  US20).** `latest_return_time`, lending rules, and notes-for-borrowers
  are not implemented anywhere on `Tool` — not on listing creation/edit,
  not in browse/search, and not factored into return-timing checks.
- **Auto-cancel notification for owners contacting admins isn't
  implemented (US16).** A listing owner has no in-app path to contact an
  admin directly.
- **Cancellation-reason validation has no visible error message (US15).**
  The Cancel Request / Cancel Reservation buttons are correctly disabled
  until a reason is entered, but no message like "Please enter a
  cancellation reason" is shown, so the requirement isn't obvious from
  the UI alone.
- **Report-reason validation has no visible error message (US26).** The
  listing-report reason field is marked required (and submission is
  blocked without it), but the "A report reason is required" message
  doesn't render — only the `*` next to the label hints that it's
  mandatory.
- **Review reminder is only half-built (US24, Scenario 9).** The listing
  owner gets an immediate review notification when a tool is returned;
  there's no 3-day timer and the borrower never receives a review prompt
  at all.
- **Moderation report export is CSV-only (US33).** No PDF or other export
  format is available.
- **Admin reservation filtering has no owner/borrower name search
  (US34).** The admin all-reservations view filters by state, a single
  `member_id`, and date range — there's no way to filter by owner or
  borrower name directly.
- **No Hawaii Standard Time normalization on the request path (US19).**
  ADR-006 names HST as canonical, and scheduler-side jobs do convert
  through HST (`app/core/timezone.py`), but request/response endpoints
  that compare against "today" (e.g. creating a reservation) use naive
  server-local dates instead.
