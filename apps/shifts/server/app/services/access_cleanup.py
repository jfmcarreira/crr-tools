"""Local expired-digit cleanup, independent of TTLock availability or feature flags."""

import asyncio
import logging
from datetime import datetime, timezone

from ..database import SessionLocal
from .door_access import expire_pins

logger = logging.getLogger(__name__)


def _clear_expired_pins() -> None:
    with SessionLocal() as db:
        expire_pins(db, datetime.now(timezone.utc))


async def run_pin_cleanup(stop: asyncio.Event, interval: float = 60) -> None:
    while not stop.is_set():
        try:
            # Each run owns its session; never share a request session with a worker.
            await asyncio.to_thread(_clear_expired_pins)
        except Exception:
            # Keep serving and retry next minute. Exception bodies can contain SQL
            # parameters, so never include them in these logs.
            logger.error("Expired access PIN cleanup failed; retrying next interval.")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
