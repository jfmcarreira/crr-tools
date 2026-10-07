# Migration progress

Verified on 2026-10-07. Follow `MONOREPO_MIGRATION_PLAN.md`; its historical source
labels resolve to `originals/tournment-manager-web/` and `originals/crr-shifts/`.

## Phase 0 — behaviour baseline: complete

Both untouched source snapshots were copied into disposable `.migration/`
directories before dependency installation, tests and builds. SHA-256 manifests
confirm that source files match the snapshots after the checks and app copies.
No commands installed dependencies or generated outputs inside `originals/`.

| Baseline check | Result |
| --- | --- |
| Tournament `npm test` | 55 passed, 8 files |
| Tournament `npm run typecheck` | Passed |
| Tournament `npm run build` | Vue and server builds passed |
| Shifts pytest, Python 3.13.13 | 14 passed |
| Tournament SQLite integrity / foreign keys | Passed |
| Desktop/mobile screenshots | 14 captured, including print cards |

Tournament was checked locally using Node 26.0.0/npm 11.12.1, satisfying the
legacy `>=22` engine constraint. Node 22 remains the CI/container target; its CI
checks have not run yet. The legacy package has no `lint` script. Shifts' legacy
requirements resolve the same versions as the new root lockfile's runtime/test
dependencies. Existing upstream/runtime deprecation warnings remain visible.

### Preserved evidence

- `baseline/tournament.json` and `baseline/shifts.json`: source checksums,
  executed commands, exit codes and individual passing test names.
- `baseline/artifacts.json`: fixture and screenshot checksums.
- `fixtures/tournament.sqlite`: database created by the actual legacy Node
  application, containing all nine existing tables and no Alembic stamp.
- `fixtures/tournament-schema.json` and `tournament-rows.json`: exact legacy
  schema/index definitions and persisted contents for adoption checks.
- `fixtures/tournament-state.json`: expected public state, including standings,
  final-stage results, champion and third-place match.
- `fixtures/tournament-api.json`: observable requests/statuses/bodies for a
  synthetic workflow, authentication failures, duplicate-number conflict and 404.
- `fixtures/tournament-routes.json`: explicit API method/path inventory. This is
  an inventory, not a substitute for the legacy integration suite.
- `fixtures/tournament-cookie.json`: cookie attributes with its token removed.
- `screenshots/`: desktop (1440×1000), mobile (390×844), login/results/admin pages
  and Tournament match cards in print media, with a capture manifest.

Fixtures contain synthetic Portuguese names and public test-only credentials;
they contain no production data. Timestamps in the final Tournament database
are fixed; the browser clock is fixed for screenshots. Shifts demo schedules
use the server's capture month, October 2026. Raw execution logs and test-runner
reports remain available locally under ignored `migration/results/`.

### Reproduce

```sh
make baseline-test
make baseline-fixtures
make baseline-screenshots
make baseline-preserve
```

These commands require Node 22+, Python 3.13, uv, and Playwright's Chromium
download for screenshot capture. `baseline-test` replaces disposable staging
copies. Fixture/screenshot capture intentionally refreshes migration artefacts.
It starts isolated servers on localhost ports 18080 and 18081 and shuts them
down afterwards. Run screenshot commands serially. Repeated captures in a
different month/browser version may need a reviewed visual baseline update.

This machine's `uv` is installed through the Python 3.14.6 pyenv environment,
while `.python-version` selects 3.13. Commands here used
`PYENV_VERSION=3.14.6 make shifts-test` (and that environment for baseline tooling)
to resolve the uv executable; uv still used Python 3.13.13 for Shifts. Other
machines with uv available independently do not need that override.

## Phase 1 — monorepo paths: local exit verified; remote CI pending

- Tournament source/lockfile copied into `apps/tournament/`, retaining its
  working `src/{client,server,shared}` layout during this phase.
- Shifts app/templates/static files, tests and unchanged migration history copied
  into `apps/shifts/backend/`; domain/architecture reference docs copied too.
- Root uv workspace, Python 3.13 constraint, single lockfile and independent
  Shifts project metadata added. Tournament enters the workspace in Phase 3.
- Root namespaced Makefile commands, Python configuration, app instructions and
  development documentation added.
- Independent root-context Dockerfiles and Compose services/volumes added.
  Optional per-app environment files let either service be configured separately.
