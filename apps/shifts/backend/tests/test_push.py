import base64
import re
from unittest.mock import Mock

import pytest
from pywebpush import WebPushException
from sqlalchemy import select

from app.config import settings
from app.models import NotificationLog, PushSubscription
from app.services.notifications import send_email_notification, send_many


def encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


PAYLOAD = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-device",
    "keys": {"p256dh": encoded(b"\x04" + b"a" * 64), "auth": encoded(b"b" * 16)},
}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "vapid_subject", "mailto:admin@example.com")


def csrf(client):
    page = client.get("/calendar")
    return {"X-CSRF-Token": re.search(r'data-csrf="([^"]+)"', page.text).group(1)}


def test_subscription_requires_auth_and_csrf(client, logged_in, configured):
    # logged_in uses the same client; test authentication after clearing its cookie.
    headers = csrf(logged_in)
    assert logged_in.post("/push/subscriptions", json=PAYLOAD).status_code == 400
    assert logged_in.post("/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 200
    client.cookies.clear()
    assert client.post("/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 401


def test_subscribe_idempotent_and_unsubscribe(logged_in, db, admin, configured):
    headers = csrf(logged_in)
    for _ in range(2):
        assert logged_in.post("/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 200
    rows = list(db.scalars(select(PushSubscription)))
    assert len(rows) == 1
    assert rows[0].user_id == admin.id
    assert logged_in.request("DELETE", "/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 200
    assert db.scalar(select(PushSubscription)) is None


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/send/x", "https://localhost/send/x", "https://127.0.0.1/x",
    "https://fcm.googleapis.com.evil.test/x", "https://fcm.googleapis.com:8443/x",
    "https://user:password@fcm.googleapis.com/x",
])
def test_rejects_unsafe_endpoint(logged_in, configured, endpoint):
    headers = csrf(logged_in)
    assert logged_in.post("/push/subscriptions", json={**PAYLOAD, "endpoint": endpoint}, headers=headers).status_code == 422


def test_rejects_invalid_keys(logged_in, configured):
    assert logged_in.post("/push/subscriptions", json={**PAYLOAD, "keys": {"p256dh": "bad", "auth": "!"}}, headers=csrf(logged_in)).status_code == 422


def test_unconfigured(logged_in):
    assert logged_in.post("/push/subscriptions", json=PAYLOAD, headers=csrf(logged_in)).status_code == 503


def test_other_account_cannot_claim_or_remove_subscription(logged_in, db, team, configured):
    from app.models import User
    other = User(name="Outra conta", username="other", password_hash="unused")
    db.add(other)
    db.flush()
    db.add(PushSubscription(user_id=other.id, endpoint=PAYLOAD["endpoint"], **PAYLOAD["keys"]))
    db.commit()
    headers = csrf(logged_in)
    assert logged_in.post("/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 409
    assert logged_in.request("DELETE", "/push/subscriptions", json=PAYLOAD, headers=headers).status_code == 200
    assert db.scalar(select(PushSubscription)).user_id == other.id


def subscribe_device(db, admin, team, suffix=""):
    team.user = admin
    db.add(PushSubscription(user_id=admin.id, endpoint=PAYLOAD["endpoint"] + suffix, **PAYLOAD["keys"]))
    db.commit()


def test_push_independent_of_email_and_deduplicated(db, admin, team, configured, monkeypatch):
    subscribe_device(db, admin, team)
    subscribe_device(db, admin, team, "-second")
    admin.notify_email = False
    db.commit()
    send = Mock()
    monkeypatch.setattr("app.services.push.webpush", send)
    send_many(db, [team, team], "shift_changed", "Turno alterado", "O teu turno mudou.")
    assert send.call_count == 2
    assert send.call_args.kwargs["timeout"] == 10
    logs = list(db.scalars(select(NotificationLog).where(NotificationLog.channel == "push")))
    assert len(logs) == 2
    assert all(log.status == "sent" for log in logs)


@pytest.mark.parametrize("status,remaining", [(410, 0), (404, 0), (503, 1)])
def test_provider_failure_isolated_and_expired_removed(db, admin, team, configured, monkeypatch, status, remaining):
    subscribe_device(db, admin, team)
    send = Mock(side_effect=WebPushException("sensitive provider details", response=Mock(status_code=status)))
    monkeypatch.setattr("app.services.push.webpush", send)
    send_email_notification(db, team, "shift_changed", "Turno", "Alterado")
    assert len(list(db.scalars(select(PushSubscription)))) == remaining
    log = db.scalar(select(NotificationLog).where(NotificationLog.channel == "push"))
    assert log.status == "failed"
    assert "sensitive" not in log.error
    assert db.scalar(select(NotificationLog).where(NotificationLog.channel == "email")) is not None


def test_inactive_user_not_notified(db, admin, team, configured, monkeypatch):
    subscribe_device(db, admin, team)
    admin.is_active = False
    db.commit()
    send = Mock()
    monkeypatch.setattr("app.services.push.webpush", send)
    send_email_notification(db, team, "shift_changed", "Turno", "Alterado")
    send.assert_not_called()


def test_calendar_and_worker_respect_prefix(logged_in, monkeypatch):
    monkeypatch.setattr(settings, "root_path", "/crr")
    page = logged_in.get("/calendar")
    assert 'id="enable-push"' in page.text
    assert 'data-endpoint="/crr/push/subscriptions"' in page.text
    assert 'data-worker="/crr/sw.js"' in page.text
    assert "scope: '/crr/'" in page.text
    worker = logged_in.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["cache-control"] == "no-cache"
    assert "notificationclick" in worker.text
