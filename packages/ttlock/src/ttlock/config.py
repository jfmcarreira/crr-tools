from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class TTLockConfig:
    api_base_url: str = "https://euopen.ttlock.com"
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    lock_id: str = ""

    @classmethod
    def from_env(cls) -> TTLockConfig:
        return cls(
            api_base_url=os.environ.get("TTLOCK_API_BASE_URL", "https://euopen.ttlock.com"),
            client_id=os.environ.get("TTLOCK_CLIENT_ID", ""),
            client_secret=os.environ.get("TTLOCK_CLIENT_SECRET", ""),
            username=os.environ.get("TTLOCK_USERNAME", ""),
            password=os.environ.get("TTLOCK_PASSWORD", ""),
            lock_id=os.environ.get("TTLOCK_LOCK_ID", ""),
        )

    def validate(self, *, require_lock: bool = False) -> None:
        url = urlsplit(self.api_base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("api_base_url must be an HTTPS origin without credentials")
        if not all((self.client_id, self.client_secret, self.username, self.password)):
            raise ValueError("TTLock credentials are missing")
        if require_lock and (not self.lock_id.isascii() or not self.lock_id.isdigit() or int(self.lock_id) <= 0):
            raise ValueError("TTLOCK_LOCK_ID must be a positive numeric lock ID")
