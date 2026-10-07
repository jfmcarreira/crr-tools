"""Migrations run in-process at startup, so they must not silence the server's loggers."""

import logging

from app.database import run_migrations


def test_run_migrations_keeps_server_loggers_enabled() -> None:
    run_migrations()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        assert logger.disabled is False, f"{name} was disabled by the migration logging config"
