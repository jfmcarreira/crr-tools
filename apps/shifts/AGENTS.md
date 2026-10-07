# Shifts

- Preserve Portuguese messages, Jinja templates, form fields, routes, session auth,
  CSRF, `ROOT_PATH` deployment, existing SQLite data, and Alembic history.
- Backend commands run from `backend/`; production code must not import originals.
- Keep the Phase 1 service/model/router layout until the planned Phase 4 refactor.
- Preserve manual/swapped assignments, atomic swaps, and commit-before-email rules.
- Run `make shifts-test` from the repository root after relevant changes.
- Version and release this application independently using `shifts-v...` tags.
