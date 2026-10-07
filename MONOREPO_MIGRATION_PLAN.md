# CRR Apps Monorepo Migration Plan

## Fixed decisions

- One monorepo, two independently deployable applications.
- Python 3.13 for both backends.
- FastAPI + SQLAlchemy 2 + Alembic + Pydantic.
- `uv` + `pyproject.toml` with one root `uv.lock`.
- Tournament keeps its Vue 3 frontend and its existing `/api/...` contract.
- Shifts remains server-rendered with Jinja.
- Auth models remain app-specific; only proven low-level helpers may be shared later.
- Separate SQLite databases and separate Alembic histories.
- Separate Docker images and independent app versions/releases.
- Shared CRR branding, not shared domain models.
- CI builds/tests only affected apps and packages that can affect them.

## Original source baseline

All migration work is sourced from the untouched legacy code under `originals/`:

```text
originals/
├── tournment-manager-web/
└── crr-shifts/
```

The file map and later sections retain the original proposal's source labels.
Resolve `original/tournament-manager/` to `originals/tournment-manager-web/` and
`original/crr-shifts/` to `originals/crr-shifts/` in this workspace. These are path
aliases only; do not rename the snapshots. Verified progress is recorded in
`migration/README.md`.

Rules for `originals/`:

- Treat it as read-only reference source throughout the migration.
- Never move, rename, delete, reformat or update files in `originals/` as part of the migration.
- New monorepo code is created by copying, porting or rewriting from `originals/...` into `apps/...` and `packages/...`.
- Behaviour/compatibility checks compare the migrated app against the corresponding code in `originals/`.
- Runtime code must never import from `originals/`.
- Add `originals/` to the root `.dockerignore` so legacy sources are not sent into Docker build contexts.
- CI path filters do not build/deploy from `originals/`; it exists only as the migration baseline.

## Target repository

```text
crr-apps/
├── .dockerignore
├── .gitignore
├── .python-version                 # 3.13
├── AGENTS.md                       # repository-wide rules only
├── README.md
├── Makefile
├── compose.yaml
├── pyproject.toml                  # uv workspace only
├── pyrightconfig.json
├── uv.lock
│
├── original/                         # read-only legacy baseline
│   ├── tournament-manager/
│   └── crr-shifts/
│
├── apps/
│   ├── tournament/
│   │   ├── .env.example
│   │   ├── AGENTS.md
│   │   ├── Dockerfile
│   │   ├── README.md
│   │   ├── backend/
│   │   │   ├── alembic.ini
│   │   │   ├── pyproject.toml
│   │   │   ├── app/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py
│   │   │   │   ├── database.py
│   │   │   │   ├── errors.py
│   │   │   │   ├── events.py
│   │   │   │   ├── main.py
│   │   │   │   ├── models/
│   │   │   │   ├── routers/
│   │   │   │   │   ├── auth.py
│   │   │   │   │   ├── public.py
│   │   │   │   │   └── admin/
│   │   │   │   │       ├── settings.py
│   │   │   │   │       ├── display.py
│   │   │   │   │       ├── groups.py
│   │   │   │   │       ├── teams.py
│   │   │   │   │       ├── calendar.py
│   │   │   │   │       ├── matches.py
│   │   │   │   │       └── final_stage.py
│   │   │   │   ├── schemas/
│   │   │   │   ├── security/
│   │   │   │   │   ├── session.py
│   │   │   │   │   └── rate_limit.py
│   │   │   │   └── services/
│   │   │   │       ├── bracket.py
│   │   │   │       ├── calendar.py
│   │   │   │       ├── classification.py
│   │   │   │       └── state.py
│   │   │   ├── migrations/
│   │   │   │   └── versions/
│   │   │   │       └── 0001_baseline.py
│   │   │   └── tests/
│   │   └── frontend/
│   │       ├── index.html
│   │       ├── package.json
│   │       ├── package-lock.json
│   │       ├── tsconfig.json
│   │       ├── vite.config.ts
│   │       └── src/
│   │
│   └── shifts/
│       ├── .env.example
│       ├── AGENTS.md
│       ├── Dockerfile
│       ├── README.md
│       ├── docs/
│       └── backend/
│           ├── alembic.ini
│           ├── pyproject.toml
│           ├── app/
│           │   ├── __init__.py
│           │   ├── cli.py
│           │   ├── config.py
│           │   ├── database.py
│           │   ├── i18n.py
│           │   ├── main.py
│           │   ├── models/
│           │   ├── routers/
│           │   │   ├── auth.py
│           │   │   ├── account.py
│           │   │   ├── calendar.py
│           │   │   ├── dashboard.py
│           │   │   ├── exports.py
│           │   │   ├── swaps.py
│           │   │   └── admin/
│           │   │       ├── teams.py
│           │   │       ├── users.py
│           │   │       ├── schedules.py
│           │   │       ├── assignments.py
│           │   │       └── notifications.py
│           │   ├── security/
│           │   ├── services/
│           │   ├── static/
│           │   └── templates/
│           ├── migrations/
│           └── tests/
│
└── packages/
    ├── crr-brand/
    │   ├── README.md
    │   ├── assets/
    │   │   ├── logo.png
    │   │   └── favicon.png
    │   └── styles/
    │       ├── tokens.css
    │       ├── base.css
    │       └── components.css
    │
    └── crr-python/
        ├── README.md
        ├── pyproject.toml
        └── src/crr_common/
            └── __init__.py
```

