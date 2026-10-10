# Shifts

- Preserve Portuguese messages, Jinja templates, form fields, routes, session auth,
  CSRF, `ROOT_PATH` deployment, existing SQLite data, and Alembic history.
- Backend commands run from `server/`; Python application code belongs in
  `server/app/`. Server-rendered Jinja templates and browser assets belong in
  `ui/templates/` and `ui/static/`, separate from backend/domain logic.
- `services/` owns bootstrap, scheduling, calendar feeds, notifications and PDF
  rendering. `models/` contains app-specific persistence classes; its package
  exports the established model names.
- `routers/` is split by auth/account/calendar/exports/dashboard/swaps and admin
  responsibility. Shared request/session/CSRF/flash/context helpers belong in
  `routers/dependencies.py`; password and token primitives belong in `security/`.
- Preserve manual/swapped assignments, atomic swaps, and commit-before-email rules.
- Always enforce the configured scheduling horizon for upcoming assignment lists,
  calendars and shift selectors, including “Meus dias”: today through
  `scheduling_horizon()`, inclusive. Reuse `scheduling_horizon()` and
  `in_scheduling_window()` rather than hard-coding maximum dates. Keep explicitly
  historical views separate; existing out-of-window assignments remain read-only.
- Run `make shifts-test` from the repository root after relevant changes.
- Version and release this application independently using `shifts-v...` tags.
