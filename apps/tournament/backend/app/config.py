from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Both are required with no development default: ADMIN_PASSWORD is the only
    # credential of the admin API, and SESSION_SECRET is the HMAC key of every
    # session token (long enough that captured cookies cannot be forged offline).
    admin_password: str = ""
    session_secret: str = ""
    database_path: str = "/data/tournament.sqlite"
    app_base_path: str = "/"
    client_dist_path: Path = Path(__file__).resolve().parents[2] / "frontend/dist"
    trust_proxy: bool = False
    # Comma-separated IPs/CIDRs allowed to set X-Forwarded-* when trust_proxy is on.
    # "*" trusts every client, which lets X-Forwarded-For be spoofed and defeats
    # the login rate limit; list only the reverse proxy's own addresses instead.
    trusted_proxies: str = "127.0.0.1"
    # None decides per request (HTTPS, or via the trusted proxy); set true/false to force.
    session_cookie_secure: bool | None = None
    session_lifetime_ms: int = 7 * 24 * 60 * 60 * 1000

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env",
        env_file_encoding="utf-8", extra="ignore",
    )

    @field_validator("app_base_path")
    @classmethod
    def normalize_base(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError('APP_BASE_PATH tem de começar por "/".')
        return value if value.endswith("/") else value + "/"

    @model_validator(mode="after")
    def _require_secrets(self) -> "Settings":
        if not self.admin_password:
            raise ValueError(
                "ADMIN_PASSWORD tem de estar definida; não existe valor padrão."
            )
        if len(self.session_secret) < 32:
            raise ValueError(
                "SESSION_SECRET tem de ter pelo menos 32 caracteres; defina-a no .env."
            )
        return self
