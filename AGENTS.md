# CRR tools monorepo

- Keep Tournament and Shifts independently runnable, deployable, versioned and tested.
- Production applications live under `apps/`; shared infrastructure and branding live under `packages/`.
- Keep app-specific domain models, authentication and database histories independent.
- Target Python 3.13, uv, FastAPI, SQLAlchemy 2, Alembic and Pydantic.
- Only extract shared infrastructure when both applications genuinely need it.
- Preserve each application's public routes, authentication behavior and user-facing Portuguese messages when changing implementation details.
- Run the affected app tests and shared-package tests before committing changes.
- Exception: when changes are limited to UI/frontend files, no test runs are
  required. This overrides app-specific test-run instructions for that scope;
  check the affected UI manually instead. Backend or shared-package changes
  still require the relevant tests.
- Do not add automated tests for UI design or presentation-only changes (spacing,
  colors, dimensions, layout, scroll styling, or CSS classes). Do not assert exact
  CSS declarations or HTML markup just to lock in a visual design. Check these
  changes manually; keep automated tests focused on behavior, domain rules,
  security, data integrity and functional contracts.
