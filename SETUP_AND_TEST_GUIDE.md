# Group 3 — ICS 613 Setup, Run, Test & Manual Test Guide

**Team:** Group 3 — ICS 613
**Project:** Neighborhood Tool Sharing
**Stack:** FastAPI + PostgreSQL (backend) · React + Vite (frontend)

This guide gets the entire project running on a fresh machine on
**Windows, macOS, or Linux**: PostgreSQL in Docker, the FastAPI
backend, and the React frontend. It also covers the test suites and a
step-by-step manual UI walkthrough.

> **For deployment, see [Deployment_Guide.md](Deployment_Guide.md).**

> **Conventions used below**
> - `bash` code blocks run on macOS, Linux, and **Git Bash on Windows**.
> - `cmd` blocks run in `cmd.exe` (the default Windows terminal).
> - `powershell` blocks run in PowerShell.
> - Pick the block that matches your shell. If you use VS Code's
>   integrated terminal, the default is PowerShell on Windows and
>   `bash` on macOS/Linux.

---

## 1. Prerequisites

| Program | Minimum version | Check with |
|---|---|---|
| Git | 2.30+ | `git --version` |
| Python | 3.11, 3.12, or 3.13 | `python --version` (or `python3 --version`) |
| Node.js | **20.19+ or 22.12+** (required by Vite 8) | `node --version` |
| npm | 10+ | `npm --version` |
| Docker + Docker Compose | Docker 24+ | `docker --version` and `docker compose version` |

> **Windows note:** the official Python installer registers `python`
> (not `python3`) on `PATH`. Use `python` in the snippets below. Node
> 20 LTS or 22 LTS from nodejs.org works.

If any check fails, install that program before continuing.

---

## 2. Clone the repository

```bash
git clone https://github.com/ICS613-Group3/Group3-ICS613-project.git
cd Group3-ICS613-project
```

```cmd
git clone https://github.com/ICS613-Group3/Group3-ICS613-project.git
cd Group3-ICS613-project
```

All paths in this guide are relative to the repository root.

---

## 3. Start Postgres in Docker

The backend has a `docker-compose.yml` that runs **only the database**.
The FastAPI app runs on the host (not in a container) for faster
hot-reload and to avoid port conflicts.

```bash
cd backend
docker compose up -d
docker compose ps
```

```cmd
cd backend
docker compose up -d
docker compose ps
```

Wait until the `db` service shows `(healthy)` and `pgadmin` shows `(running)`.
The init script `db/init/00-create-test-db.sql` auto-creates the `toolsharing`
and `toolsharing_test` databases on first boot.

**pgAdmin (web-based database GUI)**

pgAdmin is included in the compose file. Open `http://localhost:5050` and log in with:
- Email: `admin@example.com`
- Password: `devpass123`

Then **Register → Server** and enter:
  - Name: `Toolsharing (Docker)`
  - Host: `tool-db`, Port: `5432`
  - Username: `ics613user`, Password: `ics613password`
  - Save password: Yes

> **Note:** pgAdmin takes 10–20 seconds to initialize after `docker compose up -d`.
> If `localhost:5050` is unreachable, wait a moment and refresh.

Verify connectivity:

```bash
docker exec -it tool-db psql -U ics613user -d toolsharing -c "SELECT 1;"
```

```cmd
docker exec -it tool-db psql -U ics613user -d toolsharing -c "SELECT 1;"
```

Should return `1`.

> **If the container name is different** (e.g. you set `COMPOSE_PROJECT_NAME`),
> substitute whatever `docker compose ps` shows for the `db` service.
> The default project name from `docker-compose.yml` is `tool-share`, so
> the container is `tool-db`.

---

## 4. Set up the Python backend

### 4.1 Create a virtual environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