`crr-python` starts intentionally small. Do not extract helpers just because two apps use Python. Extract code only after both apps have the same concrete need.

## Common backend conventions

Both backends should use the same structural rules even where code is not shared:

- `config.py`: Pydantic Settings only.
- `database.py`: engine/session wiring and app-specific migration startup.
- `models/`: persistence only; no HTTP concerns.
- `schemas/`: request/response models where JSON APIs exist.
- `routers/`: HTTP orchestration and dependency checks, kept thin.
- `services/`: deterministic/domain operations.
- `security/`: app-specific authentication primitives.
- `tests/`: mirrors services/routers and tests observable behaviour.
- SQLAlchemy 2-style `select()` and typed `Mapped[...]` models.
- Alembic owns schema creation/evolution; no schema DDL embedded in application startup code.

### Tournament JSON compatibility

The Python rewrite must preserve the existing Vue contract exactly:

- Same route paths and HTTP methods.
- Same status codes.
- Same `{ "error": "..." }` error shape and, where tests depend on them, the same Portuguese error messages.
- Same camelCase JSON field names. Python uses snake_case internally and Pydantic aliases at the API boundary.
- Same `tournament_admin_session` cookie name, path semantics, `HttpOnly`, `SameSite=Strict`, secure behaviour and seven-day lifetime.
- Reproduce the current HMAC-SHA256/base64url session token format so sessions survive the backend cut-over when `SESSION_SECRET` is unchanged.
- Keep the 5-failures/15-minute in-memory login limiter semantics.
- Keep `/api/public/events` as notification-only SSE: initial `retry: 3000`, 25-second heartbeat, and `state-changed` event with `{"type":"state-changed"}`.
- Preserve `APP_BASE_PATH`/`VITE_BASE_PATH` sub-path deployment behaviour.

## Tournament database migration

The existing SQLite file must be usable without export/import.

1. Model the existing tables exactly in SQLAlchemy first: `tournament_settings`, `display_settings`, `league_groups`, `teams`, `players`, `league_matches`, `final_seeds`, `final_match_results`, `league_rounds`, including current checks/indexes/FKs.
2. `0001_baseline.py` creates that exact schema for a new empty database.
3. Startup checks for an existing pre-Alembic database. If tables exist but `alembic_version` does not, validate the expected table/column set and **stamp** `0001_baseline` instead of running the create migration.
4. Empty databases run `alembic upgrade head` normally.
5. Keep SQLite `foreign_keys=ON`, WAL mode and `busy_timeout=5000` via SQLAlchemy connection events.
6. Add a test that copies a database produced by the current Node application, starts the Python application, and verifies all data/state is unchanged.

This permits rollback to the Node version during the migration window because the baseline schema itself does not change.

## Tournament backend port mapping by responsibility

`app.ts` should not become another monolith. Its endpoints split as follows:

| Router | Existing endpoints |
|---|---|
| `routers/auth.py` | `/api/auth/login`, `/logout`, `/session` |
| `routers/admin/settings.py` | `/api/admin/settings` |
| `routers/admin/display.py` | `/api/admin/display` |
| `routers/admin/groups.py` | `/api/admin/groups...` |
| `routers/admin/teams.py` | `/api/admin/teams...`, player CRUD |
| `routers/admin/calendar.py` | calendar get/generate/preview/delete |
| `routers/admin/matches.py` | league result + round standings endpoints |
| `routers/admin/final_stage.py` | all final-stage config/seeds/results endpoints |
| `routers/public.py` | `/api/public/state`, `/api/public/events` |

