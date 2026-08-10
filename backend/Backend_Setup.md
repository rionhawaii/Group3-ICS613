# Backend Setup Guide

**Group 3 — Neighborhood Tool Sharing**
**ICS 613 — Summer 2026**

This guide gets the backend running on your machine. After following it you will have PostgreSQL running in Docker, all Python dependencies installed, the database schema created, and seed data loaded.

> **Choose your shell on Windows.** All examples in this guide are written for
> **PowerShell 5.1+** (the default terminal on Windows 10/11). The right-hand
> column shows the equivalent **Git Bash** command. If you are on **cmd.exe**,
> translate PowerShell commands using the table in section 2.

---

## 1. Prerequisites

| Program | Minimum version | Check with |
|---------|----------------|------------|
| Git | 2.30+ | `git --version` |
| Python | 3.11, 3.12, or 3.13 | `python --version` |
| Docker + Docker Compose | Docker 24+ | `docker --version; docker compose version` |

If any check fails, install that program before continuing.

> **Windows Python install tip.** Download Python 3.11+ from
> https://www.python.org/downloads/windows/ and **check "Add Python to PATH"**
> during install. Re-open your terminal after install so the new PATH
> takes effect.

---

## 2. Cross-platform notes

### 2a. PowerShell vs Git Bash on Windows

| Action | PowerShell (default) | Git Bash |
|--------|----------------------|----------|
| Python version | `python --version` | `python3 --version` |
| Create venv | `python -m venv venv` | `python3 -m venv venv` |
| Activate venv | `.\venv\Scripts\Activate.ps1` | `source venv/bin/activate` |
| Copy file | `cp .env.example .env` (alias) | `cp .env.example .env` |
| Set env var for one command | `$env:VAR = 'value'; <command>` | `VAR=value <command>` |
| Path separator | `\` or `/` both work in most tools | `/` |

`cp`, `ls`, `cat`, `rm` all work in PowerShell as **aliases** for the
`Copy-Item`, `Get-ChildItem`, `Get-Content`, `Remove-Item` cmdlets. You do
not need Git Bash to run the basic setup.

### 2b. cmd.exe (if you must)

cmd.exe is the least ergonomic of the three. If you are stuck with it:

| Action | cmd.exe |
|--------|---------|
| Python version | `python --version` |
| Create venv | `python -m venv venv` |
| Activate venv | `venv\Scripts\activate.bat` |
| Copy file | `copy .env.example .env` |
| Set env var | `set VAR=value` *(persists for the whole cmd window!)* |

To run a single command with an env var in cmd, wrap in a subshell:
`cmd /c "set VAR=value && command"`.

**Recommendation:** open PowerShell (`Win + X → Windows PowerShell` or
`Windows Terminal → PowerShell`) instead.

---

## 3. Clone and enter the project

```powershell
git clone https://github.com/ICS613-Group3/Group3-ICS613-project.git
cd Group3-ICS613-project\\backend
```

All remaining commands run from `backend\`.

---

## 4. Start PostgreSQL

```powershell
docker compose up -d
```

This starts the database container (`tool-db`) in the background. The FastAPI app is NOT run in Docker — you run it on the host (see section 11). Running the app on the host is faster for hot-reload during development and avoids port conflicts.

Verify the database is healthy:

```powershell
docker compose ps
```

Wait until the `db` service shows `healthy`. If it stays `starting` for more than 30 seconds, check the logs:

```powershell
docker compose logs db
```

---

## 5. Create Python virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Your prompt should now show `(venv)`. To deactivate later, run `deactivate`.

> **PowerShell execution policy error?** If you get
> *"running scripts is disabled on this system"*, run PowerShell **as
> Administrator** once and execute:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-open your regular PowerShell window. **Do not** use
> `Set-ExecutionPolicy Unrestricted` — that disables a security boundary.

---

## 6. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If `pip` is not on PATH inside the venv, use `python -m pip ...` instead.

---

## 7. Configure environment

```powershell
cp .env.example .env
```

The defaults work for local development. If you changed the PostgreSQL password or want real email sending, edit `backend\.env`. The key settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://ics613user:ics613password@localhost:5432/toolsharing` | Main database |
| `TEST_DATABASE_URL` | …`localhost:5432/toolsharing_test` | Test database |
| `SECRET_KEY` | placeholder (`change-me-...`, ≥ 32 chars) | JWT signing key — see below |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed frontend origins |
| `DISABLE_SCHEDULER` | `false` | Set to `true` to skip background jobs |

