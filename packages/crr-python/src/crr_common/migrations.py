from pathlib import Path

from alembic.config import Config
from sqlalchemy import URL
from sqlalchemy.engine import Connection


def migration_config(
    ini_path: str | Path,
    script_location: str | Path,
    *,
    database_url: str | URL | None = None,
    connection: Connection | None = None,
) -> Config:
    """Prepare Alembic wiring; the caller owns migration policy and connections."""
    config = Config(str(Path(ini_path).resolve()))
    config.set_main_option("script_location", str(Path(script_location).resolve()).replace("%", "%%"))
    if database_url is not None:
        url = database_url.render_as_string(hide_password=False) if isinstance(database_url, URL) else database_url
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config