Pydantic schemas should be grouped by the same domain, not placed in one large schema file.

## Shifts `web.py` split

Do this **after** the monorepo move, with no route or template behaviour changes:

| Target router | Current responsibility |
|---|---|
| `routers/auth.py` | `/login`, `/logout`, auth dependencies |
| `routers/account.py` | `/account` |
| `routers/calendar.py` | ICS feed and calendar page |
| `routers/exports.py` | schedule export HTML/PDF |
| `routers/dashboard.py` | `/`, `/health` |
| `routers/swaps.py` | all member/admin swap transitions outside schedule assignment |
| `routers/admin/teams.py` | admin team CRUD |
| `routers/admin/users.py` | admin user CRUD |
| `routers/admin/schedules.py` | schedule configuration, patterns, rotation membership |
| `routers/admin/assignments.py` | assignments, regeneration, assign-day, swap assignment |
| `routers/admin/notifications.py` | notification log page |

Shared request helpers (`current_user`, `require_user`, `require_admin`, CSRF validation, flash/context helpers) go into a small router dependency/helper module, not into `security/` unless they are genuinely security primitives.

## Shared branding

Use one canonical CRR asset set. The Tournament logo is the higher-resolution current source and becomes `packages/crr-brand/assets/logo.png`; the Shifts copy is removed after visual verification.

### `tokens.css`

Normalize the already-overlapping palette around the existing CRR red `#ed1c24`:

- primary / primary-hover / primary-dark
- background / surface
- text / muted text
- border
- danger / warning
- soft brand background
- shared radii, shadows, spacing and font stack

App-specific tokens such as Tournament match-card dimensions stay in the app stylesheet.

### `base.css`

Only cross-app primitives: box sizing, body typography/background, links, form controls, focus state, basic tables.

### `components.css`

Shared visual patterns only where both apps actually use them: CRR button variants, cards/panels, alerts/status badges and common table treatment. Do not attempt to share Vue components with Jinja.

Tournament imports shared CSS before its app stylesheet. Shifts mounts `packages/crr-brand` as a second FastAPI static directory (for example `/brand`) and loads shared CSS before `app.css`.

## Python packaging

Root `pyproject.toml` is a uv workspace:

```toml
[tool.uv.workspace]
members = [
  "apps/tournament/backend",
  "apps/shifts/backend",
  "packages/crr-python",
]
```

Each backend has its own project metadata and dependencies but resolves into one root `uv.lock`. Use `requires-python = ">=3.13,<3.14"` initially so both applications are tested against the same interpreter generation.

Shifts dependencies currently in `requirements*.txt` move into `apps/shifts/backend/pyproject.toml`; the requirements files are deleted only after the uv lockfile is generated and CI passes.

Tournament backend dependencies start with FastAPI, Uvicorn, SQLAlchemy, Alembic, Pydantic Settings and the testing stack (`pytest`, `httpx`).

## Docker/deployment

Keep two images:

- `crr-tournament`
- `crr-shifts`

Both Dockerfiles use repository root as build context so they can consume `packages/`. The root `.dockerignore` must exclude `original/` entirely.

Tournament uses a Node 22 build stage for Vue and a Python 3.13 runtime stage. The built SPA is copied into the Python image and served by FastAPI, preserving the current single-container deployment.

Shifts becomes Python 3.13 + uv and copies the shared brand package into the image. Its database remains independent from Tournament.

The root `compose.yaml` defines two independent services and storage locations. `docker compose up tournament` and `docker compose up shifts` must both work independently; `docker compose up` may run both.

## Root developer commands

The root Makefile should expose namespaced commands rather than hiding which app is running:

```text
make tournament-backend-dev
make tournament-frontend-dev
make tournament-test
make tournament-build
make shifts-dev
make shifts-test
make shifts-build
make test
```

`make test` runs both backends plus Tournament frontend tests/typechecking.

## CI

Use path-aware jobs:

