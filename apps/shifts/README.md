# Contínuos CRR — Shifts

Public registration is disabled by default. Set `REGISTRATION_ENABLED=true` to
show the sign-up link. Users must enter an existing active, unassigned team's
name (case-insensitive); registration claims that team and signs them in.
Assigned teams cannot be claimed again. All registration attempts count toward
a limit of five per client IP per five minutes, including successful attempts.
The limiter is process-local; use one worker or enforce a shared limit at the
reverse proxy, and configure trusted proxy addresses correctly. A team name is
not a secret: enable this only when name-based claiming is appropriate.

The FastAPI server lives in `server/`; the server-rendered UI lives in `ui/`.
Models, services, security primitives and domain routers remain separate from
Jinja templates and browser assets, with the established Jinja/form contracts
and `0001_initial` Alembic history. Python dependencies are managed with `uv`
and the root `uv.lock`.

```text
apps/shifts/
├── server/
│   ├── app/          # Python routes, domain logic, persistence and security
│   ├── migrations/   # Independent Alembic history
│   └── tests/        # Server and UI integration tests
└── ui/
    ├── templates/    # Jinja HTML pages
    └── static/       # CSS, JavaScript, PWA manifest and service worker
```

The UI is served by FastAPI, not a separate frontend process or build.

The internal `crr-python` workspace dependency supplies synchronous engine
construction and Alembic configuration. Shifts owns its sessions, backups,
startup database handling and migration history. Docker installs the shared package
as a wheel alongside the app's dependencies.

The canonical logo, favicon and common CSS live in `packages/crr-brand`, mounted
at `/brand` with root-path-aware Jinja links. PDF exports read that same logo.
App-specific layouts and forms remain in `ui/static/app.css`; Docker
copies the UI and brand package into the image alongside the server.

From the repository root:

```sh
make shifts-test
make shifts-dev
make shifts-debug
```

Copy the repository-root `.env.example` to `.env` and configure
`SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`, and the remaining deployment settings.
Both are enforced: startup fails without a `SECRET_KEY` of at least 32 random
characters (e.g. `openssl rand -hex 24`), and the first start refuses to create
the administrator with an empty or placeholder `INITIAL_ADMIN_PASSWORD`.
The local server listens on port 8000. Migrations, backups and initial data run
on startup. `make shifts-dev` and `make shifts-debug` create repository-root
`data/shifts/` and use `data/shifts/bar_rota.db`, overriding `DATABASE_URL` from
`.env`. Existing databases at older paths are not moved. For manual CLI runs,
the root `.env.example` uses that same location relative to `server/`; create
`data/shifts/` from the repository root before initializing the database.

`make shifts-debug` uses the workspace's `.venv/bin/python` directly (like
`shifts-dev`), so it does not invoke pyenv or uv at runtime. The environment must
already contain the app's development dependencies, including `debugpy`.
It runs the backend with development-only `debugpy`, listening
on `127.0.0.1:5678`. It waits for a debugger connection before starting Uvicorn
on port 8000 and disables auto-reload. Stop any backend already using port 8000
first. In VS Code, install the Python Debugger extension and use an attach
configuration with `"type": "debugpy"`, `"request": "attach"` and
`"connect": {"host": "127.0.0.1", "port": 5678}`. Do not expose the debugger port
publicly. The same repository-root `.env` and startup database behavior apply.

```sh
docker compose up --build shifts
make shifts-build
```

Compose loads the repository-root `.env`. The `shifts-data` volume contains
`/data/bar_rota.db`; this database is independent from Tournament. The image is
`crr-shifts`, targeting Python 3.13. Initial Python project version is `0.1.0`;
future release tags use `shifts-v...`.

For administrative CLI commands:

```sh
uv run --directory apps/shifts/server --package crr-shifts --locked python -m app.cli init-db
uv run --directory apps/shifts/server --package crr-shifts --locked python -m app.cli seed-demo
```

Tests use isolated synthetic SQLite data and disabled SMTP. `make shifts-test`
runs the backend pytest suite; production dependencies come from
`pyproject.toml`/`uv.lock` via uv.

See `docs/DOMAIN.md` for domain rules and `docs/ARCHITECTURE.md` for the current
module layout, application lifecycle and deployment commands.

## PWA push notifications

