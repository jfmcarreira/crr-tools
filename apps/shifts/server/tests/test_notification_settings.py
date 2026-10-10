import re
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import select

from app.config import settings
from app.i18n import EVENT_TYPE_LABELS
from app.models import NotificationLog, NotificationSetting, PushSubscription, User
from app.security import hash_password
from app.services.notification_settings import MASTER_SETTING_KEY, notification_enabled
from app.services.notifications import send_email_notification
from app.services.push import send_push_notification
from conftest import sign_in


def master_form(client, email=True, push=True):
    page = client.get("/admin/notifications")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    return {"csrf_token": token, **({"email_enabled": "on"} if email else {}),
            **({"push_enabled": "on"} if push else {})}


def test_defaults_enabled_with_two_checkboxes(logged_in, db):
    page = logged_in.get("/admin/notifications")
    assert page.status_code == 200
    assert "Interruptores gerais de notificações" in page.text
    assert page.text.count('type="checkbox"') == 2
    for channel in ("email", "push"):
        assert re.search(rf'name="{channel}_enabled"[^>]*checked', page.text)
        assert notification_enabled(db, channel)


def test_pause_and_resume_persist_without_changing_users(logged_in, db, admin, monkeypatch):
    admin.notify_email = False
    db.add(PushSubscription(user_id=admin.id, endpoint="https://fcm.googleapis.com/send/test", p256dh="unused", auth="unused"))
    db.commit()
    response = logged_in.post("/admin/notifications/settings", data=master_form(logged_in, email=False))
    assert "Opções de envio de notificações guardadas." in response.text
    assert not notification_enabled(db, "email")
    assert notification_enabled(db, "push")
    page = logged_in.get("/admin/notifications")
    assert not re.search(r'name="email_enabled"[^>]*checked', page.text)
    assert re.search(r'name="push_enabled"[^>]*checked', page.text)
    assert len(list(db.scalars(select(NotificationSetting)))) == 2
    form = master_form(logged_in)
    monkeypatch.setattr(settings, "root_path", "/crr")
    response = logged_in.post("/admin/notifications/settings", data=form, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/crr/admin/notifications"
    assert notification_enabled(db, "email")
    assert notification_enabled(db, "push")
    db.refresh(admin)
    assert not admin.notify_email
    assert db.scalar(select(PushSubscription)).user_id == admin.id


def test_csrf_rejection_does_not_change_switch(logged_in, db):
    assert logged_in.post("/admin/notifications/settings", data={"csrf_token": "wrong"}).status_code == 400
    assert db.scalar(select(NotificationSetting)) is None


def test_admin_only(client, db):
    assert client.get("/admin/notifications").status_code == 401
    assert client.post("/admin/notifications/settings", data={}).status_code == 401
    user = User(name="Operador", username="notification-operator", password_hash=hash_password("secret123"))
    db.add(user)
    db.commit()
    sign_in(client, user.username, "secret123")
    assert client.get("/admin/notifications").status_code == 403
    assert client.post("/admin/notifications/settings", data={}).status_code == 403
    assert db.scalar(select(NotificationSetting)) is None


@pytest.fixture
def delivery(db, admin, team, monkeypatch):
    team.user = admin
    admin.notify_email = True
    db.add(PushSubscription(user_id=admin.id, endpoint="https://fcm.googleapis.com/send/test", p256dh="unused", auth="unused"))
    db.commit()
    for key, value in {
        "smtp_host": "smtp.example.com", "vapid_public_key": "public",
        "vapid_private_key": "private", "vapid_subject": "mailto:admin@example.com",
    }.items():
        monkeypatch.setattr(settings, key, value)
    smtp = MagicMock()
    monkeypatch.setattr("app.services.notifications.smtplib.SMTP", smtp)
    push = Mock()
    monkeypatch.setattr("app.services.push.webpush", push)
    return smtp, push


@pytest.mark.parametrize("event", [*EVENT_TYPE_LABELS, "future_event"])
@pytest.mark.parametrize("email,push_enabled", [(True, True), (True, False), (False, True), (False, False)])
def test_master_gates_every_event_and_channel(db, team, delivery, event, email, push_enabled):
    smtp, push = delivery
    for channel, enabled in (("email", email), ("push", push_enabled)):
        db.add(NotificationSetting(event_type=MASTER_SETTING_KEY[0], channel=channel, enabled=enabled))
    db.commit()
    send_email_notification(db, team, event, "Aviso", "O turno foi alterado.")
    assert smtp.called is email
    assert push.called is push_enabled
    logs = list(db.scalars(select(NotificationLog)))
    assert {log.channel for log in logs} == {"email", "push"}
    for log in logs:
        enabled = email if log.channel == "email" else push_enabled
        assert log.status == ("sent" if enabled else "skipped")


def test_direct_push_honors_master(db, team, delivery):
    _, push = delivery
    db.add(NotificationSetting(event_type=MASTER_SETTING_KEY[0], channel="push", enabled=False))
    db.commit()
    send_push_notification(db, team, "swap_requested", "Pedido de troca", "Novo pedido")
    push.assert_not_called()
    assert db.scalar(select(NotificationLog)).status == "skipped"


def test_enabled_master_still_respects_email_preference(db, admin, team, delivery):
    smtp, push = delivery
    admin.notify_email = False
    db.commit()
    send_email_notification(db, team, "swap_requested", "Aviso", "Novo pedido")
    smtp.assert_not_called()
    push.assert_called_once()


@pytest.mark.parametrize("enabled", [True, False])
def test_legacy_master_inherited_until_channels_saved(logged_in, db, enabled):
    db.add(NotificationSetting(event_type=MASTER_SETTING_KEY[0], channel=MASTER_SETTING_KEY[1], enabled=enabled))
    db.commit()
    for channel in ("email", "push"):
        assert notification_enabled(db, channel) is enabled
    page = logged_in.get("/admin/notifications")
    for channel in ("email", "push"):
        assert bool(re.search(rf'name="{channel}_enabled"[^>]*checked', page.text)) is enabled
    logged_in.post("/admin/notifications/settings", data=master_form(logged_in, email=True, push=False))
    assert notification_enabled(db, "email")
    assert not notification_enabled(db, "push")
    # Preserve the legacy setting, but explicit channel flags now take priority.
    assert db.get(NotificationSetting, MASTER_SETTING_KEY).enabled is enabled


def test_old_per_event_settings_do_not_act_as_master(db, team, delivery):
    smtp, push = delivery
    db.add(NotificationSetting(event_type="swap_requested", channel="email", enabled=False))
    db.commit()
    send_email_notification(db, team, "swap_requested", "Aviso", "Novo pedido")
    smtp.assert_called_once()
    push.assert_called_once()
