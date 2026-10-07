# Shifts

- Preserve Portuguese messages, Jinja templates, form fields, routes, session auth,
  CSRF, `ROOT_PATH` deployment, existing SQLite data, and Alembic history.
- Backend commands run from `backend/`; production code must not import originals.
- `services/` owns bootstrap, scheduling, calendar feeds, notifications and PDF
  rendering. `models/` contains app-specific persistence classes; its package
  exports the established model names.
- `routers/` is split by auth/account/calendar/exports/dashboard/swaps and admin
  responsibility. Shared request/session/CSRF/flash/context helpers belong in
  `routers/dependencies.py`; password and token primitives belong in `security/`.
- Preserve manual/swapped assignments, atomic swaps, and commit-before-email rules.
- Run `make shifts-test` from the repository root after relevant changes.
- Version and release this application independently using `shifts-v...` tags.
