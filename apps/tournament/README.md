# Tournament

The FastAPI backend lives in `backend/app`, with app-specific SQLAlchemy models,
Alembic history, Pydantic schemas, domain services and routers. Vue lives in
`frontend/src` with its existing `/api/...` contract. The frontend owns its
`package.json`, lockfile, Vite config and strict TypeScript config. Built SPA
assets are in `frontend/dist` and served by the Python backend.

Shared CRR assets and CSS come from `packages/crr-brand` through Vite's
`@crr-brand` alias. Tokens/base/components load before `frontend/src/styles.css`;
the app owns its responsive layout and print-card dimensions. Vite's public
asset directory uses the canonical package, including the favicon.

From the repository root:

```sh
make tournament-install
make tournament-test
make tournament-build
make tournament-backend-dev
# In another terminal:
make tournament-frontend-dev
```

Copy `apps/tournament/.env.example` to `apps/tournament/.env` and configure
`ADMIN_PASSWORD` and `SESSION_SECRET`. Uvicorn listens on port 8080 and Vite
on 5173. Development data is stored in `apps/tournament/tournament.sqlite`.
Use consistent `APP_BASE_PATH` and `VITE_BASE_PATH`; `/jogo/` remains the example
deployment prefix, while both support `/`.

```sh
docker compose up --build tournament
```

Compose loads `apps/tournament/.env`; `TOURNAMENT_BASE_PATH` in the root shell
controls both the frontend build path and backend path (default `/jogo/`). The
`tournament-data` volume contains `/data/tournament.sqlite`. The image is
`crr-tournament`; app version `1.0.0` is recorded in the frontend package and
backend project metadata. The image builds Vue with Node 22 and runs Python 3.13
as UID/GID 1000, matching the old container's database ownership.

Both backends consume the internal `crr-python` workspace dependency for
synchronous engine construction and Alembic configuration. Tournament owns its
connection pragmas, legacy-schema validation and transactional adoption policy.
Production installs the shared package as a wheel inside the image.

Tests require Node 22+ and uv. `make tournament-test` runs 72 native backend pytest
scenarios, frontend tests and Vue typechecking. Native service/router tests include
the 44 scenarios previously executed through temporary legacy transports, including
a real HTTP/SSE server. `make tournament-compat-test` selects compatibility tests.
CI uses Node 22/Python 3.13 and runs from `apps/`. Node backend code/config and
dependencies have been retired; the original source baseline is under `originals/`.

For an independent release, update this app's backend project version and
`frontend/package.json`/lockfile together, then use a `tournament-vX.Y.Z` tag.
The release workflow verifies versions and publishes only the Tournament image.
See `docs/RELEASES.md` at the repository root for registry and runner setup.

## Existing SQLite data

Startup upgrades empty databases with Alembic. Pre-Alembic databases are validated
against all nine legacy tables, columns, defaults, checks, unique/index definitions
and foreign keys before being stamped at `0001_baseline`. Adoption preserves
their schema and rows; there is no export/import. An incompatible schema stops
startup before stamping. SQLite foreign keys, WAL and a 5000 ms busy timeout are
configured on every connection. Migration/stamp operations are transactional.

Keep `SESSION_SECRET` unchanged during cut-over so existing HMAC/base64url admin
sessions remain valid. Cookie name/path, HttpOnly, Strict SameSite, HTTPS behavior
and seven-day lifetime are preserved. `TRUST_PROXY` controls forwarded headers.
Deployments under `/jogo/` retain the legacy proxy-prefix stripping behavior.
