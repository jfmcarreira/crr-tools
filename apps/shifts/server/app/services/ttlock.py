"""Shifts configuration adapter for the standalone TTLock client."""
from __future__ import annotations

from typing import Any

import httpx
from ttlock import TTLockClient as _TTLockClient, TTLockConfig, TTLockError

from ..config import settings


def _config() -> TTLockConfig:
    return TTLockConfig(
        api_base_url=settings.ttlock_api_base_url, client_id=settings.ttlock_client_id,
        client_secret=settings.ttlock_client_secret, username=settings.ttlock_username,
        password=settings.ttlock_password, lock_id=settings.ttlock_lock_id,
    )


class TTLockClient(_TTLockClient):
    """Compatibility constructor resolving the app's live configuration."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        super().__init__(_config, client=client)

    def list_passcodes(self, lock_id: str | None = None) -> list[dict]:
        # Existing ledgers carry a lock ID. Never reconcile them against another lock.
        if lock_id is not None and lock_id != self.lock_id:
            raise TTLockError("lock_mismatch")
        return super().list_passcodes()


ttlock_client = TTLockClient()


def issue_pin_via_ttlock(*, lock_id: str, name: str) -> dict[str, Any]:
    """Generate a period code for the configured lock's current and next hour."""
    if not settings.ttlock_enabled:
        raise TTLockError("disabled")
    if lock_id != ttlock_client.lock_id:
        raise TTLockError("lock_mismatch")
    return ttlock_client.generate_timed_pin(keyboard_pwd_name=name)
