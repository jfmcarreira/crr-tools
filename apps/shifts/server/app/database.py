from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from crr_common.database import create_sync_engine
from crr_common.migrations import migration_config
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class Base(DeclarativeBase):
    pass


engine = create_sync_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def alembic_config() -> Config:
    return migration_config(MIGRATIONS_DIR.parent / "alembic.ini", MIGRATIONS_DIR,
                            database_url=settings.database_url)


def run_migrations() -> None:
    """Bring the database up to the latest revision. Safe to call on every start."""
    command.upgrade(alembic_config(), "head")


def current_revision() -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()



def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_file(url: str | None = None) -> Path | None:
    """The SQLite file behind DATABASE_URL, or None for another engine."""
    raw = url or settings.database_url
    if not raw.startswith("sqlite"):
        return None
    path = urlparse(raw).path
    if not path:
        return None
    # sqlite:///./data/x.db is relative, sqlite:////srv/x.db is absolute.
    if path.startswith("/"):
        path = path[1:]
    if not path or path.startswith(":memory:"):
        return None
    return Path(path)


def backup_database(destination_dir: str | None = None) -> Path | None:
    """Copy the database aside on every start, never overwriting an older copy.

    Uses SQLite's own backup API so the copy is consistent even if another
    process is writing. Returns the new file, or None when there is nothing to copy.
    """
    source = database_file()
    if source is None or not source.is_file():
        return None

    folder = Path(destination_dir or settings.backup_dir or source.parent / "backups")
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"{source.stem}-{stamp}{source.suffix}"
    index = 1
    while target.exists():  # two starts in the same second
        target = folder / f"{source.stem}-{stamp}-{index}{source.suffix}"
        index += 1

    with sqlite3.connect(source) as origin, sqlite3.connect(target) as copy:
        origin.backup(copy)
    shutil.copystat(source, target)
    return target