```cmd
cd backend
python -m venv venv
venv\Scripts\activate.bat
```

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` at the start of your prompt.

### 4.2 Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4.3 Create the `.env` file

```bash
cp .env.example .env
echo "ENVIRONMENT=development" >> .env
```

```cmd
copy .env.example .env
echo ENVIRONMENT=development>> .env
```

```powershell
Copy-Item .env.example .env
Add-Content .env "ENVIRONMENT=development"
```

The `ENVIRONMENT=development` line is required so the placeholder
`SECRET_KEY` shipped in `.env.example` is accepted. In production, you
would set `ENVIRONMENT=production` and provide a real key.

### 4.4 Create database tables

```bash
python scripts/init_db.py
```

```cmd
python scripts\init_db.py
```

```powershell
python scripts/init_db.py
```

Expected: `All tables created successfully.`

### 4.5 (Optional) Load seed data

This creates 3 demo users, 5 tool categories, and 12 tool listings
with photos so you have something to log in with and browse.

```bash
SEED_PASSWORD=devpass123 python scripts/seed_dev.py
```

```cmd
set SEED_PASSWORD=devpass123
python scripts\seed_dev.py
```

```powershell
$env:SEED_PASSWORD = "devpass123"
python scripts/seed_dev.py
```

If you skip `SEED_PASSWORD`, the script generates a random 16-character
password and prints it.

The three seed users (all use the same password):

| Email | Role | Full name |
|---|---|---|
| `admin@example.com` | Admin | Admin User |
| `member01@example.com` | Owner | Demo Owner |
| `member02@example.com` | Borrower | Demo Borrower |

### 4.6 Start the backend

```bash
python run.py --port 8000
```

```cmd
python run.py --port 8000
```

```powershell
python run.py --port 8000
```

Expected: `Uvicorn running on http://0.0.0.0:8000` (or `http://127.0.0.1:8000`).

Verify from a second terminal:

```bash
curl http://localhost:8000/api/v1/health
# Returns: {"status":"ok"}
```

```cmd
curl http://localhost:8000/api/v1/health
REM Returns: {"status":"ok"}
```

```powershell
(Invoke-WebRequest http://localhost:8000/api/v1/health).Content
# Returns: {"status":"ok"}
```

Interactive API documentation is at `http://localhost:8000/docs`.

> **Windows + curl:** `curl.exe` ships with Windows 10+ and Windows 11.
> On older Windows builds you may need to install it or use the
> PowerShell `Invoke-WebRequest` example instead.

---

## 5. Set up the frontend

Open a **second terminal**. Leave the backend running in the first.

```bash
cd frontend
npm install
```

```cmd
cd frontend
npm install
```

```powershell
cd frontend
npm install
```

> The first install takes a couple of minutes. `npm install` works
> identically on all three platforms.

### 5.1 Start the dev server

```bash
npm run dev
```

```cmd
npm run dev
```

```powershell
npm run dev
```

Vite starts on `http://localhost:5173` and proxies `/api/*` to
`http://localhost:8000` (configured in `vite.config.ts`). This means the
frontend can call `/api/v1/tools` and it will reach the backend without
CORS issues — and the same code works in production when both are
served from the same origin.

Verify the proxy from a third terminal:

```bash
curl http://localhost:5173/api/v1/health
# Returns: {"status":"ok"}   (Vite forwarded the call to the backend)
```

```cmd
curl http://localhost:5173/api/v1/health
REM Returns: {"status":"ok"}
```

```powershell
(Invoke-WebRequest http://localhost:5173/api/v1/health).Content
# Returns: {"status":"ok"}
```

If you get a 502 Bad Gateway, the backend isn't running. Go back to
step 4.6.

> **Port already in use:** run `npm run dev -- --port 5174` to use a
> different port. Remember to also add the new origin to
> `backend/.env` `CORS_ORIGINS` if you want to bypass the proxy.

---

## 6. End-to-end smoke test (curl)

The frontend uses the Vite proxy, so these calls all go through
`http://localhost:5173`. If you want to hit the backend directly,
substitute `http://localhost:8000` for `http://localhost:5173`.

