from collections.abc import Mapping
from typing import Any

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine, make_url


def create_sync_engine(
    url: str | URL,
    *,
    connect_args: Mapping[str, Any] | None = None,
    **engine_options: Any,
) -> Engine:
    """Construct a synchronous engine without changing connection/schema policy."""
    arguments = dict(connect_args or {})
    if make_url(url).get_backend_name() == "sqlite":
        arguments.setdefault("check_same_thread", False)
    return create_engine(url, connect_args=arguments, **engine_options)
