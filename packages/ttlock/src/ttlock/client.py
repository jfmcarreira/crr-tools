from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import TTLockConfig


class _HideTokenURLs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # httpx INFO request logs include query-string access tokens.
        return "accessToken=" not in record.getMessage()


logging.getLogger("httpx").addFilter(_HideTokenURLs())


class TTLockError(RuntimeError):
    """Sanitized failure: never include API response bodies or credentials."""

    def __init__(self, code: str, *, uncertain: bool = False):
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain
        # Safe operation metadata for reconciliation; never attach credentials or digits.
        self.start_date: int | None = None
        self.end_date: int | None = None


class TTLockClient:
    def __init__(self, config: TTLockConfig | Callable[[], TTLockConfig], *,
                 client: httpx.Client | None = None) -> None:
        self._config = config
        self.client = client
        self._token = ""
        self._expires_at = 0.0
        self._credentials: TTLockConfig | None = None
        self._token_lock = threading.Lock()

    def _resolve_config(self, *, require_lock: bool = False) -> TTLockConfig:
        config = self._config() if callable(self._config) else self._config
        try:
            config.validate(require_lock=require_lock)
        except ValueError:
            raise TTLockError("invalid_configuration") from None
        return config

    @property
    def lock_id(self) -> str:
        return self._resolve_config(require_lock=True).lock_id

    def _request(self, config: TTLockConfig, method: str, path: str, payload: dict,
                 *, creating: bool = False) -> dict:
        # Never retry transport failures: a create may already have succeeded.
        def send(client: httpx.Client) -> httpx.Response:
            kwargs = {"data" if method == "POST" else "params": payload}
            return client.request(method, f"{config.api_base_url.rstrip('/')}{path}", follow_redirects=False, **kwargs)

        try:
            if self.client is not None:
                response = send(self.client)
            else:
                with httpx.Client(timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
                    response = send(client)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError
        except (httpx.HTTPError, ValueError):
            raise TTLockError("invalid_response", uncertain=creating) from None
        code = body.get("errcode", 0)
        if code not in (None, 0, "0"):
            safe_code = str(code) if str(code).lstrip("-").isdigit() else "rejected"
            raise TTLockError(f"api_{safe_code}", uncertain=creating and safe_code not in {"10004", "-3009"})
        return body

    def _refresh_token(self, config: TTLockConfig, *, force: bool = False) -> str:
        with self._token_lock:
            if not force and self._credentials == config and time.monotonic() < self._expires_at:
                return self._token
            body = self._request(config, "POST", "/oauth2/token", {
                "clientId": config.client_id,
                "clientSecret": config.client_secret,
                "username": config.username,
                # Required by the provider's password grant, not for local storage.
                "password": hashlib.md5(config.password.encode(), usedforsecurity=False).hexdigest(),
            })
            token = body.get("access_token")
            try:
                lifetime = int(body["expires_in"])
            except (KeyError, ValueError, TypeError):
                raise TTLockError("invalid_token_response") from None
            if not isinstance(token, str) or not token or lifetime <= 0:
                raise TTLockError("invalid_token_response")
            self._token = token
            self._expires_at = time.monotonic() + max(0, lifetime - 60)
            self._credentials = config
            return token

    def _authenticated(self, method: str, path: str, payload: dict, *, creating: bool = False,
                       config: TTLockConfig | None = None) -> dict:
        # One immutable configuration snapshot per operation, including retries.
        config = config if config is not None else self._resolve_config()
        payload = {**payload, "clientId": config.client_id, "accessToken": self._refresh_token(config)}
        try:
            return self._request(config, method, path, payload, creating=creating)
        except TTLockError as exc:
            if exc.code != "api_10004":
                raise
            # Explicit expired-token rejection cannot have created a PIN.
            payload["accessToken"] = self._refresh_token(config, force=True)
            return self._request(config, method, path, payload, creating=creating)

    def _generate_pin(self, *, keyboard_pwd_name: str,
                      start_at_utc: datetime, keyboard_pwd_type: int,
                      keyboard_pwd_version: int, end_at_utc: datetime | None = None) -> dict[str, Any]:
        if keyboard_pwd_version not in (1, 2, 3, 4):
            raise ValueError("Passcode version must be 1, 2, 3 or 4")
        dates = [start_at_utc] if end_at_utc is None else [start_at_utc, end_at_utc]
        for value in dates:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Generated passcodes require timezone-aware dates")
            utc = value.astimezone(timezone.utc)
            if utc.minute or utc.second or utc.microsecond:
                raise ValueError("Generated passcodes require whole UTC hour boundaries")
        if end_at_utc is not None and end_at_utc.astimezone(timezone.utc) <= start_at_utc.astimezone(timezone.utc):
            raise ValueError("End time must be after start time")
        config = self._resolve_config(require_lock=True)
        payload = {
            "lockId": config.lock_id, "keyboardPwdName": keyboard_pwd_name,
            "keyboardPwdVersion": keyboard_pwd_version, "keyboardPwdType": keyboard_pwd_type,
            "startDate": int(start_at_utc.timestamp() * 1000),
            "date": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        if end_at_utc is not None:
            payload["endDate"] = int(end_at_utc.timestamp() * 1000)
        end = end_at_utc if end_at_utc is not None else start_at_utc + timedelta(hours=6)
        end_date = int(end.timestamp() * 1000)
        # This GET generates a passcode: treat failures like creation, not a read.
        try:
            body = self._authenticated("GET", "/v3/keyboardPwd/get", payload, creating=True, config=config)
            code = body.get("keyboardPwd")
            if (not isinstance(code, str) or not code.isascii() or not code.isdigit()
                    or not str(body.get("keyboardPwdId", "")).isdigit() or int(body["keyboardPwdId"]) <= 0):
                raise TTLockError("invalid_generated_passcode_response", uncertain=True)
        except TTLockError as exc:
            if exc.uncertain:
                exc.start_date = payload["startDate"]
                exc.end_date = end_date
            raise
        # Include the exact requested window, so callers never recalculate across an hour boundary.
        return {**body, "lockId": config.lock_id, "startDate": payload["startDate"],
                "endDate": end_date}


    def _list(self, path: str, payload: dict, *, config: TTLockConfig | None = None) -> list[dict]:
        records = []
        for page in range(1, 101):
            body = self._authenticated("GET", path, {
                **payload, "pageNo": page, "pageSize": 200,
                "date": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, config=config)
            if not isinstance(body.get("list"), list) or not all(isinstance(row, dict) for row in body["list"]):
                raise TTLockError("invalid_list_response")
            records.extend(body["list"])
            try:
                if page >= int(body["pages"]):
                    return records
            except (KeyError, ValueError, TypeError):
                raise TTLockError("invalid_list_response") from None
        raise TTLockError("too_many_pages")

    def generate_timed_pin(self, *, keyboard_pwd_name: str,
                           keyboard_pwd_version: int = 4) -> dict[str, Any]:
        """Generate a period code covering the current and next UTC calendar hour."""
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return self._generate_pin(
            keyboard_pwd_name=keyboard_pwd_name, start_at_utc=start,
            end_at_utc=start + timedelta(hours=2), keyboard_pwd_type=3, keyboard_pwd_version=keyboard_pwd_version,
        )

    def generate_one_time_pin(self, *, keyboard_pwd_name: str,
                              keyboard_pwd_version: int = 4) -> dict[str, Any]:
        """Generate a single-use code usable within six hours of its start (type 1)."""
        return self._generate_pin(
            keyboard_pwd_name=keyboard_pwd_name,
            start_at_utc=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            keyboard_pwd_type=1, keyboard_pwd_version=keyboard_pwd_version,
        )

    def list_locks(self) -> list[dict]:
        """Discover owned and shared locks, including reported eKey permissions."""
        owned = self._list("/v3/lock/list", {})
        keys = self._list("/v3/key/list", {})
        locks: dict[str, dict] = {}
        permission_fields = ("keyId", "userType", "keyStatus", "keyRight", "remoteEnable", "startDate", "endDate")
        for record in owned + keys:
            lock_id = str(record.get("lockId", ""))
            if not lock_id.isdigit() or int(lock_id) <= 0:
                raise TTLockError("invalid_list_response")
            lock_id = str(int(lock_id))
            if lock_id not in locks:
                locks[lock_id] = dict(record)
            else:
                # Keep owned lock details, filling missing fields from the eKey.
                for field, value in record.items():
                    locks[lock_id].setdefault(field, value)
        for key in keys:
            lock = locks[str(int(key["lockId"]))]
            for field in permission_fields:
                if field in key:
                    lock[field] = key[field]
        return list(locks.values())

    def list_passcodes(self) -> list[dict]:
        config = self._resolve_config(require_lock=True)
        return self._list("/v3/lock/listKeyboardPwd", {"lockId": config.lock_id, "orderBy": 1}, config=config)