**`SECRET_KEY` for local dev:** the placeholder value shipped in `.env.example`
(`replace-with-a-long-random-string-at-least-32-characters-long`) is accepted as
long as your `ENVIRONMENT` is set to `development`, `test`, or `dev`
(which `.env.example` does by default). You don't need to generate a key
to run locally.

**`SECRET_KEY` for production:** the placeholder is rejected at startup when
`ENVIRONMENT=production`. Generate a real key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output as the value of `SECRET_KEY=` in your `.env` file. **Do not
commit this value to git.** `.gitignore` already excludes `.env`.

---

## 8. Verify database connectivity

```powershell
python scripts\check_db.py
```

All checks should report `[OK]`.

---

## 9. Create database schema

The application uses SQLAlchemy `Base.metadata.create_all()` to create all tables
automatically from the ORM models. There is no Alembic migration workflow to run — `init_db.py` uses `create_all()` instead.

From the `backend/` directory, run:

```powershell
python scripts\init_db.py
```

All 13 tables (`users`, `tools`, `photos`, `reservations`, `reviews`, `notifications`,
`messages`, `listing_reports`, `admin_audit_log`, `tool_categories`, invite/password-reset/
verification token tables) will be created.

To verify the tables exist:

```powershell
docker compose exec db psql -U ics613user -d toolsharing -c "\dt"
```

### Upgrading from R1

If you already have a database from R1, pulling the latest code is not enough —
you must drop and recreate the schema. `create_all()` only creates tables that
don't exist; it does not alter existing columns. Your `tools` table still has the
old R1 enum column, and your database is missing the new R2 tables.

```powershell
# 1. Wipe all data (keep table structure)
python scripts\clean_dev.py

# 2. Drop the entire schema (resets column types + removes old tables)
docker compose exec db psql -U ics613user -d toolsharing -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Recreate all tables with the R2 schema
python scripts\init_db.py

# 4. Re-seed with demo data
python scripts\seed_dev.py
```

You now have a fresh R2 database with demo data.

---

## 10. Load seed data (optional)

> ⚠️ **DEVELOPMENT ONLY.** The seed users (`admin@example.com`, `member01@example.com`,
> `member02@example.com`) and `SEED_PASSWORD` are local demo accounts. They exist only
> in your local PostgreSQL database for testing the app. They are NOT real mailboxes,
> do NOT send or receive real email, and must NEVER appear in any deployed environment.
> In production, real users register through the admin invite flow.

```powershell
python scripts\seed_dev.py
```

Creates three demo users, 5 admin-managed tool categories, 12 tool listings with photos, 7 reservations, 4 reviews, 3 notifications, and 2 invite tokens:

| Email | Password | Role |
|-------|----------|------|
| `admin@example.com` | **from `SEED_PASSWORD` in `.env` (default `devpass123`)** | Admin |
| `member01@example.com` | same as admin | Owner |
| `member02@example.com` | same as admin | Borrower |

The seed script **generates a random 16-character password** on every
run and prints it to stderr if you did not set `SEED_PASSWORD` in your
`.env`. Sample output:

```
[seed] No SEED_PASSWORD env var set — generated a random one.
      Use this to log in as admin@example.com / member01@example.com
      / member02@example.com:
        password = aB3xK9pL2mN7qR4s
      Set SEED_PASSWORD in your .env to fix it for repeated runs.
```

To pin the password for repeated runs, add to your `.env`:

```dotenv
SEED_PASSWORD=my-development-password
```

**Setting the password on the command line instead of `.env`:**

```powershell
# PowerShell — one command
$env:SEED_PASSWORD = "devpass123"; python scripts\seed_dev.py  # pragma: allowlist secret
```

