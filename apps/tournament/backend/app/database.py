import re
from pathlib import Path

from alembic import command
from crr_common.database import create_sync_engine
from crr_common.migrations import migration_config
from sqlalchemy import CheckConstraint, DefaultClause, UniqueConstraint, URL, event, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool

from .models import Base

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


def normalized(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).lower()


def validate_legacy_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    if set(inspector.get_table_names()) - {"alembic_version"} != set(Base.metadata.tables):
        raise RuntimeError("Tournament database does not match the legacy table set; adoption refused.")
    for name, table in Base.metadata.tables.items():
        actual = inspector.get_columns(name)
        if [column["name"] for column in actual] != list(table.columns.keys()):
            raise RuntimeError(f"Legacy columns differ: {name}; adoption refused.")
        for column in actual:
            expected = table.columns[column["name"]]
            # SQLite reflects an INTEGER PRIMARY KEY as nullable, despite its implicit NOT NULL.
            if (str(column["type"]) != str(expected.type).split(" COLLATE")[0] or
                (not (expected.primary_key and len(table.primary_key.columns) == 1) and column["nullable"] != expected.nullable)):
                raise RuntimeError(f"Legacy column type/nullability differs: {name}.{expected.name}")
            default = column["default"]
            expected_default = str(expected.server_default.arg) if isinstance(expected.server_default, DefaultClause) else None
            if str(default).strip("'") != str(expected_default).strip("'"):
                raise RuntimeError(f"Legacy default differs: {name}.{expected.name}")
        if inspector.get_pk_constraint(name)["constrained_columns"] != [c.name for c in table.primary_key.columns]:
            raise RuntimeError(f"Legacy primary key differs: {name}")
        checks = {normalized(item["sqltext"]) for item in inspector.get_check_constraints(name)}
        expected_checks = {normalized(item.sqltext) for item in table.constraints if isinstance(item, CheckConstraint)}
        if checks != expected_checks:
            raise RuntimeError(f"Legacy checks differ: {name}")
        uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(name)}
        expected_uniques = {tuple(c.name for c in item.columns) for item in table.constraints if isinstance(item, UniqueConstraint)}
        if uniques != expected_uniques:
            raise RuntimeError(f"Legacy unique constraints differ: {name}")
        foreign = {(tuple(item["constrained_columns"]), item["referred_table"], tuple(item["referred_columns"]),
                    item.get("options", {}).get("ondelete")) for item in inspector.get_foreign_keys(name)}
        expected_foreign = {(tuple(c.parent.name for c in item.elements), item.referred_table.name,
                             tuple(c.column.name for c in item.elements), item.ondelete) for item in table.foreign_key_constraints}
        if foreign != expected_foreign:
            raise RuntimeError(f"Legacy foreign keys differ: {name}")
        indexes = {(item["name"], tuple(item["column_names"]), bool(item["unique"]),
                    normalized(item.get("dialect_options", {}).get("sqlite_where", "")))
                   for item in inspector.get_indexes(name)}
        expected_indexes = {(item.name, tuple(c.name for c in item.columns), item.unique,
                             normalized(item.dialect_options["sqlite"].get("where"))) for item in table.indexes}
        if indexes != expected_indexes:
            raise RuntimeError(f"Legacy indexes differ: {name}")
        ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).scalar_one()
        if bool(table.dialect_options["sqlite"].get("autoincrement")) != ("autoincrement" in ddl.lower()):
            raise RuntimeError(f"Legacy autoincrement differs: {name}")
        if name == "league_groups" and not re.search(r"\bname\s+TEXT\b[^,]*\bCOLLATE\s+NOCASE\b", ddl, re.IGNORECASE):
            raise RuntimeError("Legacy group collation differs")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Legacy foreign key violations; adoption refused.")


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        # SQLite's legacy driver transaction mode does not begin on DDL.
        # Explicitly enclose validation, stamping and upgrade in one real transaction.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config = migration_config(BACKEND / "alembic.ini", BACKEND / "migrations",
                                  database_url=engine.url, connection=connection)
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            validate_legacy_schema(connection)
            command.stamp(config, "0001_baseline")
        command.upgrade(config, "head")
