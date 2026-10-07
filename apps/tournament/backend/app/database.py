from pathlib import Path

from alembic import command
from crr_common.database import create_sync_engine
from crr_common.migrations import migration_config
from sqlalchemy import URL, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]


def create_database_engine(path: str) -> Engine:
    if path != ":memory:":
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
    options = {"poolclass": StaticPool} if path == ":memory:" else {}
    engine = create_sync_engine(URL.create("sqlite", database=path), **options)

    @event.listens_for(engine, "connect")
    def pragmas(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config = migration_config(
            BACKEND / "alembic.ini",
            BACKEND / "migrations",
            database_url=engine.url,
            connection=connection,
        )
        command.upgrade(config, "head")
