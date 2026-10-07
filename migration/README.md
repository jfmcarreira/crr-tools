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

## Phase 4 — Shifts structural refactor: locally verified complete

- Moved bootstrap, scheduling, calendar-feed, notification and PDF modules into
  `apps/shifts/backend/app/services/`, updating CLI, startup and test imports.
- Split persistence into `models/{user,team,schedule,assignment,swap,notification}.py`.
  `models/__init__.py` exports the established class names; forward relationship
  typing uses `TYPE_CHECKING` while SQLAlchemy registers all classes normally.
- Split password hashing/verification and CSRF-token generation into `security/`.
  Session/current-user/admin checks, CSRF validation, flash/context, redirects and
  navigation helpers moved into `routers/dependencies.py`.
- Replaced `web.py` with the planned auth/account/calendar/exports/dashboard/swaps
  routers and admin teams/users/schedules/assignments/notifications routers.
  Supporting schedule/swap/assignment/user helpers have an acyclic dependency
  graph. All 48 route declarations and their forms/dependencies moved intact.
- Updated architecture/contributor/development documentation and wired the new
  compatibility check into `make shifts-test` and path-aware CI.

Before changing application code, captured `phase4/baseline.json` and produced
`fixtures/shifts.sqlite` through the existing Shifts code. The fixture contains
synthetic admin/member users, a multi-team login, rotation membership, and
generated/manual/swapped assignments. It contains no production data.

The one-time structural generator relocated definitions verbatim and selected
explicit imports, refusing existing destinations. Verification compares **173
top-level function/class AST fingerprints**, ORM columns/defaults/constraints/
indexes/relationships, full OpenAPI and existing migration-file checksums against
the baseline. It copies the populated fixture before each run and confirms that
startup preserves every existing row.

| Check | Result |
| --- | --- |
| Shifts pytest | 16 passed |
| `make shifts-compat-test` | 96 request/response and resulting-data comparisons matched across `/` and `/crr` |
| ORM/schema and relationship comparison | Identical |
| Route/form/OpenAPI contract | Identical; 48 declarations retained |
| Existing migration history and function/class ASTs | Identical |
| Populated Shifts SQLite fixture on startup | All existing rows preserved |
| `make migration-visual-check` | All 14 captures match Phase 2 byte-for-byte, including print cards |
| Shifts image build | Passed after starting Docker Desktop |
| Container smoke checks | Shifts and both Tournament fresh/adopted-fixture checks passed |
| Tournament regression checks | 28 Python tests, 13 frontend/shared tests, 44 legacy assertions and Vue typecheck passed |

Workflows cover authentication/CSRF/authorization, calendar feeds, PDF exports,
swap creation/acceptance/approval/reversal, administrative CRUD, rotation edits,
assignment changes, password editing and logout. Swap operations exchange both
assignments; explicit generation retains manual/swapped rows. Timestamps, CSRF
nonces and new password salts are normalized only in comparison artefacts;
application behavior is unchanged. The verifier fixes its runtime calendar date
to the capture date so CI can reproduce default-month/navigation HTML later.

`phase4/structure.json` records router ownership and relocated function hashes;
`phase4/verification.json` records successful checks and fixture/baseline hashes.
Raw reports and difference diagnostics stay under `.migration/phase4-results/`.
`make shifts-test` includes this check; `make shifts-compat-test` runs it alone.
Do not rerun the one-time generator or overwrite the baseline. The original
snapshots and branding/compatibility baselines remain intact. Remote CI is still
unverified.

## Phase 5 — proven Python infrastructure: locally verified complete

Compared both final backends and extracted two concrete common operations into
the internal `crr-python` uv member (`src/crr_common`):

- `create_sync_engine`: synchronous SQLAlchemy construction with SQLite request-
  worker threading support. It recognizes SQLAlchemy URL/dialect objects, honors
  explicit connection options and forwards engine/pool options. Each app still
  controls its connection pragmas, filesystem setup and session factories.