- Path-filtered CI tests/builds only affected apps; shared branding/Python/root
  tooling changes trigger both as applicable. No production or CI job runs from
  `originals/`.

| Migrated check | Result |
| --- | --- |
| `make tournament-test` | 55 tests and both typechecks passed |
| `make tournament-build` | Vue and server builds passed |
| `make shifts-test` | 14 passed with locked Python 3.13 dependencies |
| Live app rendering from `apps/` | Both applications served successfully |
| `make migration-visual-check` | All 14 captures byte-for-byte match legacy |
| `docker compose config --quiet` | Passed; both independent services listed |
| Docker image builds | Both passed: Tournament Node 22, Shifts Python 3.13 |
| `make images-smoke-test` | Both containers started; JSON/HTML routes passed |
| GitHub Actions | Workflow added; remote execution not verified |

`tools/migrate_app_sources.py` was used for the one-time source copy. It refuses
existing destinations rather than overwriting application work. Do not rerun it
against the populated apps. Requirements files stay in the migrated Shifts copy
until the lockfile workflow passes CI, as required by the plan.

Docker was initially stopped; Docker Desktop was started and both independent
image builds then passed. The smoke check used temporary containers, random
localhost ports, synthetic credentials and tmpfs databases; containers were
removed after checking Tournament `/api/public/state` and `/results`, and Shifts
`/health` and `/login`. No production database or persistent volume was used.

Repeat image checks after building both images:

```sh
docker build -f apps/tournament/Dockerfile -t crr-tournament .
make shifts-build
make images-smoke-test
```

## Phase 2 — shared CRR brand: locally verified complete

- Created `packages/crr-brand` with one canonical Tournament logo (2324×2051)
  and favicon, copied byte-for-byte from the baseline. Shared CSS defines the
  red `#ed1c24` palette, neutral/control/error colors, font stack, radii, shadows
  and spacing tokens, plus common base, button, panel and error-alert rules.
- Both apps load tokens/base/components before app styles. Existing variable
  names now alias shared tokens. Responsive layouts, typography hierarchy,
  control padding, specialist badges and print-card dimensions stay app-local.
- Tournament imports the package through Vite's `@crr-brand` alias and public
  asset directory; shared files also work in Vite development under `/jogo/`.
- Shifts mounts `/brand`, generates prefixed asset URLs through Jinja `url_for`,
  and uses the canonical logo in PDF exports. Its login logo retains the old
  display aspect ratio to avoid a subpixel form-layout shift from the source
  image's slightly different dimensions.
- Removed the two app-local logo files and Tournament's local favicon after
  successful visual verification. Original snapshots remain unchanged.
- Both root-context images consume the package; the existing brand path filter
  triggers both application CI jobs.

| Check | Result |
| --- | --- |
| Tournament tests/typechecks | 55 passed; both typechecks passed |
| Tournament Vue/server build | Passed |
| Shifts tests, including PDF exports and brand resources | 16 passed |
| Shifts brand assets under `/` and `/crr` | CSS, logo and favicon passed |
| Tournament Vite development under `/jogo/` | Page, favicon, entrypoint, shared CSS and logo passed |
| `make branding-visual-check` | All 14 captures preserve measured legacy element rectangles exactly |
| Tournament print cards | Both desktop/mobile captures match Phase 0 byte-for-byte |
| `make migration-visual-check` | All 14 captures match the new Phase 2 reference byte-for-byte |
| Both Docker builds | Passed |
| `make images-smoke-test` | Both containers serve HTML/JSON and referenced CSS/JS/PNG resources |

Visual review confirmed the intended palette/control-focus/panel-corner changes
and sharper canonical Shifts logo, with no layout regressions in the captured
desktop/mobile pages. `phase2/screenshots/` preserves the 14 updated PNGs,
capture manifest and measured rectangles. `phase2/verification.json` records
the geometry/print results, element counts and screenshot checksums. Phase 0
screenshots and compatibility fixtures are retained unchanged.

`make branding-visual-check` compares geometry against new captures of the
isolated legacy copies, allowing the deliberate color/asset changes. Future
`make migration-visual-check` runs use `phase2/screenshots/` as their exact
reference. Both require the Phase 0 staging/Playwright setup described above.
Container smoke checks emulate the existing Tournament proxy's `/jogo` prefix
stripping when fetching its built asset URLs. Remote CI remains unverified.