- Tournament frontend job: `apps/tournament/frontend/**` or `packages/crr-brand/**`.
- Tournament backend job: `apps/tournament/backend/**` or `packages/crr-python/**`.
- Shifts job: `apps/shifts/**`, `packages/crr-brand/**` or `packages/crr-python/**`.
- Root tooling changes (`pyproject.toml`, `uv.lock`, Compose, CI itself) run both backend jobs as appropriate.

A branding-only change must test both applications because it can break either rendered UI.

## Independent releases

Do not use one monorepo version. Tag releases independently, for example:

```text
tournament-v1.1.0
shifts-v1.0.3
```

A release workflow builds only the relevant image from that tag. Shared package changes are released only through whichever app consumes the change; the shared packages do not need separate public versions initially.

## Migration sequence

### Phase 0 — freeze behaviour

- Run and preserve both current test suites in isolated copies of
  `originals/tournment-manager-web/` and `originals/crr-shifts/`. Dependency
  installation, bytecode, test caches and build outputs must stay outside snapshots.
- Add any migration-only compatibility fixtures/tests outside `original/`; do not modify the source snapshots.
- Capture the existing Tournament API contract before replacing Fastify.
- Save a representative Tournament SQLite database fixture produced by `original/tournament-manager/` for migration tests.
- Save screenshots of key pages from both original apps for branding regression comparison.

**Exit:** both existing repositories are green and baseline artefacts exist.

### Phase 1 — create monorepo without architecture changes

- Keep `original/` unchanged as the migration baseline.
- Create root structure/configuration.
- Copy Tournament frontend/server sources and Shifts sources from `original/` according to the file map below.
- At this point Tournament may temporarily still run a copied Node backend from its app directory; the goal is only to prove the new monorepo paths.
- Update build/test paths so all migrated builds/tests run from `apps/`, never from `original/`.

**Exit:** both apps run from the monorepo with no functional change.

### Phase 2 — shared CRR brand

- Create `crr-brand` tokens/assets/base components.
- Replace both logo copies with the canonical shared asset.
- Extract only visibly common CSS; leave app-specific layout CSS local.
- Verify mobile/desktop and Tournament print cards.

**Exit:** both apps have the same brand primitives without layout regressions.

### Phase 3 — Tournament FastAPI replacement

- Create SQLAlchemy models and Alembic baseline/adoption logic.
- Port deterministic services and their tests first.
- Port state assembly.
- Port auth/session/rate limiting.
- Port routers one domain at a time.
- Port SSE.
- Serve the existing Vue build from FastAPI.
- Remove Node backend dependencies only after the complete Python API compatibility suite passes.

**Exit:** existing Vue build works unchanged against Python; existing tournament DB opens in place; API/status/error/SSE contract tests pass.

### Phase 4 — Shifts structural refactor

- Move service modules into `services/`.
- Split models without schema changes.
- Split `web.py` router by router.
- Move security primitives into `security/`.
- Do not alter routes, form fields, templates or database schema in this phase.

**Exit:** Shifts tests pass and rendered behaviour is unchanged.

### Phase 5 — extract proven Python common code

Compare the final two Python backends. Only now extract byte-for-byte-equivalent or clearly generic infrastructure into `crr-python`, likely starting with SQLite engine pragmas/Alembic setup helpers if doing so removes real duplication without app-specific switches.

**Exit:** neither app imports the other's code; shared package contains no domain concepts.

### Phase 6 — cleanup

- Remove Tournament TypeScript server files/config/dependencies from `apps/tournament/` only; keep the copy under `original/tournament-manager/` untouched.
- Remove migrated Shifts requirements files and duplicate logo from `apps/shifts/` only; keep `original/crr-shifts/` untouched.
- Remove temporary compatibility scaffolding outside `original/`.
- Update documentation and release workflows.
- Retain `original/` as the historical migration baseline unless a separate, explicit post-migration decision removes it.

## Non-goals

- No combined database.
- No shared `Team` model.
- No common login/user schema.
- No migration of Shifts to Vue.
- No migration of Tournament away from Vue.
- No microservices or separate API container/frontend container unless a real deployment need appears later.
- No generic repository/service framework merely to make the directory trees look identical.

## Acceptance criteria

The migration is complete when:

1. Each app can be built/run/tested independently from the monorepo.
2. Tournament's existing Vue frontend works without API changes against FastAPI.
3. Existing Tournament and Shifts SQLite data opens without manual conversion or loss.
4. Each app retains a separate migration history/database/auth model/image/version.
5. Both apps use the same canonical CRR logo and design tokens.
6. Shared Python code contains infrastructure only, no Tournament/Shifts domain entities.
7. A change limited to one app does not require deploying the other.
8. The old Tournament Node backend can be removed with no remaining runtime dependency on Fastify, `better-sqlite3` or Zod.
9. `original/` remains unchanged and no production/runtime code imports or executes from it.