- `migration_config`: Alembic ini/script/database wiring, with absolute paths,
  interpolation-safe URLs and an optional caller-owned connection. Baseline
  validation, stamping/upgrades, transactions and history stay app-specific.

This removes duplicated setup without app-name switches or domain concepts.
No models, schemas, auth primitives, error messages or business rules moved into
the package. Both applications declare an explicit workspace dependency and
resolve it through the root lockfile. Local commands use the workspace install;
both independent production images install a non-editable wheel in `/opt/venv`.

Added `make python-common-test`, included it in root `make test` and both affected
app CI jobs. Shared-package paths already trigger both jobs. Docker contexts now
include the package before their frozen uv install step.

| Check | Result |
| --- | --- |
| Shared package tests | 7 passed: cross-thread SQLite, memory/pool forwarding, consumer-owned pragmas, non-SQLite/explicit options, paths/URL escaping and connection ownership |
| Tournament backend | 28 passed |
| Tournament frontend/shared + Vue typecheck/build | 13 passed; typecheck and build passed |
| Legacy Tournament assertions on Python | 44 passed |
| Shifts pytest | 16 passed |
| Shifts workflow/schema/ORM/OpenAPI compatibility | 96 requests matched across both prefixes; mappings, data and histories preserved |
| `make migration-visual-check` | All 14 screenshots match Phase 2 byte-for-byte |
| Independent Docker builds | Both passed |
| Shared-package imports in both images | Verified `/opt/venv/lib/python3.13/site-packages/crr_common` |
| Container startup/resource/adoption smoke checks | Fresh Tournament, populated Node fixture and Shifts passed |

The Phase 4 baseline remains unchanged. `phase5/shifts-definition-overrides.json`
records only the intentional `alembic_config` delegation, with exact before/after
AST fingerprints and the baseline checksum. The verifier still guards the other
172 definitions and all route/form/ORM/data/history expectations; its latest
evidence is in `phase5/shifts-compatibility.json`. Unknown changes continue to
fail rather than being normalized away. `tools/record_shared_infrastructure.py`
was the one-time manifest generator and refuses to overwrite recorded evidence.

Remote GitHub Actions execution is still unverified. The apps retain independent
versions, images, databases and auth models; `crr-python` has an internal 0.1.0
version and is released through its consuming applications.

Historical-source checksum revalidation is blocked: `originals/` is currently
empty, and both referenced legacy directories are missing. `make baseline-preserve`
therefore cannot verify their checksums. Phase 5 did not modify these directories;
its app/package tests use saved fixtures and owned compatibility contracts, all
of which remain present and pass. Snapshot retention/restoration must be resolved
before declaring the full migration acceptance criteria complete.

## Phase 6 — cleanup and independent releases: local delivery verified; exit pending remote CI

- Finalized Tournament's independent `frontend/` layout: source, API types,
  package/lockfile, strict TypeScript config and Vite config live together. The
  Python backend serves `frontend/dist`; Docker, Makefile, env loading and visual
  checks use the final paths.
- Removed the retired TypeScript server files/config, backend-only shared seeding
  implementation, temporary Python/Vitest transport adapters, duplicated contract
  copies and completed one-time structural generators.
- Ported all 44 legacy assertions to permanent native backend pytest: 19 HTTP
  scenarios (including a real network SSE server) and 25 calendar/classification/
  bracket/seeding scenarios. The full backend suite now has 72 tests; the frontend
  has its 9 format/score tests. `phase6/native-test-coverage.json` records the paths.
- Recovered both absent legacy source snapshots from the isolated copies. Every
  one of the 125 files matched its captured SHA-256 before copying; the recovery
  refused any existing destination. `phase6/snapshot-recovery.json` records this.
  Nested Git repositories/history were not available and have not been fabricated.
  Source checksum verification is operational again.
