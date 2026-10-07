# Tournament

- The FastAPI backend is under `backend/app`; Vue is under `frontend/src`.
  Backend commands must run from `backend/` to isolate its `app` package from Shifts.
- Alembic owns the schema. Never rewrite a released revision; add a new revision for schema changes.
- Preserve `/api/...`, camelCase payloads, Portuguese errors, session cookies, login limiting, SSE and sub-path deployment.
- Keep deterministic calendar, standings, seeding and bracket rules testable.
- Run `make tournament-test` and `make tournament-build` from the repository root.
- Version and release this application independently using `tournament-v...` tags.
