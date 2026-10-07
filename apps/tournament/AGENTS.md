# Tournament

- Follow the root migration plan and record checks in `migration/README.md`.
- The FastAPI backend is under `backend/app`; Vue stays under `src/client` until
  final layout cleanup. Backend commands must run from `backend/` to isolate its
  `app` package from Shifts.
- Alembic owns the schema. Validate legacy databases before stamping the baseline;
  preserve SQLite rows, constraints, indexes, FKs and existing container UID 1000.
- Preserve `/api/...`, camelCase payloads, Portuguese errors, session cookies,
  HMAC tokens, login limiting, SSE, and sub-path deployment during the Python port.
- Keep deterministic calendar, standings, seeding, and bracket rules testable.
- Run `make tournament-test` and `make tournament-build` from the repository root.
- The compatibility command reuses preserved legacy assertions against real Python
  services and HTTP servers; production code must not import the legacy backend.
- Version and release this application independently using `tournament-v...` tags.
