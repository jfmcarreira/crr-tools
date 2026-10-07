# CRR Python infrastructure

Internal uv workspace package, imported as `crr_common`, targeting Python 3.13.
Both applications consume it explicitly through workspace dependencies.

## Proven shared needs

- `database.create_sync_engine`: both FastAPI applications use synchronous
  SQLAlchemy and allow SQLite connections to cross request-worker threads.
  This wraps SQLAlchemy URL handling and supplies `check_same_thread=False` for
  SQLite, while forwarding caller engine options and honoring explicit connection
  arguments. Other database dialects receive no SQLite-specific arguments.
- `migrations.migration_config`: both applications create an Alembic configuration
  from their own ini file, migration directory and database setting. It resolves
  paths, escapes URL interpolation characters, and optionally attaches a caller-
  owned connection for transactional migrations.

Schema validation, revision histories, upgrades/stamps, transaction ownership,
SQLite pragmas, backups, sessions, domain models and authentication belong to
each application. The package contains no app imports, switches or domain code.
It neither opens migration connections nor runs DDL.

Run `make python-common-test` from the repository root. `make test` includes
these checks, and shared-package changes trigger both app CI jobs. Docker images
install the package as a wheel with `uv sync --no-editable`; local uv commands
use the workspace package. Its internal version is not a public release stream.
