import json
from pathlib import Path
import shutil

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.database import create_database_engine, normalized, run_migrations, validate_legacy_schema

FIXTURES = Path(__file__).resolve().parents[4] / "migration/fixtures"


def test_fresh_database_matches_node_schema_and_defaults(tmp_path):
    engine = create_database_engine(str(tmp_path / "new.sqlite"))
    try:
        run_migrations(engine)
        with engine.connect() as connection:
            validate_legacy_schema(connection)
            expected = json.loads((FIXTURES / "tournament-schema.json").read_text())
            for item in expected:
                actual = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name=?", (item["name"],)).scalar_one()
                assert normalized(actual) == normalized(item["sql"]), item["name"]
            assert connection.exec_driver_sql("SELECT name FROM tournament_settings").scalar_one() == "Torneio"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
    finally:
        engine.dispose()


def test_adopts_populated_node_database_without_modifying_rows_or_schema(tmp_path):
    path = tmp_path / "legacy.sqlite"
    shutil.copyfile(FIXTURES / "tournament.sqlite", path)
    engine = create_database_engine(str(path))
    try:
        run_migrations(engine)
        run_migrations(engine)
        with engine.connect() as connection:
            for name, rows in json.loads((FIXTURES / "tournament-rows.json").read_text()).items():
                assert [dict(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY rowid').mappings()] == rows
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0001_baseline"
    finally:
        engine.dispose()


@pytest.mark.parametrize("damage", ["DROP TABLE players", "ALTER TABLE teams ADD COLUMN unexpected TEXT", "DROP INDEX idx_teams_group"])
def test_refuses_incompatible_legacy_database_without_stamping(tmp_path, damage):
    path = tmp_path / "bad.sqlite"
    shutil.copyfile(FIXTURES / "tournament.sqlite", path)
    engine = create_database_engine(str(path))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(damage)
        with pytest.raises(RuntimeError):
            run_migrations(engine)
        assert "alembic_version" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_database_constraints_and_player_cascade(tmp_path):
    engine = create_database_engine(str(tmp_path / "constraints.sqlite"))
    try:
        run_migrations(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO teams(number,name,group_id,created_at,updated_at) VALUES(1,'Equipa',1,'t','t')")
            connection.exec_driver_sql("INSERT INTO players(team_id,name,sort_order) VALUES(1,'Jogador',0)")
            connection.exec_driver_sql("DELETE FROM teams WHERE id=1")
            assert connection.exec_driver_sql("SELECT count(*) FROM players").scalar_one() == 0
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO league_groups(name,sort_order,created_at,updated_at) VALUES('grupo a',1,'t','t')")
    finally:
        engine.dispose()


def test_failed_upgrade_rolls_back_schema_creation(tmp_path, monkeypatch):
    from app import database
    engine = create_database_engine(str(tmp_path / "failed.sqlite"))
    def fail(config, revision):
        config.attributes["connection"].exec_driver_sql("CREATE TABLE incomplete(id INTEGER)")
        raise RuntimeError("migration failed")
    monkeypatch.setattr(database.command, "upgrade", fail)
    try:
        with pytest.raises(RuntimeError, match="migration failed"):
            run_migrations(engine)
        assert not inspect(engine).get_table_names()
    finally:
        engine.dispose()
