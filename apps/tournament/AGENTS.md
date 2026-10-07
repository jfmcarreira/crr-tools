# Tournament

- Follow the root migration plan and record checks in `migration/README.md`.
- Phase 1 temporarily retains the Vue/Fastify source layout and Node backend.
- Preserve `/api/...`, camelCase payloads, Portuguese errors, session cookies,
  HMAC tokens, login limiting, SSE, and sub-path deployment during the Python port.
- Keep deterministic calendar, standings, seeding, and bracket rules testable.
- Run `make tournament-test` and `make tournament-build` from the repository root.
- Version and release this application independently using `tournament-v...` tags.
