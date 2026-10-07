from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import URL
from sqlalchemy.pool import StaticPool

from crr_common.database import create_sync_engine


def test_sqlite_connection_can_cross_request_worker_threads(tmp_path):
    engine = create_sync_engine(URL.create("sqlite", database=str(tmp_path / "threads.sqlite")))
    try:
        with engine.connect() as connection, ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(lambda: connection.exec_driver_sql("SELECT 42").scalar_one()).result() == 42
    finally:
        engine.dispose()


def test_caller_pool_options_and_memory_database_are_preserved():
    engine = create_sync_engine("sqlite:///:memory:", poolclass=StaticPool)
    try:
        assert isinstance(engine.pool, StaticPool)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE example(value INTEGER)")
            connection.exec_driver_sql("INSERT INTO example VALUES(7)")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT value FROM example").scalar_one() == 7
    finally:
        engine.dispose()


def test_shared_factory_leaves_sqlite_pragmas_to_the_consumer(tmp_path):
    engine = create_sync_engine(URL.create("sqlite", database=str(tmp_path / "policy.sqlite")))
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "delete"
    finally:
        engine.dispose()


def test_non_sqlite_urls_and_explicit_connection_options(monkeypatch):
    from crr_common import database
    calls = []
    marker = object()
    def factory(url, **options):
        calls.append((url, options))
        return marker
    monkeypatch.setattr(database, "create_engine", factory)
    assert create_sync_engine("postgresql://localhost/example", pool_pre_ping=True) is marker
    assert calls[-1][1] == {"connect_args": {}, "pool_pre_ping": True}
    arguments = {"check_same_thread": True, "timeout": 10}
    assert create_sync_engine("sqlite://", connect_args=arguments) is marker
    assert calls[-1][1]["connect_args"] == arguments
    assert arguments == {"check_same_thread": True, "timeout": 10}
