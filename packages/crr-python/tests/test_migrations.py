from sqlalchemy import URL

from crr_common.database import create_sync_engine
from crr_common.migrations import migration_config


def ini(tmp_path):
    path = tmp_path / "alembic.ini"
    path.write_text("[alembic]\nscript_location = %(here)s/migrations\n")
    return path


def test_configuration_resolves_paths_and_preserves_url_percent_escapes(tmp_path):
    scripts = tmp_path / "migration%files"
    url = "postgresql://reader:p%25ss@localhost/database"
    config = migration_config(ini(tmp_path), scripts, database_url=url)
    assert config.config_file_name == str(tmp_path / "alembic.ini")
    assert config.get_main_option("script_location") == str(scripts)
    assert config.get_main_option("sqlalchemy.url") == url
    assert "connection" not in config.attributes


def test_sqlalchemy_url_objects_are_rendered_without_redacting_connection_credentials(tmp_path):
    url = URL.create("postgresql", username="test-user", password="test%only", host="localhost", database="example")
    config = migration_config(ini(tmp_path), tmp_path / "migrations", database_url=url)
    assert config.get_main_option("sqlalchemy.url") == url.render_as_string(hide_password=False)


def test_configuration_reuses_caller_connection_without_opening_or_committing_it(tmp_path):
    engine = create_sync_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            config = migration_config(ini(tmp_path), tmp_path / "migrations", connection=connection)
            assert config.attributes["connection"] is connection
            assert connection.in_transaction()
            assert not connection.closed
            assert config.get_main_option("sqlalchemy.url") is None
            transaction.rollback()
    finally:
        engine.dispose()
