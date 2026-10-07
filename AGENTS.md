# CRR tools monorepo

- Keep Tournament and Shifts independently runnable, deployable, versioned and tested.
- Production applications live under `apps/`; shared infrastructure and branding live under `packages/`.
- Keep app-specific domain models, authentication and database histories independent.
- Target Python 3.13, uv, FastAPI, SQLAlchemy 2, Alembic and Pydantic.
- Only extract shared infrastructure when both applications genuinely need it.
- Preserve each application's public routes, authentication behavior and user-facing Portuguese messages when changing implementation details.
- Run the affected app tests and shared-package tests before committing changes.