## Exact existing-file migration map

The following table accounts for every non-directory file in the two original codebases. Every source path is rooted under `original/`; source files remain untouched. Actions such as `copy`, `port`, `rewrite` and `merge` create or update files outside `original/`.

| Repository | Source | Action | Destination | Notes |
|---|---|---|---|---|
| Tournament Manager | `original/tournament-manager/.dockerignore` | merge | `/.dockerignore` | Merge Docker ignore rules for root build context |
| Tournament Manager | `original/tournament-manager/.env.example` | copy | `apps/tournament/.env.example` | Keep app-specific environment contract |
| Tournament Manager | `original/tournament-manager/.gitignore` | merge | `/.gitignore` | Merge repository ignore rules |
| Tournament Manager | `original/tournament-manager/AGENTS.md` | copy+edit | `apps/tournament/AGENTS.md` | Keep tournament-specific contributor guidance |
| Tournament Manager | `original/tournament-manager/AGENTS.md.bak` | leave-in-original | `—` | Redundant backup after AGENTS.md is migrated; no migrated copy is needed |
| Tournament Manager | `original/tournament-manager/Dockerfile` | rewrite | `apps/tournament/Dockerfile` | Replace Node backend runtime with Node frontend build + Python 3.13 FastAPI runtime |
| Tournament Manager | `original/tournament-manager/README.md` | copy+edit | `apps/tournament/README.md` | Update monorepo/dev/deploy commands |
| Tournament Manager | `original/tournament-manager/compose.yaml` | merge | `/compose.yaml` | Tournament service becomes one root Compose service |
| Tournament Manager | `original/tournament-manager/index.html` | copy | `apps/tournament/frontend/index.html` | Vite frontend root |
| Tournament Manager | `original/tournament-manager/logo.png` | copy+canonicalize | `packages/crr-brand/assets/logo.png` | Use as canonical high-resolution CRR logo |
| Tournament Manager | `original/tournament-manager/package-lock.json` | copy | `apps/tournament/frontend/package-lock.json` | Regenerate after package.json cleanup |
| Tournament Manager | `original/tournament-manager/package.json` | copy+edit | `apps/tournament/frontend/package.json` | Remove backend Node dependencies/scripts |
| Tournament Manager | `original/tournament-manager/public/favicon.png` | copy+canonicalize | `packages/crr-brand/assets/favicon.png` | Shared favicon |
| Tournament Manager | `original/tournament-manager/src/client/App.vue` | copy+edit | `apps/tournament/frontend/src/App.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/AdminShell.vue` | copy+edit | `apps/tournament/frontend/src/components/AdminShell.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/AppLogo.vue` | copy+edit | `apps/tournament/frontend/src/components/AppLogo.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/AppModal.vue` | copy+edit | `apps/tournament/frontend/src/components/AppModal.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/ClassificationTable.vue` | copy+edit | `apps/tournament/frontend/src/components/ClassificationTable.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/DisplayClassificationPanel.vue` | copy+edit | `apps/tournament/frontend/src/components/DisplayClassificationPanel.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/DisplayFit.vue` | copy+edit | `apps/tournament/frontend/src/components/DisplayFit.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/DisplayLatestResultsPanel.vue` | copy+edit | `apps/tournament/frontend/src/components/DisplayLatestResultsPanel.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/FinalBracket.vue` | copy+edit | `apps/tournament/frontend/src/components/FinalBracket.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/MatchResultCard.vue` | copy+edit | `apps/tournament/frontend/src/components/MatchResultCard.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/match-cards/FourScores.vue` | copy+edit | `apps/tournament/frontend/src/components/match-cards/FourScores.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/match-cards/SingleScore.vue` | copy+edit | `apps/tournament/frontend/src/components/match-cards/SingleScore.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/match-cards/SixScores.vue` | copy+edit | `apps/tournament/frontend/src/components/match-cards/SixScores.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/components/matchCards.ts` | copy+edit | `apps/tournament/frontend/src/components/matchCards.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/displayPanels.ts` | copy+edit | `apps/tournament/frontend/src/displayPanels.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/api.ts` | copy+edit | `apps/tournament/frontend/src/lib/api.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/format.test.ts` | copy+edit | `apps/tournament/frontend/src/lib/format.test.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/format.ts` | copy+edit | `apps/tournament/frontend/src/lib/format.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/score.test.ts` | copy+edit | `apps/tournament/frontend/src/lib/score.test.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/score.ts` | copy+edit | `apps/tournament/frontend/src/lib/score.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/lib/usePublicTournamentState.ts` | copy+edit | `apps/tournament/frontend/src/lib/usePublicTournamentState.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/main.ts` | copy+edit | `apps/tournament/frontend/src/main.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/router.ts` | copy+edit | `apps/tournament/frontend/src/router.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/styles.css` | copy+edit | `apps/tournament/frontend/src/styles.css` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/types.ts` | copy+edit | `apps/tournament/frontend/src/types.ts` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/CalendarView.vue` | copy+edit | `apps/tournament/frontend/src/views/CalendarView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/DisplaySettingsView.vue` | copy+edit | `apps/tournament/frontend/src/views/DisplaySettingsView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/DisplayView.vue` | copy+edit | `apps/tournament/frontend/src/views/DisplayView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/FinalStageView.vue` | copy+edit | `apps/tournament/frontend/src/views/FinalStageView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/LoginView.vue` | copy+edit | `apps/tournament/frontend/src/views/LoginView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/MatchCardsView.vue` | copy+edit | `apps/tournament/frontend/src/views/MatchCardsView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/PublicResultsView.vue` | copy+edit | `apps/tournament/frontend/src/views/PublicResultsView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/ResultsView.vue` | copy+edit | `apps/tournament/frontend/src/views/ResultsView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/client/views/TeamsView.vue` | copy+edit | `apps/tournament/frontend/src/views/TeamsView.vue` | Adjust imports/base paths/brand imports as needed |
| Tournament Manager | `original/tournament-manager/src/server/app.integration.test.ts` | port | `apps/tournament/backend/tests/test_api_compatibility.py` | Port all observable route/status/error contract tests |
| Tournament Manager | `original/tournament-manager/src/server/app.ts` | port+split | `apps/tournament/backend/app/{routers,schemas,services}/` | Split Fastify monolith into FastAPI routers and Pydantic schemas; preserve API contract |
| Tournament Manager | `original/tournament-manager/src/server/auth.ts` | port+split | `apps/tournament/backend/app/security/{session.py,rate_limit.py}` | Preserve cookie name/token format/rate-limit semantics |
| Tournament Manager | `original/tournament-manager/src/server/db/database.test.ts` | port | `apps/tournament/backend/tests/test_database.py` | Port schema/default/constraint tests |
| Tournament Manager | `original/tournament-manager/src/server/db/database.ts` | port+split | `apps/tournament/backend/app/database.py + app/models/ + migrations/versions/0001_baseline.py` | SQLAlchemy model + Alembic baseline with legacy DB adoption |
| Tournament Manager | `original/tournament-manager/src/server/errors.ts` | port | `apps/tournament/backend/app/errors.py` | Preserve JSON error shape |
| Tournament Manager | `original/tournament-manager/src/server/events.ts` | port | `apps/tournament/backend/app/events.py` | SSE state-change broker |
| Tournament Manager | `original/tournament-manager/src/server/main.ts` | port | `apps/tournament/backend/app/main.py` | FastAPI application entry point |
| Tournament Manager | `original/tournament-manager/src/server/services/bracket.test.ts` | port | `apps/tournament/backend/tests/services/test_bracket.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/bracket.ts` | port | `apps/tournament/backend/app/services/bracket.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/calendar.test.ts` | port | `apps/tournament/backend/tests/services/test_calendar.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/calendar.ts` | port | `apps/tournament/backend/app/services/calendar.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/classification.test.ts` | port | `apps/tournament/backend/tests/services/test_classification.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/classification.ts` | port | `apps/tournament/backend/app/services/classification.py` |  |
| Tournament Manager | `original/tournament-manager/src/server/services/state.ts` | port | `apps/tournament/backend/app/services/state.py` | Translate SQL-backed state assembly to SQLAlchemy while preserving response shape |
| Tournament Manager | `original/tournament-manager/src/shared/types/tournament.ts` | copy+edit | `apps/tournament/frontend/src/types/tournament.ts` | Frontend API types remain TypeScript; FastAPI Pydantic schemas mirror this contract |
| Tournament Manager | `original/tournament-manager/src/vite-env.d.ts` | copy | `apps/tournament/frontend/src/vite-env.d.ts` |  |
| Tournament Manager | `original/tournament-manager/tsconfig.client.json` | copy+rename | `apps/tournament/frontend/tsconfig.json` | Update include paths |
| Tournament Manager | `original/tournament-manager/tsconfig.server.json` | leave-in-original | `—` | Node/TypeScript backend removed; no migrated copy is needed |
| Tournament Manager | `original/tournament-manager/vite.config.ts` | copy+edit | `apps/tournament/frontend/vite.config.ts` | Proxy to FastAPI and read shared brand assets |
| CRR Shifts | `original/crr-shifts/.dockerignore` | merge | `/.dockerignore` | Merge Docker ignore rules for root build context |
| CRR Shifts | `original/crr-shifts/.env.example` | copy+edit | `apps/shifts/.env.example` | Keep app-specific environment contract; Python 3.13 runtime |
| CRR Shifts | `original/crr-shifts/.gitignore` | merge | `/.gitignore` | Merge repository ignore rules |
| CRR Shifts | `original/crr-shifts/AGENTS.md` | copy+edit | `apps/shifts/AGENTS.md` | Keep shifts-specific contributor guidance |
| CRR Shifts | `original/crr-shifts/Dockerfile` | rewrite | `apps/shifts/Dockerfile` | Python 3.13 + uv; root build context |
| CRR Shifts | `original/crr-shifts/Makefile` | merge | `/Makefile` | Convert to root namespaced targets such as shifts-dev/shifts-test |
| CRR Shifts | `original/crr-shifts/README.md` | copy+edit | `apps/shifts/README.md` | Update monorepo/dev/deploy commands |
| CRR Shifts | `original/crr-shifts/alembic.ini` | copy+edit | `apps/shifts/backend/alembic.ini` | Update script paths for backend subdirectory |
| CRR Shifts | `original/crr-shifts/app/__init__.py` | copy | `apps/shifts/backend/app/__init__.py` |  |
| CRR Shifts | `original/crr-shifts/app/bootstrap.py` | copy+refactor | `apps/shifts/backend/app/services/bootstrap.py` | No behavior change |
| CRR Shifts | `original/crr-shifts/app/calendar.py` | copy+refactor | `apps/shifts/backend/app/services/calendar_feed.py` | Avoid name collision with router |
| CRR Shifts | `original/crr-shifts/app/cli.py` | copy+edit | `apps/shifts/backend/app/cli.py` | Update imports/paths |
| CRR Shifts | `original/crr-shifts/app/config.py` | copy+edit | `apps/shifts/backend/app/config.py` | Keep settings contract |
| CRR Shifts | `original/crr-shifts/app/database.py` | copy+edit | `apps/shifts/backend/app/database.py` | Update migration paths; later share proven generic helpers |
| CRR Shifts | `original/crr-shifts/app/i18n.py` | copy | `apps/shifts/backend/app/i18n.py` |  |
| CRR Shifts | `original/crr-shifts/app/main.py` | copy+edit | `apps/shifts/backend/app/main.py` | Include split routers and shared brand StaticFiles mount |
| CRR Shifts | `original/crr-shifts/app/models.py` | split | `apps/shifts/backend/app/models/{user.py,team.py,schedule.py,assignment.py,swap.py,notification.py,__init__.py}` | Pure structural split; retain SQLAlchemy schema |
| CRR Shifts | `original/crr-shifts/app/notifications.py` | copy+refactor | `apps/shifts/backend/app/services/notifications.py` |  |
| CRR Shifts | `original/crr-shifts/app/pdf.py` | copy+refactor | `apps/shifts/backend/app/services/pdf.py` |  |
| CRR Shifts | `original/crr-shifts/app/scheduling.py` | copy+refactor | `apps/shifts/backend/app/services/scheduling.py` |  |
| CRR Shifts | `original/crr-shifts/app/security.py` | split | `apps/shifts/backend/app/security/{passwords.py,csrf.py,__init__.py}` | Keep auth model independent from Tournament |
| CRR Shifts | `original/crr-shifts/app/static/app.css` | copy+edit | `apps/shifts/backend/app/static/app.css` | Remove extracted shared brand tokens/components |
| CRR Shifts | `original/crr-shifts/app/static/logo-crr.png` | reference-shared-copy | `packages/crr-brand/assets/logo.png` | Use shared canonical logo; do not keep duplicate |
| CRR Shifts | `original/crr-shifts/app/templates/_schedule_export_form.html` | copy+edit | `apps/shifts/backend/app/templates/_schedule_export_form.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/account.html` | copy+edit | `apps/shifts/backend/app/templates/account.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_assign.html` | copy+edit | `apps/shifts/backend/app/templates/admin_assign.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_notifications.html` | copy+edit | `apps/shifts/backend/app/templates/admin_notifications.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_schedule.html` | copy+edit | `apps/shifts/backend/app/templates/admin_schedule.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_schedules.html` | copy+edit | `apps/shifts/backend/app/templates/admin_schedules.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_team_delete.html` | copy+edit | `apps/shifts/backend/app/templates/admin_team_delete.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_teams.html` | copy+edit | `apps/shifts/backend/app/templates/admin_teams.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/admin_users.html` | copy+edit | `apps/shifts/backend/app/templates/admin_users.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/base.html` | copy+edit | `apps/shifts/backend/app/templates/base.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/calendar.html` | copy+edit | `apps/shifts/backend/app/templates/calendar.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/dashboard.html` | copy+edit | `apps/shifts/backend/app/templates/dashboard.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/export_schedule.html` | copy+edit | `apps/shifts/backend/app/templates/export_schedule.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/login.html` | copy+edit | `apps/shifts/backend/app/templates/login.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/swap_new.html` | copy+edit | `apps/shifts/backend/app/templates/swap_new.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/templates/swaps.html` | copy+edit | `apps/shifts/backend/app/templates/swaps.html` | Only update shared-brand/static references as needed |
| CRR Shifts | `original/crr-shifts/app/web.py` | split | `apps/shifts/backend/app/routers/` | Split by auth/account/calendar/swaps/admin while preserving routes/templates |
| CRR Shifts | `original/crr-shifts/compose.yaml` | merge | `/compose.yaml` | Shifts service becomes one root Compose service |
| CRR Shifts | `original/crr-shifts/docs/ARCHITECTURE.md` | copy+edit | `apps/shifts/docs/ARCHITECTURE.md` | Update paths/architecture notes |
| CRR Shifts | `original/crr-shifts/docs/DOMAIN.md` | copy+edit | `apps/shifts/docs/DOMAIN.md` | Update paths/architecture notes |
| CRR Shifts | `original/crr-shifts/migrations/README` | copy+edit | `apps/shifts/backend/migrations/README` |  |
| CRR Shifts | `original/crr-shifts/migrations/env.py` | copy+edit | `apps/shifts/backend/migrations/env.py` | Update imports/path |
| CRR Shifts | `original/crr-shifts/migrations/script.py.mako` | copy | `apps/shifts/backend/migrations/script.py.mako` |  |
| CRR Shifts | `original/crr-shifts/migrations/versions/0001_initial.py` | copy | `apps/shifts/backend/migrations/versions/0001_initial.py` | Preserve migration history unchanged |
| CRR Shifts | `original/crr-shifts/pyproject.toml` | rewrite | `apps/shifts/backend/pyproject.toml` | Full uv project metadata + runtime/dev dependencies |
| CRR Shifts | `original/crr-shifts/pyrightconfig.json` | merge | `/pyrightconfig.json` | One root Python type-check config for both backends |
| CRR Shifts | `original/crr-shifts/requirements-dev.txt` | leave-in-original | `—` | Dependencies move to pyproject.toml/uv.lock; no migrated copy is needed |
| CRR Shifts | `original/crr-shifts/requirements.txt` | leave-in-original | `—` | Dependencies move to pyproject.toml/uv.lock; no migrated copy is needed |
| CRR Shifts | `original/crr-shifts/tests/.gitkeep` | copy+edit | `apps/shifts/backend/tests/.gitkeep` | Update imports/paths only |
| CRR Shifts | `original/crr-shifts/tests/conftest.py` | copy+edit | `apps/shifts/backend/tests/conftest.py` | Update imports/paths only |
| CRR Shifts | `original/crr-shifts/tests/test_export_schedule.py` | copy+edit | `apps/shifts/backend/tests/test_export_schedule.py` | Update imports/paths only |
