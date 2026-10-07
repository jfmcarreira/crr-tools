# Contínuos CRR — Shifts

The server-rendered FastAPI application lives in `backend/`. Its models,
services, security primitives and domain routers are organized separately, with
the established Jinja/form contracts and `0001_initial` Alembic history. Python
dependencies are managed with `uv` and the root `uv.lock`.

The internal `crr-python` workspace dependency supplies synchronous engine
construction and Alembic configuration. Shifts owns its sessions, backups,
startup adoption rules and migration history. Docker installs the shared package
as a wheel alongside the app's dependencies.

The canonical logo, favicon and common CSS live in `packages/crr-brand`, mounted
at `/brand` with root-path-aware Jinja links. PDF exports read that same logo.
App-specific layouts and forms remain in `backend/app/static/app.css`; Docker
copies the brand package into the image alongside the backend.

From the repository root:

```sh
make shifts-test
make shifts-dev
```

Copy `apps/shifts/.env.example` to `apps/shifts/backend/.env` and configure
`SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`, and the remaining deployment settings.
The local server listens on port 8000. Migrations, backups and initial data run
on startup; SQLite data defaults to `backend/data/bar_rota.db`. `make shifts-dev`
creates its data directory. Create that directory before using CLI initialization
directly if using the default database URL.

```sh
docker compose up --build shifts
make shifts-build
```

Compose loads `apps/shifts/backend/.env`. The `shifts-data` volume contains
`/data/bar_rota.db`; this database is independent from Tournament. The image is
`crr-shifts`, targeting Python 3.13. Initial Python project version is `0.1.0`;
future release tags use `shifts-v...`.

For administrative CLI commands:

```sh
uv run --directory apps/shifts/backend --package crr-shifts --locked python -m app.cli init-db
uv run --directory apps/shifts/backend --package crr-shifts --locked python -m app.cli seed-demo
```

The requirements files are retained during migration until CI verifies the
lockfile workflow. Tests use isolated synthetic SQLite data and disabled SMTP.
`make shifts-test` runs pytest and the Phase 4 compatibility check: ORM/schema
definitions and relationships, OpenAPI, migration history, existing data at
startup and 96 requests across `/` and `/crr`. `make shifts-compat-test` runs the
compatibility check alone. The synthetic fixture is under `migration/fixtures/`
and the expected contract under `migration/phase4/`.

See `docs/DOMAIN.md` for domain rules and `docs/ARCHITECTURE.md` for the current
module layout, application lifecycle and deployment commands.