**bash / Git Bash (macOS, Linux, Windows):**

```bash
# Login as the owner user
LOGIN=$(curl -sS -X POST http://localhost:5173/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"member01@example.com","password":"devpass123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "Token: ${TOKEN:0:30}..."

# Authenticated call — /auth/me
curl -sS http://localhost:5173/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List tools
curl -sS "http://localhost:5173/api/v1/tools?page_size=3" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Unauthenticated call — should return 401
curl -sS -o /dev/null -w "status: %{http_code}\n" \
  http://localhost:5173/api/v1/tools
```

**cmd (Windows):**

```cmd
curl -sS -X POST http://localhost:5173/api/v1/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"member01@example.com\",\"password\":\"devpass123\"}" > login.json

REM cmd doesn't have a built-in JSON parser. Use Python:
python -c "import json; print(json.load(open('login.json'))['access_token'])" > token.txt
set /p TOKEN=<token.txt
del login.json token.txt
```

(The interactive UI walkthrough in section 7 is faster for Windows
users — it does the same calls through the browser.)

**PowerShell (Windows):**

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:5173/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"email":"member01@example.com","password":"devpass123"}'
$token = $login.access_token

Write-Host "Token: $($token.Substring(0, 30))..."

# Authenticated call
Invoke-RestMethod -Headers @{ Authorization = "Bearer $token" } `
  -Uri http://localhost:5173/api/v1/auth/me | Format-List

# List tools
Invoke-RestMethod -Headers @{ Authorization = "Bearer $token" } `
  -Uri "http://localhost:5173/api/v1/tools?page_size=3" | Format-List