```cmd
:: cmd.exe — set first, then run (stays set for the whole window)
set SEED_PASSWORD=devpass123
python scripts\seed_dev.py
```

```bash
# Git Bash / Linux / macOS
SEED_PASSWORD=devpass123 python scripts/seed_dev.py
```

> `SEED_PASSWORD=... python ...` is bash syntax only. cmd.exe and PowerShell
> cannot parse it — that is why this guide's default is `python scripts\seed_dev.py`
> with the password taken from `.env`.

**Re-running the seed script:** If you run `seed_dev.py` a second time it will fail with a `duplicate key` error because the users already exist. Clear existing data first:

```powershell
python scripts\clean_dev.py
python scripts\seed_dev.py
```

The `clean_dev.py` script deletes all rows from every table without dropping the tables themselves, so you can re-seed as many times as needed during development.

### About the seed email addresses

These three addresses are **local seed accounts for development and demo only**. They are NOT real mailboxes and never send or receive real email. They exist only in your local PostgreSQL database so the team can log in and test the app without going through the invite flow every time.

The `@example.com` domain is reserved for documentation purposes (RFC 2606) and is not affected by the `email-validator` library's special-use domain block that would reject addresses like `@toolsharing.local`.

The real email flow is:

| Account | Address | What it does |
|---------|---------|--------------|
| **Sender (outgoing)** | `ics613.group3@gmail.com` | Sends verification, password-reset, and invite emails to real users. Configured in `.env` as `SMTP_FROM` and `SMTP_USER`. |
| **Receivers (real users)** | real addresses like `alice@example.com` | Recipients who were invited by the admin. They receive the invite email, register through the link, and get verified through their own address. |
| **Seed accounts (dev only)** | `admin@example.com`, `member01@example.com`, `member02@example.com` | Pre-created demo logins in the local database. Use these to skip the invite flow during local testing. |

### Configure your own SMTP credentials

The Backend lead does **NOT** share a team SMTP password. Every team member must use **their own Gmail address and App Password** for local development.

> **⚠️ SECURITY — SMTP password rotation:**
> The team-wide SMTP password (`ics613.group3@gmail.com`) that may have been
> shared in chat is a real Gmail App Password. **Rotate it now** by going to
> https://myaccount.google.com/apppasswords and revoking the old password,
> then generating a new one. The new password belongs to `ics613.group3@gmail.com`
> only — do not paste it into chat, Discord, or any other channel. Store it
> locally in your `.env` file (which is gitignored). If you need the
> transactional email account's password, ask the Backend lead in person or
> over a 1:1 call.

If you do not set your own SMTP credentials, the application will still work — SMTP failures are logged as warnings and the operation continues. No real mail is sent. The invite/reset/verify tokens are still saved in the database, so you can complete the flow by reading the token directly from the database if needed.

To set up your own SMTP:

1. Enable 2-Step Verification on your personal Google account.
2. Go to https://myaccount.google.com/apppasswords and generate an App Password for "Mail".
3. Copy the 16-character password (no spaces).
4. Edit your local `backend\.env` and update:
   ```dotenv
   SMTP_USER=your-own-email@gmail.com
   SMTP_PASSWORD=xxxxxxxxxxxxxxxx
   ```
5. Do NOT commit `.env` to the repo. The `.gitignore` already excludes it.

If you need to add yourself as a real user, ask the seeded admin to invite your real email through the admin API or frontend, then register through the link. The seeded accounts stay in your local database only and are not visible to anyone else.

---

## 11. Start the server

The backend includes a `run.py` helper at the project root that takes care
of the `sys.path` setup that `PYTHONPATH=src` would normally do. You do
**not** need to set `PYTHONPATH` for any of the commands in this guide.

```powershell
python run.py --reload
```

Open http://localhost:8000/docs for the interactive API documentation.

> **Equivalent to:** `uvicorn src.app.main:app --reload --port 8000` on
> bash, but works on every shell. `run.py` adds `src/` to `sys.path` and
> delegates to uvicorn with `src.app.main:app` as the default.

