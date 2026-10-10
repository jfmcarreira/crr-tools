# Tournament

The FastAPI backend lives in `backend/app`, with app-specific SQLAlchemy models,
Alembic history, Pydantic schemas, domain services and routers. Vue lives in
`frontend/src` and communicates with the backend through `/api/...`. Built SPA
assets are in `frontend/dist` and served by the Python backend.

Shared CRR assets and CSS come from `packages/crr-brand` through Vite's
`@crr-brand` alias. Tokens/base/components load before `frontend/src/styles.css`;
the app owns its responsive layout and print-card dimensions. Vite's public
asset directory uses the canonical shared package, including the favicon.

From the repository root:

```sh
make tournament-install
make tournament-test
make tournament-build
make tournament-backend-dev
# In another terminal:
make tournament-frontend-dev
```

Copy the repository-root `.env.example` to `.env` and configure
`ADMIN_PASSWORD` and `SESSION_SECRET` (at least 32 random characters; the app
refuses to start while either is empty). Uvicorn listens on port 8080 and Vite on
5173. `make tournament-backend-dev` creates repository-root `data/tournament/`
and stores development data in `data/tournament/tournament.sqlite`, overriding
`DATABASE_PATH` from `.env`. Existing databases at older paths are not moved.
Use consistent `APP_BASE_PATH` and `VITE_BASE_PATH`; `/jogo/` is the example
deployment prefix, while both also support `/`.

```sh
docker compose up --build tournament
```

Compose loads the repository-root `.env`; `TOURNAMENT_BASE_PATH` in that file or the shell
controls both the frontend build path and backend path (default `/jogo/`). The
`tournament-data` volume contains `/data/tournament.sqlite`. The image is
`crr-tournament`; app version `1.0.0` is recorded in the frontend package and
backend project metadata. The image builds Vue with Node 22 and runs Python 3.13
as UID/GID 1000.

The backend consumes the internal `crr-python` workspace dependency for
synchronous engine construction and Alembic configuration. Tournament owns its
SQLite connection pragmas, database schema and migration history.

Tests require Node 22+ and uv. `make tournament-test` runs backend pytest tests,
frontend tests and Vue typechecking. The backend suite includes route, service,
security, database and real HTTP/SSE integration coverage. CI runs from `apps/`
and builds the production image after tests pass.

For an independent release, update this app's backend project version and
`frontend/package.json`/lockfile together, then use a `tournament-vX.Y.Z` tag.
The release workflow verifies versions and publishes only the Tournament image.
See `docs/RELEASES.md` at the repository root for registry and runner setup.

## Database

Startup applies Alembic revisions through `head`. SQLite foreign keys, WAL and a
5000 ms busy timeout are configured on every connection. Schema changes should
be introduced as new Alembic revisions; do not edit revisions that have already
been released.

`SESSION_SECRET` signs the admin session cookie. Cookie path follows
`APP_BASE_PATH`; HttpOnly, Strict SameSite, HTTPS behavior and the seven-day
lifetime are configured by the backend. `TRUST_PROXY` controls forwarded-header
handling.
