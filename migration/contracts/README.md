# Preserved Tournament assertions

These five test files are byte-for-byte copies of the legacy HTTP and deterministic
service tests, preserved before retiring Node backend dependencies. Their source
checksums match the Phase 0 Tournament manifest.

`tools/check_tournament_compat.py` generates isolated test copies that replace
only implementation imports with migration transport adapters. All assertions
and scenarios run unchanged: 19 tests use actual FastAPI HTTP/SSE servers, and 25
invoke the real Python calendar, classification, bracket and seeding services.
The adapters depend on frontend Vitest tooling and the Python backend, with no
Fastify/better-sqlite3/Zod runtime dependency and no imports from `originals/`.

Run `make tournament-compat-test` after `make tournament-install`, or run the full
`make tournament-test`. The `--freeze` option was used once; do not overwrite
these snapshots during later refactors. Native pytest supplies database adoption,
HTTP fixture replay, authentication, validation, concurrency and SSE checks.
