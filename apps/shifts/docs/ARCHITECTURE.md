# Architecture

## Runtime

Single FastAPI process with server-rendered HTML and a SQLite database volume. This keeps deployment suitable for a small VPS, NAS or home server.

From the monorepo root, `make shifts-dev` prepares the backend's default `data/`
directory and runs Uvicorn on `127.0.0.1:8000` through uv, with auto-reload.
Dependencies resolve through the root `uv.lock` into the root `.venv`. Settings
come from the environment and `backend/.env`; migrations and initial seeding run
on startup, as they do in production.

## Layers

- `backend/app/models/`: persistence schema split into user, team, schedule
  (including patterns/rotation members), assignment, swap and notification
  modules. The package exports the established model names and registers all
  classes with the existing app-specific `Base`; mappings and relationships are
  preserved.
- `migrations/`: Alembic revision history. The app upgrades to `head` on start.
- `backend/app/services/`: bootstrap, deterministic scheduling, calendar feeds,
  SMTP notifications and PDF rendering.
- `backend/app/routers/`: auth, account, calendar, exports, dashboard and swaps.
  `admin/` splits teams, users, schedules, assignments and notification-log pages.
  Each domain owns its routes; the package composes their routers for `main.py`.
- `routers/dependencies.py`: session/current-user/admin checks, CSRF validation,
  flash/context, redirect and month-navigation helpers. Schedule, swap, assignment
  and user helper modules support the domains that actually share them. They do
  not import feature routers, keeping the dependency graph acyclic.
- `backend/app/security/`: the existing PBKDF2 password codec and CSRF-token
  generator. HTTP/session orchestration stays in routers.
- `services/notifications.py`: synchronous SMTP adapter + durable send log, with
  one recipient per user (not per team).
- `services/scheduling.py`: the monthly generator plus the scheduling-window
  policy. `scheduling_horizon()` and `in_scheduling_window()` define the only
  editable dates (today through the end of the 6th month ahead); every router
  that writes assignments or swaps checks them, and the shared
  `_beyond_horizon_message()` in `routers/dependencies.py` produces the refusal.
- `services/pdf.py`: ReportLab-rendered A4 schedule lists, with embedded Unicode fonts and
  adaptive layout to keep the selected range on one page.
- `backend/app/cli.py`: maintenance commands that can be run manually or by cron.
- `packages/crr-python`: shared synchronous engine/threading and Alembic-config
  construction. Each app supplies its own database setting, script location and
  migration policy; the package contains no models or authentication code.

## Data lifecycle

1. Visiting a month calls `ensure_month_assignments`.
2. Missing Night rows use the repeating monthly pattern, or remain unassigned for unconfigured days.
3. Missing lunch rows are created from each independent rotation.
4. Admin assigns/overrides rows on each schedule's own configuration page (the night pattern, or a lunch month view).
5. Member change requests operate on concrete assignment IDs.
6. Email is attempted after the database action commits.

## Deployment

`apps/shifts/Dockerfile` uses a repository-root build context, Python 3.13 and uv,
and copies the shared brand package beside the backend. It serves `app.main:app`
on port 8000. Root `compose.yaml` loads `apps/shifts/backend/.env` and mounts the
independent `shifts-data` volume at `/data`, with its database URL pointing to
`/data/bar_rota.db`; default backups live beside it. Run
`docker compose up --build shifts` from the monorepo root. See
[the application README](../README.md) for environment and CLI commands.

Maintenance commands are provided by `python -m app.cli`: `init-db`, `migrate`, `seed-demo`, `db-shell`, and `send-reminders`. Settings come from environment variables and `.env` through `app/config.py`.

`alembic.ini` supplies migration paths and logging configuration. The actual database URL comes from application settings, configured programmatically in `app/database.py` and reused by `migrations/env.py`.

For larger installations, the SQLAlchemy configuration can point to PostgreSQL, but the project intentionally ships only the SQLite deployment path today.

## Testing

Run `make shifts-test` from the monorepo root. It uses the locked uv project to
run pytest. HTTPX supports FastAPI `TestClient`; pypdf verifies downloaded
documents. Fixtures configure temporary SQLite storage before importing app
modules, disable SMTP, apply Alembic revisions and clean up afterwards.
