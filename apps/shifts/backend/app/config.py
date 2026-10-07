from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Contínuos CRR"
    # HMAC key of the signed session cookie: required, and long enough that a
    # captured cookie cannot be forged. There is deliberately no development
    # default — a known key would let anyone mint an admin session.
    secret_key: str = ""
    database_url: str = "sqlite:///./data/bar_rota.db"
    base_url: str = "http://localhost:8000"
    # Prefix the reverse proxy serves the app under, e.g. "/crr" for https://host/crr/.
    # The proxy must forward that prefix (X-Forwarded-Prefix) or the paths here must match.
    root_path: str = ""
    # Networks allowed to set X-Forwarded-*; "*" for a private docker network.
    trusted_proxy_hosts: str = "*"
    # Secret token of the whole-rota calendar feed; every person also has their own.
    calendar_token: str = ""
    # Where the startup copies of the SQLite file go; empty means "backups" beside it.
    backup_dir: str = ""
    # Timezone of the calendar feed, so shifts show at the bar's own wall-clock time.
    timezone: str = "Europe/Lisbon"

    initial_admin_name: str = "Administrador"
    initial_admin_username: str = "admin"
    initial_admin_email: str = "admin@example.com"
    initial_admin_password: str = "change-me-now"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "bar-rota@example.com"
    smtp_starttls: bool = True
    reminder_days_ahead: int = 1
    # Secure by default; set false only for plain-HTTP development.
    session_https_only: bool = True

    @model_validator(mode="after")
    def _require_strong_secret_key(self) -> Settings:
        if len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY tem de ter pelo menos 32 caracteres; defina-a no .env "
                "(não existe valor padrão de propósito)."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def prefix(self) -> str:
        """The path the reverse proxy serves the app under, without a trailing slash."""
        return self.root_path.rstrip("/")

    def url(self, path: str) -> str:
        """Prefix an internal path so it keeps working under a sub-path deployment."""
        if not self.prefix or not path.startswith("/") or path.startswith("//"):
            return path
        cut = min(
            (index for index in (path.find("?"), path.find("#")) if index != -1),
            default=len(path),
        )
        return f"{self.prefix}{path[:cut]}{path[cut:]}"


settings = Settings()