`run.py` accepts any uvicorn flag:

```powershell
python run.py --host 0.0.0.0 --port 9000 --reload --log-level debug
python run.py --help    # full uvicorn CLI help
```

---

## 12. Run tests

```powershell
pytest src/app/tests/ -q
```

All tests should pass (373 passed, 17 skipped, 9 xfailed in the current suite). The test database (`toolsharing_test`) is created automatically by `db/init/00-create-test-db.sql` when the Docker container first starts. `pyproject.toml` configures `pythonpath = ["src"]` and the test conftest sets default env vars, so no `PYTHONPATH` or `.env` setup is needed.

Run a single test file:

```powershell
pytest src/app/tests/acceptance/test_us01_register.py -v
```

### What these tests cover (and what they do NOT cover)

The 394 tests in `src/app/tests/` are **acceptance and auxiliary tests**. They verify that each API endpoint behaves correctly — status codes, request validation, response shapes, database state changes, and business rules (e.g., overlap rejection via the EXCLUDE constraint, magic-byte photo validation, CancellerType CHECK constraint). They run automatically with pytest and do not require a separate server process.

**Test breakdown:**
- 283 acceptance tests (`src/app/tests/acceptance/`) — verify user story scenarios via API calls
- 97 auxiliary tests (`src/app/tests/auxiliary/`) — security/permission/edge-case coverage with no user-story mapping (rate limiting, SECRET_KEY validation, audit-log detail, admin user directory, etc.)

**These tests cover user-facing acceptance scenarios.** Each acceptance test file maps 1:1 to a user story (US01–US34 + admin invite) with one class per scenario, following the convention in `src/app/tests/acceptance/__init__.py`.

In short:

| Test type | Owner | Purpose | Where it lives |
|-----------|-------|---------|----------------|
|| Acceptance tests | QA lead | Verify user story scenarios via API calls | `src/app/tests/acceptance/` (283 tests, pytest) |
|| Auxiliary tests | QA lead | Security/permission/edge-case coverage with no user-story mapping | `src/app/tests/auxiliary/` (97 tests, pytest) |
|| E2E browser automation | QA lead | Drive a full demo path through the UI | `frontend/e2e/` (Playwright, runs in CI) |

If you change backend code, run the pytest suite to make sure the acceptance and auxiliary tests still pass.

---

## 13. Lint and type-check

```powershell
ruff check src/app/      # lint
mypy src/app/            # type-check (optional, not required for PRs)
```

---

## Common issues

**"Cannot connect to database"**
- Is Docker running? `docker info`
- Wait 10 seconds for PostgreSQL to finish starting

**"Address already in use" on port 5432**
- Port 5432 is the **default and required** port for this project. If something else is already listening on 5432, find and stop it — do not change this project's port.
- **Identify the conflicting process:**

  ```powershell
  # Show the PID owning port 5432
  Get-NetTCPConnection -LocalPort 5432 -State Listen |
      Select-Object OwningProcess
  Get-Process -Id (Get-NetTCPConnection -LocalPort 5432 -State Listen).OwningProcess |
      Select-Object Id, ProcessName, Path
  ```
  Or the cross-platform one-liner:

  ```powershell
  netstat -ano | findstr :5432
  ```

  Common culprits: a locally-installed PostgreSQL service (`postgresql-x-x`),
  pgAdmin, Docker Desktop's own daemon, or a leftover container from a
  previous attempt.

- **Stop the conflicting process** (run PowerShell as Administrator for
  system services):
  ```powershell
  # Example: stop a locally-installed PostgreSQL Windows service
  Stop-Service -Name postgresql* -Force
  # Or stop the conflicting process by PID
  Stop-Process -Id <pid> -Force
  # Or stop a leftover Docker container
  docker ps --filter "publish=5432"
  docker stop <container-name>
  ```
- **Then re-run the project's own PostgreSQL:**
  ```powershell
  docker compose up -d
  docker compose ps    # should show "healthy" on `db`
  ```

