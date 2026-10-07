import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.database import create_database_engine, run_migrations


def test_fresh_database_schema_defaults_and_pragmas(tmp_path):
    engine = create_database_engine(str(tmp_path / "new.sqlite"))
    try:
        run_migrations(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT name FROM tournament_settings").scalar_one() == "Torneio"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
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