Administrators can pause/resume all delivery on **Notificações** using the
**Interruptores gerais de notificações** checkboxes and **Guardar** button.
Email and push have independent global flags, gating every event without
modifying user email preferences or device subscriptions. When resumed,
those personal preferences still apply. Paused notifications are recorded as
skipped (push only for configured, subscribed devices), not queued for later.
The flags persist as `(__master__, email)` and `(__master__, push)` settings in
the table from migration `0007_notification_settings` (no new schema required).
Until saved, each flag inherits the previous `(__master__, all)` switch, or
defaults to on when no switch exists. Legacy per-event rows are not consulted.

The **Calendário** page has an **Ativar notificações** button and a per-device
disable button. Push follows the existing shift changes, swaps and CLI reminders,
independently of email preferences/SMTP. Each user's subscribed devices receive
one push per event; failures are recorded with `channel=push` in notification logs.
Expired subscriptions (HTTP 404/410) are removed automatically. Sending is
best-effort, not a guarantee of delivery; it currently runs synchronously with a
10-second timeout per device. The existing reminder CLI still needs its scheduled
invocation; push does not add a new reminder timer.

Configure `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` in
the repository-root `.env`. The subject should be a contact such as `mailto:admin@example.com`.
Generate a key pair locally (keep the private key secret):

```sh
uv run --directory apps/shifts/server --package crr-shifts --locked python - <<'PY'
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
key = ec.generate_private_key(ec.SECP256R1())
encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
print("VAPID_PRIVATE_KEY=" + encode(key.private_numbers().private_value.to_bytes(32, "big")))
print("VAPID_PUBLIC_KEY=" + encode(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)))
PY
```

Keep the same keys across deployments; changing them requires devices to
unsubscribe and enable notifications again. Restart the app after configuring
them; migration `0006_push_subscriptions` runs on startup without changing
existing accounts. Serve over HTTPS (localhost is suitable for development).
On iPhone/iPad, iOS 16.4+ requires adding the PWA to the Home Screen and opening
it there before enabling notifications. Browser-blocked permissions must be
changed in browser settings. Notifications may show shift details on the lock
screen; on shared devices, disable notifications before signing out. Signing out
does not remove a subscription, so reminders still arrive while the app is closed.

The root-scoped `/sw.js` route and subscription requests honor `ROOT_PATH`.
Subscription endpoints are limited to the standard Google, Mozilla, Apple and
Windows push providers to prevent server-side requests to arbitrary hosts.
Verify on a real device by enabling notifications and triggering a shift-change
or reminder event; automated tests mock provider delivery.

## TTLock timed door PINs

The API client lives in [`packages/ttlock`](../../packages/ttlock/README.md), with
standalone discovery/listing and generated timed/one-time PIN CLI commands.
`server/app/services/ttlock.py` adapts Shifts' live settings and configured lock.
Shifts uses **generated period codes**, not custom or one-time codes; permissions,
the encrypted ledger and reconciliation remain owned by Shifts.
The CLI reads exported `TTLOCK_*` credentials (not `.env` automatically) and does
not require Shifts' `SECRET_KEY` or database. It can test the lock while
`TTLOCK_ENABLED=false`: creating a CLI PIN is a real, separate physical-access
operation, not a Shifts assignment request. See the package README for commands,
sensitive-output precautions and uncertain-create handling.

Keep `TTLOCK_ENABLED=false` until a supervised physical test proves generation
and whole-hour validity on the configured lock. `/v3/keyboardPwd/get` selects the
digits and requires no gateway write. The lock/account must support generated
period passcodes (version 4 by default). Codes cover the **current and next UTC
calendar hour**: a request at 12:50 UTC covers 12:00–14:00 UTC, leaving 1 hour
10 minutes. This is not two hours from issuance, and is not a 15-minute code.
Clock/timezone configuration on the lock must be correct.
There is no callback/webhook requirement: leave TTLock's unlock-record callback unset.

Configure these privately in the repository-root `.env` (never commit or send credentials):

- `TTLOCK_CLIENT_ID` and `TTLOCK_CLIENT_SECRET`: Open Platform application credentials.
- `TTLOCK_USERNAME` and `TTLOCK_PASSWORD`: the **TTLock mobile-app account** owning
  the lock or holding an appropriately authorized shared eKey, not the
  developer-portal account. Enter the password normally; the
  backend applies TTLock's required MD5 encoding for its OAuth password grant.
