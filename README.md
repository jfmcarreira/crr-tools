# CRR tools

Two independently runnable applications in one monorepo:

- [Tournament](apps/tournament/README.md): Vue 3 and FastAPI on Python 3.13.
- [Shifts](apps/shifts/README.md): FastAPI, Jinja, SQLAlchemy and Alembic on Python 3.13.
- [CRR brand](packages/crr-brand/README.md): shared logo, favicon and CSS primitives.
- [CRR Python](packages/crr-python/README.md): shared engine/threading and Alembic configuration helpers.
- [TTLock](packages/ttlock/README.md): standalone lock API client and diagnostic CLI, consumed by Shifts.

## Development

Requires Node 22+, Python 3.13, `uv`, and `make`.

```sh
make tournament-install
make tournament-test tournament-build
make shifts-test
make python-common-test
make ttlock-test
make test
```

`uv` resolves both backend projects using the single root `uv.lock` and creates
the root `.venv`. Each backend runs from its own directory and owns its database,
models, authentication and Alembic history.

Run `make tournament-backend-dev` and `make tournament-frontend-dev` in separate
terminals, or `make shifts-dev` for Shifts. Both servers load `.env` from the
repository root, regardless of their working directory. Copy `.env.example` to
`.env` and configure the secrets for the apps you run. Environment variables
override file values; database paths remain relative to each server's working
directory. Tournament's Vite frontend also reads the root file, exposing only
`VITE_`-prefixed values to browser code. App-specific settings are documented
in each application's README.

Local Make dev/debug targets create repository-root `data/shifts/` and
`data/tournament/` and explicitly use their independent SQLite files, overriding
database settings in `.env`. Existing databases at older paths are not moved.
Automated tests continue to use isolated temporary databases.

## Deployment

Docker Compose 2.24+ loads the same optional repository-root `.env` for both apps:

```sh
docker compose up --build tournament
docker compose up --build shifts
```

Each service has its own Dockerfile, image, database volume and credentials.
Set the application's secrets in the root `.env` before deployment. Compose
injects the values as environment variables; the file is not copied into images.
Release tags are app-specific: `tournament-v...` and `shifts-v...`. Tag workflows
validate each app's version and publish only its image. See
[release setup and commands](docs/RELEASES.md).

## CI and releases

GitHub Actions live under `.github/workflows/`. CI runs on pushes to `main`, pull
requests and manual dispatch, using git-based change detection to select affected
apps; shared changes test both consumers. Independent app-tag releases publish
images to the configured container registry. `make tooling-test` verifies
selection and release-version logic.
