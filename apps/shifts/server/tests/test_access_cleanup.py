import asyncio
import logging
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock

from app.config import settings
from app.models import AccessPin
from app.services import access_cleanup

# Save the real function before the autouse fixture isolates the worker clock.
clear_expired_pins = access_cleanup._clear_expired_pins


def test_cleanup_erases_only_expired_digits_without_ttlock(db, admin, monkeypatch):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expired = AccessPin(user_id=admin.id, request_key="expired-cleanup", status="active",
                        encrypted_pin="expired-encrypted-digits", valid_from_utc=now - timedelta(minutes=16),
                        valid_until_utc=now - timedelta(minutes=1))
    valid = AccessPin(user_id=admin.id, request_key="valid-cleanup", status="active",
                      encrypted_pin="valid-encrypted-digits", valid_from_utc=now,
                      valid_until_utc=now + timedelta(minutes=15))
    db.add_all([expired, valid])
    db.commit()
    monkeypatch.setattr(settings, "ttlock_enabled", False)
    remote = Mock(side_effect=AssertionError("Cleanup must not call TTLock"))
    from app.services.door_access import ttlock_client
    monkeypatch.setattr(ttlock_client, "list_passcodes", remote)
    monkeypatch.setattr(ttlock_client, "generate_timed_pin", remote)
    clear_expired_pins()
    db.refresh(expired)
    db.refresh(valid)
    assert expired.encrypted_pin is None
    assert expired.status == "expired"
    assert valid.encrypted_pin == "valid-encrypted-digits"
    assert valid.status == "active"
    remote.assert_not_called()


def test_worker_retries_failures_and_stops_cleanly(monkeypatch, caplog):
    calls = []
    async def exercise():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        def cleanup():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("sensitive SQL parameters")
            loop.call_soon_threadsafe(stop.set)
        monkeypatch.setattr(access_cleanup, "_clear_expired_pins", cleanup)
        await asyncio.wait_for(access_cleanup.run_pin_cleanup(stop, interval=0.001), timeout=5)
    with caplog.at_level(logging.ERROR):
        asyncio.run(exercise())
    assert len(calls) == 2
    assert "retrying" in caplog.text
    assert "sensitive SQL parameters" not in caplog.text


def test_lifespan_starts_worker_even_when_ttlock_disabled(db, monkeypatch):
    # A separate lifespan allows us to install the probe before worker startup.
    from fastapi.testclient import TestClient
    from app.main import app
    started = Event()
    monkeypatch.setattr(settings, "ttlock_enabled", False)
    monkeypatch.setattr(access_cleanup, "_clear_expired_pins", started.set)
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200
        assert started.wait(timeout=5)
