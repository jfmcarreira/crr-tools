# TTLock

Standalone Python 3.13 uv workspace package, imported as `ttlock`. Its library
and CLI support listing account locks, listing lock passcodes, and generating
gateway-free whole-hour timed or one-time codes. Custom gateway-based PIN creation
is not supported. OAuth authentication,
token caching and one retry after explicit token expiry are automatic.
It has no Shifts imports, database, feature flags or authorization policies.

## CLI

Export `TTLOCK_CLIENT_ID`, `TTLOCK_CLIENT_SECRET`, `TTLOCK_USERNAME`,
`TTLOCK_PASSWORD` and `TTLOCK_LOCK_ID` privately. Every passcode operation uses
this single configured lock: neither the library nor CLI accepts a per-call
lock ID. The username/password belong to the mobile-app
account owning the lock, not the developer portal. Supply the original password;
the client applies the provider's required MD5 encoding. `TTLOCK_API_BASE_URL`
defaults to `https://euopen.ttlock.com` and must be an HTTPS origin.
The CLI does not load `.env` files or require Shifts' `SECRET_KEY`.

From the repository root:

```sh
uv run --package ttlock --locked ttlock list-locks
uv run --package ttlock --locked ttlock list-passcodes
uv run --package ttlock --locked ttlock generate-timed-pin
uv run --package ttlock --locked ttlock generate-one-time-pin
```

`python -m ttlock` is equivalent to the `ttlock` entry point. Credentials, API
region and lock ID come only from environment variables; there are no CLI
configuration overrides. Set `TTLOCK_LOCK_ID` once in the environment (or in `TTLockConfig` for
library callers). `list-locks` remains account-wide discovery and works without
`TTLOCK_LOCK_ID`, so it can be used to find the ID during initial setup.

Output is JSON. Lock listings omit administrative credentials/lock data; passcode
listings omit digits unless `--show-codes` is supplied. Generation prints the new
PIN and its validity dates: treat the terminal output as sensitive. These codes
can grant real physical access, independent of `TTLOCK_ENABLED`; run generation
only for supervised authorized tests. No custom-PIN creation, delete or
remote-unlock command is provided.

### Gateway-free generated codes

`generate-timed-pin` calls `/v3/keyboardPwd/get` with type 3 (period), rather than
installing a custom PIN. TTLock chooses the digits; no `--code` or `--minutes`
option is available. Its window is fixed to the **current and next UTC calendar
hour**: start at the current hour boundary and end two hour boundaries later.
At 12:50 UTC, the code covers 12:00–14:00 UTC (1 hour 10 minutes remaining).
This is not two hours from creation. The policy lives in the library, not just
the CLI; there are no start/end or duration overrides.

```sh
python -m ttlock generate-timed-pin
```

Both generation commands use the current UTC hour boundary. Keep the lock's
clock/timezone correctly configured and verify physical validity before relying
on a code. TTLock documents that period codes must be used at least once within
24 hours of their start, or they are invalidated.

`generate-one-time-pin` uses type 1: **one successful use within six hours of the
start**, not six hours after creation and not a 15-minute expiry. There are no
start or duration overrides. JSON includes `singleUse`, the type and the
validity dates; for one-time codes `endDate` is the documented six-hour deadline,
and the code stops working earlier once used.

Both default to passcode version 4; `--passcode-version` can specify the actual
lock version (1–4). Earlier versions have provider-specific capabilities; consult
TTLock's documentation before using them. Generation requires valid account
permissions but does not write a chosen code through a gateway. Returned PINs
are sensitive and should not be pasted into logs or chats.
With the workspace environment activated and credentials exported, use
`python -m ttlock ...` directly; `uv` is not required at runtime.

These commands do not write to any application's database or issuance ledger.
Shifts consumes generated timed codes through its own configuration adapter and
keeps authorization, encrypted storage, duplicate prevention and reconciliation
in the application. Its existing records retain their stored validity dates.

`list-locks` combines `/v3/lock/list` (owned locks) with `/v3/key/list` (account
eKeys, including shared locks), deduplicating by `lockId`. It includes reported
`userType` (`110301` admin, `110302` common user), `keyRight` (0 not authorized,
1 authorized), `keyStatus`, `remoteEnable` (1 enabled, 2 disabled), and eKey
validity dates when supplied by TTLock. These are provider metadata, not a
guarantee that passcode generation is permitted or supported. Ordinary shared
access or remote-unlock permission alone may not allow PIN management. The API
still enforces permissions and the lock must support the requested passcode type.
An eKey-list failure is reported as an error, not silently hidden as a partial list.

Errors go to stderr with exit code 1 (API/configuration failure) or 2 (usage/input).
Transport failures during creation are uncertain and **never automatically
retried**: inspect the lock's passcodes before doing anything else. Running the
command again can create another PIN; the standalone package has no issuance
ledger/idempotency guarantee. Verify physical opening and exact expiry, including
when the gateway is offline. A cloud response alone does not prove door behavior.
Keep HTTP body/wire debugging disabled; tokens, credentials and PINs are sensitive.

## Library

```python
from ttlock import TTLockClient, TTLockConfig

api = TTLockClient(TTLockConfig.from_env())
locks = api.list_locks()
passcodes = api.list_passcodes()
hourly = api.generate_timed_pin(
    keyboard_pwd_name="Hourly test",
)
single_use = api.generate_one_time_pin(
    keyboard_pwd_name="Single-use test",
)
```

Configuration can also be provided explicitly or via a zero-argument callable for
live settings. Generated timed/one-time codes determine their
windows automatically. Their returned dictionaries include the configured
`lockId` and the actual `startDate`/`endDate` in epoch milliseconds; for one-time
codes the end is the documented six-hour deadline. Library methods return provider
dictionaries, including sensitive fields; CLI output uses a safe field allowlist.
Inject `client=httpx.Client(...)` for tests; that client remains caller-owned.
`TTLockError.code` is sanitized and `.uncertain` distinguishes possibly successful
generations. For uncertain generation failures, `.start_date` and `.end_date`
carry the requested validity window in epoch milliseconds, without credentials
or digits, so consumers can reconcile across hour boundaries.
Authorization, encrypted storage, reconciliation policy and duplicate
prevention belong to the consuming app.

Run `make ttlock-test`. Tests mock all HTTP traffic and never contact a real lock.
Tournament does not depend on this package. No separate public release stream
is introduced. Shifts consumes this package through its configuration adapter.
