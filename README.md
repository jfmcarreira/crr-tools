# CRR tools

Two independently runnable applications in one monorepo:

- [Tournament](apps/tournament/README.md): Vue 3 and FastAPI on Python 3.13.
- [Shifts](apps/shifts/README.md): FastAPI, Jinja, SQLAlchemy and Alembic on Python 3.13.
- [CRR brand](packages/crr-brand/README.md): shared logo, favicon and CSS primitives.
- [CRR Python](packages/crr-python/README.md): shared engine/threading and Alembic configuration helpers.

See [the migration plan](MONOREPO_MIGRATION_PLAN.md) and
[verified progress and baseline evidence](migration/README.md).

## Development

Requires Node 22+, Python 3.13, `uv`, and `make`.

```sh
make tournament-install
make tournament-test tournament-build
make shifts-test
make python-common-test
make test
```

`uv` resolves both backend projects using the single root `uv.lock` and creates
the root `.venv`. Each backend runs from its own directory and owns its database,
models, authentication and migration history.
Run `make tournament-backend-dev` and `make tournament-frontend-dev` in separate
terminals, or `make shifts-dev` for Shifts. App-specific environment setup is
documented in each application's README.

## Deployment

Docker Compose 2.24+ supports the optional per-app environment files:

```sh
docker compose up --build tournament
docker compose up --build shifts
```

Each service has its own Dockerfile, image, database volume, and credentials.
Set the application's secrets in its environment file before deployment.
Release tags are app-specific: `tournament-v...` and `shifts-v...`. Tag workflows
validate each app's version and publish only its image. See
[release setup and commands](docs/RELEASES.md).

## CI and releases

The configured remote uses Gitea. `.gitea/workflows/` contains path-aware CI and
independent tag-release workflows; `.github/workflows/` mirrors them for GitHub.
They use compatible contexts and git-based change detection, with shared changes
testing both consumers. `make tooling-test` verifies selection/version logic.
Remote runner execution and registry publication are pending verification.

## Baselines

`originals/` is read-only. The missing legacy source trees were recovered from
isolated copies using the saved checksums; their nested Git histories were not
available. Baseline checks
run in disposable `.migration/` copies using `make baseline-test`; production
code and CI run exclusively from `apps/`. See `migration/README.md` for fixture
and screenshot commands. Root Docker contexts exclude both the snapshots and
migration artefacts.
