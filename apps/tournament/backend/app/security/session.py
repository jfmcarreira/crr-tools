import base64
import hashlib
import hmac
import json
import math
import time

from ..config import Settings

COOKIE_NAME = "tournament_admin_session"


def timestamp_ms() -> int:
    return int(time.time() * 1000)


def encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign(payload: str, secret: str) -> str:
    return encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def create_token(settings: Settings, now: int | None = None) -> str:
    expiry = (timestamp_ms() if now is None else now) + settings.session_lifetime_ms
    payload = encode(json.dumps({"expiresAt": expiry}, separators=(",", ":")).encode())
    return payload + "." + sign(payload, settings.session_secret)


def valid_token(token: str | None, settings: Settings, now: int | None = None) -> bool:
    if not token or token.count(".") != 1:
        return False
    payload, signature = token.split(".")
    if not payload or not hmac.compare_digest(signature.encode(), sign(payload, settings.session_secret).encode()):
        return False
    try:
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        expiry = value.get("expiresAt")
        return type(expiry) in (int, float) and math.isfinite(expiry) and expiry > (timestamp_ms() if now is None else now)
    except (ValueError, TypeError, AttributeError):
        return False


def password_matches(actual: str, expected: str) -> bool:
    return hmac.compare_digest(actual.encode(), expected.encode())
