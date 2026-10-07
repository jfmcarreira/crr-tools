# Tournament

Phase 1 retains the legacy Vue/Fastify application under `src/client`, `src/server`
and `src/shared`. The planned `frontend/` and Python `backend/` split follows the
API compatibility port; the current backend remains independently runnable.

Shared CRR assets and CSS come from `packages/crr-brand` through Vite's
`@crr-brand` alias. Tokens/base/components load before `src/client/styles.css`;
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
`ADMIN_PASSWORD` and `SESSION_SECRET`. The backend listens on port 8080 and Vite
on 5173. Development data is stored in `apps/tournament/tournament.sqlite`.
Use consistent `APP_BASE_PATH` and `VITE_BASE_PATH`; `/jogo/` remains the example
deployment prefix, while both support `/`.

```sh
docker compose up --build tournament
```

Compose loads `apps/tournament/.env`; `TOURNAMENT_BASE_PATH` in the root shell
controls both the frontend build path and backend path (default `/jogo/`). The
`tournament-data` volume contains `/data/tournament.sqlite`. The image is
`crr-tournament`; the current app version remains `1.0.0` in `package.json`.

Run checks with Node 22+; the CI/container target is Node 22. The legacy package
has no lint script. Its tests cover HTTP/auth/SSE/sub-path behavior and the
deterministic tournament services. Python migration fixtures live in
`migration/fixtures/` at the repository root.
