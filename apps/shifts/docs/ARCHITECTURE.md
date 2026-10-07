# Architecture

## Runtime

Single FastAPI process with server-rendered HTML and a SQLite database volume. This keeps deployment suitable for a small VPS, NAS or home server.

For local development, `make dev` prepares the host virtualenv and default `data/` directory, then runs Uvicorn on `127.0.0.1:8000` with auto-reload for `app/`. Override the port with `make dev PORT=8001`. The app uses environment/`.env` settings and performs migrations and initial seeding during startup, just as it does in production.

## Layers

- `models.py`: persistence schema.
- `migrations/`: one Alembic revision, `0001_initial`, holding the whole schema (the history was squashed for a test environment). The app upgrades to `head` on start, and an existing database is adopted by stamping `head`; a database created before Alembic existed has no stamp and is adopted at the baseline.
- `scheduling.py`: deterministic month/rotation generation.
- `web.py`: authentication, admin editing and change-request orchestration.
- `notifications.py`: synchronous SMTP adapter + durable send log.
- `pdf.py`: ReportLab-rendered A4 schedule lists, with embedded Unicode fonts and
  adaptive layout to keep the selected range on one page.
- `cli.py`: maintenance commands that can be run manually or by cron.

## Data lifecycle

1. Visiting a month calls `ensure_month_assignments`.
2. Missing Night rows use the repeating monthly pattern, or remain unassigned for unconfigured days.
3. Missing lunch rows are created from each independent rotation.
4. Admin assigns/overrides rows on each schedule's own configuration page (the night pattern, or a lunch month view).
5. Member change requests operate on concrete assignment IDs.
6. Email is attempted after the database action commits.

## Deployment

`Dockerfile` provides a `production` target (the default) and a `dev` target with development dependencies and Uvicorn auto-reload. Both serve `app.main:app` on port 8000. `compose.yaml` is a minimal deployment example: it builds the production target, loads `.env`, publishes `${PORT:-8000}`, and mounts `${DATA_DIR:-./data}` at `/app/data`. It fixes the container database URL to the SQLite file on that mount; default backups also live there. See [the deployment guide](../README.md#run-with-docker-compose) for setup commands.

Maintenance commands are provided by `python -m app.cli`: `init-db`, `migrate`, `seed-demo`, `db-shell`, and `send-reminders`. Settings come from environment variables and `.env` through `app/config.py`.

`alembic.ini` supplies migration paths and logging configuration. The actual database URL comes from application settings, configured programmatically in `app/database.py` and reused by `migrations/env.py`.

For larger installations, the SQLAlchemy configuration can point to PostgreSQL, but the project intentionally ships only the SQLite deployment path today.

## Testing

Run `make test` on the host. It creates/reuses `.venv`, installs development dependencies, and invokes pytest; it needs no running application or container. `pyproject.toml` limits discovery to `tests/`. HTTPX supports FastAPI `TestClient` tests, and pypdf verifies PDF downloads. Fixtures configure temporary SQLite storage before importing the app, disable SMTP, run migrations and clean up after the suite. See [the testing guide](../README.md#run-tests).