> **Do not change this project's port to anything other than 5432.** The
> application code, `.env.example`, tests, and CI all assume the
> default PostgreSQL port. If you really must coexist with another
> PostgreSQL on the same host, change the *other* instance's port
> instead, or run this project's container on a different network
> interface (see Docker Desktop networking docs).

**"No module named app"**
- You forgot to activate the venv, or your IDE runs tests in a different Python. Verify with `python -c "import sys; print(sys.executable)"` and that it points inside `venv/`.

**"Target database is not up to date"**
- Follow the "Upgrading from R1" steps in section 9 to drop and recreate the schema.

**"ModuleNotFoundError: No module named 'app'" when starting uvicorn directly**
- Don't run `uvicorn src.app.main:app` raw — use `python run.py` (or `python -m uvicorn src.app.main:app` after setting `$env:PYTHONPATH='src'` in PowerShell).

**"I see a `tool-share-backend-1` or `backend-*` container but I didn't build a backend image"**
- Your `docker-compose.yml` is out of date. It no longer includes a `backend` service — the FastAPI app is run on the host via `python run.py`, not in a container.
- Pull the latest `docker-compose.yml` from the repo, then run:
  ```powershell
  docker compose up -d --remove-orphans
  ```
  This stops and removes the orphan backend container, leaving only `tool-db`.

**Docker permission denied (Linux)**
```bash
sudo usermod -aG docker $USER
```
Log out and back in for this to take effect.

**PowerShell: `Activate.ps1` blocked by execution policy**
- See the tip in section 5.

**PowerShell: `python` is not recognized**
- Python was installed but the installer wasn't told to "Add Python to PATH". Re-run the Python installer with that checkbox, or add the install directory to your PATH manually.

**`git` line endings mess up activation script**
- If `.\venv\Scripts\Activate.ps1` reports "running scripts is disabled" because of a CRLF/LF mismatch, run once:
  ```powershell
  (Get-Content .\venv\Scripts\Activate.ps1) | Set-Content -NoNewline (Get-Content .\venv\Scripts\Activate.ps1)
  ```
  This is a known Windows + Git issue. The fix above rewrites the file with the current line endings.

---

## Project structure

```
backend/
├── docker-compose.yml        # PostgreSQL service (db only — app runs on host)
├── db/init/                  # SQL init scripts run on first container start
│   └── 00-create-test-db.sql # Creates toolsharing_test database for pytest
├── media/tool_photos/        # User-uploaded photos (runtime, gitignored; served at /uploads)
├── pyproject.toml            # Python project config (ruff, mypy, pytest)
├── requirements.txt          # Python dependencies
├── run.py                    # Cross-platform `python run.py` launcher
├── scripts/
│   ├── check_db.py           # Database connectivity checker
│   ├── init_db.py            # Create all tables from ORM models (run before seed_dev.py)
│   ├── seed_dev.py           # Demo data seeder (users, categories, tools, photos)
│   ├── seed_photos/          # Tracked seed images; copied into media/tool_photos/ on `python scripts/seed_dev.py`
│   └── clean_dev.py          # Wipe all rows (keep tables)
├── src/
│   ├── __init__.py           # Marks src/ as a package (enables `python -m src.*`)
│   └── app/
│       ├── api/v1/           # REST endpoints (auth, tools, reservations, categories, messages, reports, etc.)
│       ├── core/             # Security, exceptions, timezone, logging
│       ├── db/               # Database engine and session
│       ├── models/           # SQLAlchemy ORM models (13 models)
│       ├── schemas/          # Pydantic request/response schemas
│       ├── services/         # Business logic layer
│       └── tests/            # Test suite (394 tests: 283 acceptance + 111 auxiliary)
├── .env                      # Your local environment (gitignored)
└── .env.example              # Safe template for .env
```

---

## Expected Docker containers

| Container name | Image | Purpose | Port |
|----------------|-------|---------|------|
| `tool-db` | postgres:15 | The database | 5432 → 5432 |

The FastAPI app is run directly on the host via `python run.py` (see section 11), not as a container. If `docker ps` shows a `tool-share-backend-1` container or any `backend-*` container, your compose file is out of date — pull the latest changes.
