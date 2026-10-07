# CRR tools monorepo

- Follow `MONOREPO_MIGRATION_PLAN.md`; record verified progress in `migration/README.md`.
- `originals/` contains read-only legacy snapshots. Never edit, rename, or delete
  their files, including their nested Git repositories. Run baseline checks in
  isolated copies to keep dependency installation and build outputs outside them.
- Production code lives in `apps/` and must never import from `originals/`.
- Keep the applications independently runnable, deployable, versioned, and tested.
- Preserve routes, authentication, Portuguese messages, and SQLite data during
  structural changes. Keep domain models and authentication app-specific.
- Target Python 3.13, uv, FastAPI, SQLAlchemy 2, Alembic, and Pydantic.
- Only extract shared infrastructure after both applications demonstrate the need.
- Report checks and migration blockers accurately; do not mark a phase complete
  until its exit criteria have been verified.