# Unauthenticated call
$code = (Invoke-WebRequest http://localhost:5173/api/v1/tools -UseBasicParsing).StatusCode
Write-Host "status: $code"
```

Expected:
- `/auth/me` returns the user's profile (email, full_name, status, etc.)
- `/tools` returns a `PaginatedResponse` with 12 items
- Unauthenticated `/tools` returns `status: 401`

---

## 7. Manual UI test

Open `http://localhost:5173` in your browser.

### 7.1 Login flow
1. You'll be redirected to `/login`.
2. Enter `member01@example.com` / `devpass123`.
3. Click **Login**.
4. You should be redirected to `/dashboard` showing "Welcome, Demo Owner".

### 7.2 Verify the dashboard
- Four summary cards: Tools in catalog, My active reservations,
  My completed or closed, Unread notifications.
- After seeding, expect: 12 tools, 0 reservations, a few unread
  notifications (counts may differ once you've done some testing).
- Top-right shows the user name and a **Logout** button.
- The dashboard has **no mock banner** — there is no mock mode; the
  frontend always talks to the real backend through the Vite proxy.

### 7.3 Browse Tools flow
1. Click **Browse Tools** in the top nav.
2. You should see 12 tool cards in a grid.
3. Each card shows: photo, category, rating, name, description, owner,
   condition.
4. Try the filters (they fire automatically after a 200ms debounce):
   - Select category "Power Tools" → 2 tools.
   - Type "drill" in search → 1 tool (Cordless Drill).
   - Click **Clear Filters** to reset.

### 7.4 Tool Detail flow
1. Click **View Details** on any tool.
2. Shows the tool photo, full description, owner, condition, status.
3. If the tool is active and not yours, the right side shows a
   **Reservation Request** form.
4. Pick a start date and end date, click **Submit Reservation
   Request**.
5. Success message: "Reservation request submitted. Status: REQUESTED."
6. Navigate away and back — the form starts empty, the tool still
   shows as available.

### 7.5 Reservations flow
1. Click **Reservations** in the top nav.
2. Lists reservations with status badges (REQUESTED, APPROVED,
   PICKED_UP, RETURNED, etc.).
3. Use the **role filter** dropdown to view "As Borrower" or
   "As Owner".
4. Click **View Reservation** on any reservation.
5. Shows workflow progress and action buttons (Owner Approve, Cancel,
   Confirm Pickup, Confirm Return) based on:
   - Current reservation state
   - Whether you're the borrower or owner

### 7.6 Returned Tools / Reviews flow
1. **Reservations** → **View Reservation** on a RETURNED one, or
   **Browse Tools → Returned Tools** in the nav dropdown.
2. Click **Leave a Review** / **Review This Reservation**.
3. Submit a 1–5 rating with an optional comment.
4. Navigate to **Review History** in the top nav to see it listed as
   "Given" (or "Received" from the other party's perspective).

### 7.7 Admin flows (login as admin@example.com / devpass123)
1. **Admin Members** — list all members, suspend/reactivate accounts.
2. **Admin Invites** — create and manage invite tokens (US33).
3. **Admin Listings** — deactivate/reactivate tool listings (US11).
4. **Reported Listings** — review member-reported listings (US27).
5. **Categories** — add/remove tool categories (US28).
6. **Admin Reservations** — view all active reservations (US34).
7. **Member Moderation Profiles** — view all members with violation counts, suspend/reactivate (US29/30/31).
8. **Moderation History** — audit log of all moderation actions (US32).
9. **Moderation Reports** — generate and export moderation reports (US33).

### 7.8 My Tools flow (login as member01@example.com)
1. Click **My Tools** in the nav dropdown under Browse Tools.
2. Shows your own tool listings with status, rating, and edit links.

### 7.9 Messaging flow
1. Navigate to a reservation that is REQUESTED, APPROVED, or PICKED_UP.
2. Click **Messages** or navigate to `/reservations/:id/messages` (US22).
3. Send and receive messages in the thread.
4. Messages are read-only for RETURNED/CANCELLED reservations.

### 7.10 Report Listing flow
1. Navigate to any tool detail page (not your own tool).
2. Click **Report Listing** button.
3. Select a reason, optionally add a comment, and submit.

### 7.11 Logout flow
1. Click **Logout** in the top nav.
2. Redirects to `/login`.
3. Try to navigate to `/dashboard` directly → redirects back to
   `/login`.

### 7.12 401 / token-refresh handling
1. Open DevTools → Network tab.
2. Log out, then try to navigate to `/tools`.
3. You should be redirected to `/login`.
4. The frontend's `client.ts` will have attempted a one-shot
   refresh-token rotation before giving up — visible in Network as a
   `/auth/refresh` request that returned 401, followed by the original
   request.

---

## 8. Run the test suites

### 8.1 Backend tests (pytest)

```bash
cd backend
source venv/bin/activate   # or the Windows alternative
pytest src/app/tests/ -q
```

```cmd
cd backend
venv\Scripts\activate.bat
pytest src\app\tests -q
```

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest src/app/tests -q
```

Expected: all tests pass (currently 399 tests: 288 acceptance + 111 auxiliary).

### 8.2 Frontend checks

```bash
cd frontend
npm run lint
npx tsc -b
npm run build
```

```cmd
cd frontend
npm run lint
npx tsc -b
npm run build
```

```powershell
cd frontend
npm run lint
npx tsc -b
npm run build
```

Expected: all clean, build succeeds. `npx tsc -b` only does a type
check (no emit); `npm run build` does the full production bundle.

---

## 9. Stop everything

```bash
# Stop the frontend (Ctrl+C in its terminal)
# Stop the backend  (Ctrl+C in its terminal)

# Stop the database when done for the day
cd backend
docker compose stop     # keeps data — start again with `docker compose start`
# docker compose down   # also fine, containers removed but data survives
# docker compose down -v  # ⚠️ DANGER — deletes ALL database data permanently
```

---

## 10. Reset everything (clean slate)

**bash / Git Bash:**

```bash
# Backend
cd backend
docker compose down -v
docker compose up -d
source venv/bin/activate
python scripts/init_db.py
SEED_PASSWORD=devpass123 python scripts/seed_dev.py
python run.py --port 8000

# Frontend (separate terminal)
cd ../frontend
rm -rf node_modules dist
npm install
npm run dev
```

**cmd:**

```cmd
cd backend
docker compose down -v
docker compose up -d
venv\Scripts\activate.bat
python scripts\init_db.py
set SEED_PASSWORD=devpass123
python scripts\seed_dev.py
python run.py --port 8000

REM Frontend (separate terminal)
cd ..\frontend
rmdir /s /q node_modules dist
npm install
npm run dev
```

**PowerShell:**

```powershell
# Backend
cd backend
docker compose down -v
docker compose up -d
.\venv\Scripts\Activate.ps1
python scripts/init_db.py
$env:SEED_PASSWORD = "devpass123"
python scripts/seed_dev.py
python run.py --port 8000

# Frontend (separate terminal)
cd ../frontend
Remove-Item -Recurse -Force node_modules, dist
npm install
npm run dev
```

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `Address already in use` on port 5432 | Stop your local Postgres service or another container using that port |
| `SECRET_KEY looks like a dev placeholder` at backend startup | Make sure `backend/.env` contains `ENVIRONMENT=development` |
| `Cannot connect to database` | Run `docker compose ps` — wait for `(healthy)`. May take 10-30s after `up -d` |
| `CORS error` in browser console | You bypassed the Vite proxy (or hit the backend from a non-allowed origin). Use relative paths (`/api/v1/...`). To call the backend directly, add your origin to `CORS_ORIGINS` in `backend/.env` and restart the backend. |
| Login fails with "Invalid email or password" | You didn't run the seed script. Re-run `SEED_PASSWORD=devpass123 python scripts/seed_dev.py` |
| `429 Too Many Requests` on `/auth/login` | Rate limiter blocked you (5/minute). Wait 60s and try again |
| Port 5173 in use | Run `npm run dev -- --port 5174` to use a different port. If you also need to bypass the proxy, add the new origin to `CORS_ORIGINS`. |
| Port 8000 in use | Run `python run.py --port 8001`. Then update `proxy.target` in `frontend/vite.config.ts` to match. |
| `Module not found 'app'` when starting uvicorn directly | Use `python run.py` (which sets `PYTHONPATH=src` for you) instead of `uvicorn src.app.main:app` from the system shell |
| `npm install` fails on Windows with "gyp ERR! find Python" | A native build script needs Python on `PATH`. Install the Microsoft C++ Build Tools and Python 3, or skip the optional native build. |
| Frontend shows an empty page and console has CORS errors | Backend isn't running, OR you're hitting the backend on a port the backend's `CORS_ORIGINS` doesn't include. |
| Container name isn't `tool-db` | Check `docker compose ps` for the actual name; use that in `docker exec` commands. |

---

## 12. Quick reference

| What | Where | Command |
|---|---|---|
| Database | Docker on host | `cd backend && docker compose up -d` |
| Backend | `backend/` | activate venv then `python run.py --port 8000` |
| Frontend | `frontend/` | `npm install` (once), then `npm run dev` |
| Backend tests | `backend/` | activate venv then `pytest src/app/tests/ -q` |
| Frontend checks | `frontend/` | `npm run lint && npx tsc -b && npm run build` |
| API docs | `http://localhost:8000/docs` | open in browser |
| Health check (backend) | — | `curl http://localhost:8000/api/v1/health` |
| Health check (via proxy) | — | `curl http://localhost:5173/api/v1/health` |
| pgAdmin (DB GUI) | `http://localhost:5050` | `admin@example.com` / `devpass123` |

| Login | Email | Password |
|---|---|---|
| Admin | `admin@example.com` | `devpass123` |
| Owner | `member01@example.com` | `devpass123` |
| Borrower | `member02@example.com` | `devpass123` |

---

*Last updated: 2026-08-06. Merged main (acceptance/ + auxiliary/ restructure) with Integrated_frontend_backend; test counts verified after merge.*