- `TTLOCK_LOCK_ID`: the physical lock's cloud ID.
- `TTLOCK_API_BASE_URL`: the account's regional HTTPS API endpoint (EU default).
- `TTLOCK_ELIGIBLE_SCHEDULE_SLUGS`: comma-separated schedule slugs; empty means no
  eligible schedules. Find slugs in the admin schedule configuration.
- `TTLOCK_ENCRYPTION_KEY`: a separate Fernet key, different from `SECRET_KEY`.
  Generate locally from `server/` with:

  ```sh
  uv run --package crr-shifts --locked python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
  ```

Preserve the encryption key while PINs are valid; replacing it makes stored PINs
unreadable. PINs and access tokens never go in session cookies or user-facing URLs. Keep HTTP
wire/body debugging disabled in production and keep clocks synchronized.

Enable “Códigos da Porta” only for approved users in the admin user
page. They may request a code during the first hour of an actual assigned shift,
including overnight shifts. Validity covers the current and next UTC hour even
when the shift ends sooner; the actual dates returned by the module are stored.
Existing codes keep their original stored expiry, including old 15-minute codes.
One PIN reservation is allowed per user/assignment/lock; retries do
not create new codes. The dashboard's independent “Ver código” section remains
available if permissions or assignments change after issuance.

`/admin/access` shows recent issuance status, **never PIN digits**. For a timeout
or uncertain result, use “Confirmar na fechadura” to match the lock, reservation's
unique name, type and exact validity dates against TTLock. A pending generation
contains no digits until a successful response or a single unambiguous cloud
match; recovered digits are encrypted before the code becomes viewable. Legacy
reservations with encrypted digits still require an exact-digit match.
Timeouts retain the actual requested hour window when available, including
requests crossing an hour boundary. This only confirms an existing
code; it does not retry creation, delete a code or allow a replacement. A missing
cloud record is not proof that a delayed creation cannot still finish.

The Shifts app automatically clears expired digits on startup and **every 60
seconds**, including when the website is idle or TTLock is disabled. No separate
cron job or Compose service is needed. Each run uses its own database session;
failures are logged safely and retried on the next interval. Shutdown waits for
any in-flight cleanup. Multiple app workers may run the same idempotent cleanup.

Expired digits are also cleared on signed-in dashboard/access-page requests.
For a manual cleanup while the app is stopped, use:

```sh
docker compose exec -T shifts python -m app.cli expire-access-pins
```

Cleanup only removes locally encrypted digits and retains audit metadata. It
never deletes or revokes lock passcodes. Database backups may retain old encrypted values; protect
them and apply a limited backup retention policy.

Turning off a user's permission or `TTLOCK_ENABLED` blocks **new** requests only.
Generated codes are validated offline: removing a cloud/app entry is not proof
that the physical lock has revoked it. For emergency early revocation, the owner
must use the lock's supported management procedure and verify physical rejection.
Keep `REGISTRATION_ENABLED=false` for physical-access deployments.

### Live acceptance test

First use the standalone CLI to discover the lock ID, inspect passcode metadata
and test one supervised generated period PIN without enabling Shifts. Verify physical
expiry, then run the app-level acceptance checks below: CLI tests do not exercise
Shifts authorization, duplicate prevention or encrypted storage.

1. Configure the lock/account and credentials; temporarily enable TTLock for a
   supervised test with an authorized user and current eligible assignment.
2. Request once and repeat the request: confirm the same PIN and one cloud record.
3. Prove the PIN opens the physical door, and fails at its displayed whole-hour expiry.
4. Check timed expiry offline, without assuming cloud deletion revokes a code.
5. Disable the user's permission: new POSTs must fail, while an already-issued
   code remains viewable and works only until its original expiry.
6. Verify automatic cleanup and the status page. Disable TTLock again if any
   check fails. Automated tests use mocked TTLock HTTP, not a real lock.

Migration `0005_users_email_unique` restores the email uniqueness omitted by the
existing `0004` batch schema without rewriting migration history. If duplicate
emails were saved while that constraint was absent, resolve them before upgrading;
the migration deliberately does not modify account data automatically.