- Added git-based affected-app selection and independent tag planning/version
  checks, initially delivered for Gitea with GitHub mirrors. The subsequent
  GitHub conversion below supersedes that hosting setup.
  App-specific tags select/test/build/publish only that app's image. Stable tags
  also publish its `latest`; prerelease tags do not. Registry/runner details are
  documented in `docs/RELEASES.md`.
- Developer commands use `python -m pytest`/`python -m uvicorn`, avoiding stale
  virtualenv console-script shebangs after a workspace relocation. Baseline
  evidence arguments likewise normalize historical paths across relocations.

| Check | Result |
| --- | --- |
| Tournament native backend | 72 passed |
| Tournament frontend + strict typecheck/build | 9 passed; typecheck/build passed |
| Shared Python package | 7 passed |
| Shifts pytest + preserved workflow checks | 16 passed; 96 requests matched |
| CI/release/path/version tooling tests | 11 passed |
| Existing Tournament and Shifts SQLite fixtures | Adoption/startup/data checks passed |
| `make migration-visual-check` | All 14 captures match Phase 2 byte-for-byte |
| Tournament final-layout Docker build | Passed |
| Independent container smoke checks | Fresh/adopted Tournament and Shifts passed |
| `make baseline-preserve` | Recovered sources and all nine Tournament fixture tables verified |
| Current independent release plans | `tournament-v1.0.0` and `shifts-v0.1.0` validated |

### Final acceptance status

The applications are independently runnable/testable/buildable from their final
paths, with separate schemas/histories/databases/auth/version/image contracts.
Vue works against FastAPI, both share canonical branding, `crr-python` contains
only infrastructure, app-limited releases select one image, and production code
does not import snapshots or the retired Node backend.

The full migration is **not yet marked complete**:

1. Remote CI and authenticated registry publication have not run against these
   uncommitted changes. Local workflow/version/build checks do not substitute for
   an observed successful remote run.
2. The plan explicitly gates deleting Shifts' migrated requirements files on CI
   passing. They are retained until that condition is verified; runtime/CI use uv.
3. Recovered source content matches the freeze manifest, but original nested Git
   histories were absent from the available recovery copies. Their loss remains
   recorded as a historical limitation.

No tags, commits, pushes or registry publication were performed during this work.
`originals/` retains the recovered read-only source baseline. Once CI passes,
remove the two migrated Shifts requirements files and verify the release runner.

## GitHub Actions conversion

The primary remote is now `https://github.com/jfmcarreira/crr-tools.git`, with
default branch `main` confirmed through the GitHub API. `.github/workflows/`
is the active CI/release configuration; obsolete Gitea workflow mirrors were
removed. CI supports main pushes, pull requests and manual dispatch, retains
affected-app selection, and runs the automation-tooling checks before selection.

Independent release tags retain app-specific version validation and select one
image. The default registry is now always GHCR; release jobs authenticate with
the built-in `GITHUB_TOKEN` and `packages: write`. Current images are
`ghcr.io/jfmcarreira/crr-tournament` and `ghcr.io/jfmcarreira/crr-shifts`.
Explicit registry overrides remain supported. GitHub runners supply Docker;
the workflows provision Node 22 and Python 3.13 with pinned uv.

Verified locally: all 11 automation tests pass; both workflow YAML files parse,
CI triggers/manual dispatch and release tag/permission configuration match the
intended setup; both current app tags resolve to their GHCR image names; and
`git diff --check` passes. GitHub API lookup confirms the repository/default branch.

No commits, pushes, workflow dispatches or image publication are performed by
this change;
remote execution of the modified workflows remains pending verification.

## Next work

1. Verify GitHub Actions CI on Node 22/Python 3.13 after publishing the intended changes.
2. Remove Shifts' migrated requirements files after that successful CI run.
3. Verify an independent tagged release with configured registry credentials.

Phase 6's local implementation/checks are delivered; the exit conditions above
remain pending.
