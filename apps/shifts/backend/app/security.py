from __future__ import annotations

import hashlib
import hmac
import os
import secrets

ITERATIONS = 310_000


MIN_PASSWORD_LENGTH = 4


def hash_password(password: str) -> str:
    if len(password.strip()) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"A palavra-passe tem de ter pelo menos {MIN_PASSWORD_LENGTH} caracteres"
        )
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
