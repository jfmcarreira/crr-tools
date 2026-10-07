from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_password: str = Field(min_length=1)
    session_secret: str = Field(min_length=1)
    database_path: str = "/data/tournament.sqlite"
    app_base_path: str = "/"
    client_dist_path: Path = Path(__file__).resolve().parents[2] / "frontend/dist"
    trust_proxy: bool = False
    session_lifetime_ms: int = 7 * 24 * 60 * 60 * 1000

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    @field_validator("app_base_path")
    @classmethod
    def normalize_base(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError('APP_BASE_PATH tem de começar por "/".')
        return value if value.endswith("/") else value + "/"