## Phase 3 — Tournament FastAPI replacement: locally verified complete

- Added the independent `crr-tournament` Python 3.13 workspace member, version
  1.0.0, with FastAPI, SQLAlchemy 2, Alembic and Pydantic Settings.
- Modeled the nine existing SQLite tables with typed `Mapped` columns. The frozen
  Alembic baseline creates the exact Node schema and defaults. Existing databases
  are validated before stamping, including column types/nullability, defaults,
  primary/unique keys, checks, indexes, foreign keys, autoincrement and group
  collation. Validation/stamping/upgrades use an explicit SQLite transaction;
  failed upgrades roll back schema creation. Foreign keys/WAL/5000 ms timeout
  apply to every connection.
- Ported calendar generation, standard/total-points standings and head-to-head
  tie breakers, brackets/byes/third-place advancement, seeding and state assembly.
- Added domain-grouped request/response schemas and separate auth/public/admin
  routers. CamelCase payloads, status/error shapes, Portuguese messages, HTTP
  methods and confirmation rules are preserved. Request validation also covers
  JavaScript-style ID coercion, name trimming and UTF-16 length limits.
- Reproduced the Node HMAC-SHA256/base64url session format and cookie semantics;
  verified a token produced by the actual Node implementation. Preserved the
  five-failure/15-minute login window and successful-login reset. Synchronization
  preserves serial numbering and atomic login limiting under ASGI concurrency.
- Ported notification-only SSE with retry 3000, 25-second heartbeat, exact
  state-change frames and subscriber cleanup. FastAPI serves the existing Vue
  build, including the legacy sub-path proxy deployment behavior.
- Switched development and production runtime to Uvicorn/Python. The image builds
  Vue with Node 22 and preserves UID/GID 1000 for existing SQLite volumes. Removed
  Fastify, better-sqlite3, Zod, tsx and backend-only type packages/scripts from
  the frontend dependency graph after compatibility checks passed.
- Updated Makefile/CI to check both Python and frontend code. Preserved all 44
  legacy HTTP/service assertions under `contracts/` and execute them unchanged
  using migration-only Python transports. This compatibility command uses owned
  contracts and app tooling; CI never reads/builds/runs `originals/`.

| Check | Result |
| --- | --- |
| Backend pytest | 28 passed |
| Preserved legacy assertions against Python | 44 passed: 19 HTTP/SSE, 25 deterministic services |
| Frontend/shared tests | 13 passed |
| Vue typecheck and build | Passed |
| Fresh database schema/defaults vs Node | Exact normalized SQLite DDL match |
| Python startup with populated Node fixture | All nine table contents and public state preserved |
| Incompatible schemas / migration failure | Refused without stamping; failed DDL rolled back |
| Token compatibility / cookies / limiter | Node-produced token and HTTPS/proxy/window/reset/concurrency checks passed |
| `make migration-visual-check` | All 14 screenshots match Phase 2 byte-for-byte |
| Both Docker builds | Passed |
| Container smoke checks | Fresh Tournament, adopted Node fixture and Shifts passed; referenced resources served |
| Shifts regression suite | 16 passed |

`phase3/compatibility.json` preserves passing legacy test names and contract
checksums; raw test reports remain in `.migration/port-compat/`. Database tests
copy the Node fixture before adoption; container adoption checks likewise use a
read-only fixture mount copied into tmpfs. No production database was used.

The TypeScript server source/config files are retired reference material pending
Phase 6 cleanup; production images contain only the Python backend and built
Vue assets. The Vue source directory move is also deferred to that cleanup.
Compatibility transport scaffolding remains until the corresponding cleanup
exit criteria are verified. Remote GitHub Actions execution is still unverified.

On this machine, the pyenv override described above also applies to Tournament
Makefile commands; uv still executes the applications on Python 3.13.

## Next work

1. Verify the new CI jobs on Node 22/Python 3.13 after publishing the changes.
2. Phase 4: Shifts service/model/security extraction and router split, preserving
   routes, templates, forms, authentication, SQLite data and migration history.

Phases 4–6 are not complete. No shared Python package has been extracted yet.
Independent tag-triggered release workflows and final dependency cleanup belong
to later phases.
