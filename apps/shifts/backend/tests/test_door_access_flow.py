import re
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import Mock

import pytest
import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.models import AccessPin, Assignment, Schedule, Team, User
from app.services import door_access
from app.services.door_access import DoorAccessError, as_utc, issue_pin, visible_pin
from app.services.ttlock import TTLockError

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)  # 13:00 Lisbon, at shift start


def generated_result(now=NOW, **overrides):
    start = now.replace(minute=0, second=0, microsecond=0)
    return {"keyboardPwdId": 42, "keyboardPwd": "012345678", "lockId": "123",
            "startDate": int(start.timestamp() * 1000),
            "endDate": int((start + timedelta(hours=2)).timestamp() * 1000), **overrides}


@pytest.fixture
def configured(monkeypatch):
    for name, value in {
        "ttlock_enabled": True, "ttlock_lock_id": "123", "ttlock_client_id": "client",
        "ttlock_client_secret": "secret", "ttlock_username": "owner", "ttlock_password": "password",
        "ttlock_eligible_schedule_slugs": "test-access",
        "ttlock_encryption_key": Fernet.generate_key().decode(),
    }.items():
        monkeypatch.setattr(settings, name, value)
    create = Mock(return_value=generated_result())
    monkeypatch.setattr(door_access, "issue_pin_via_ttlock", create)
    return create


@pytest.fixture
def assignment(db, admin):
    admin.can_request_pin = True
    team = Team(name="Access team", user=admin, is_active=True)
    schedule = Schedule(name="Access", slug="test-access", schedule_type="fixed", weekdays="5",
                        start_time=time(13), end_time=time(16), is_active=True)
    row = Assignment(date=date(2026, 10, 10), schedule=schedule, team=team, source="manual")
    db.add_all([team, schedule, row])
    db.commit()
    return row


def test_issue_once_encrypted_and_view_survives_permission_and_assignment_change(db, admin, assignment, configured):
    pin = issue_pin(db, admin, assignment.id, NOW)
    digits = visible_pin(db, admin, pin.id, NOW)
    assert digits == "012345678"
    assert pin.encrypted_pin != digits
    assert as_utc(pin.valid_from_utc) == NOW.replace(minute=0)
    assert as_utc(pin.valid_until_utc) == NOW.replace(minute=0) + timedelta(hours=2)
    assert issue_pin(db, admin, assignment.id, NOW).id == pin.id
    configured.assert_called_once()
    admin.can_request_pin = False
    assignment.team_id = None
    db.commit()
    assert visible_pin(db, admin, pin.id, NOW) == digits
    with pytest.raises(DoorAccessError) as failure:
        issue_pin(db, admin, assignment.id, NOW)
    assert failure.value.status_code == 403
    configured.assert_called_once()


@pytest.mark.parametrize("change", ["permission", "inactive", "unowned", "team_inactive", "schedule_inactive", "slug", "weekday", "disabled"])
def test_denial_never_calls_api_or_inserts(db, admin, assignment, configured, monkeypatch, change):
    if change == "permission":
        admin.can_request_pin = False
    elif change == "inactive":
        admin.is_active = False
    elif change == "unowned":
        assignment.team.user_id = None
    elif change == "team_inactive":
        assignment.team.is_active = False
    elif change == "schedule_inactive":
        assignment.schedule.is_active = False
    elif change == "slug":
        monkeypatch.setattr(settings, "ttlock_eligible_schedule_slugs", "other")
    elif change == "weekday":
        assignment.schedule.weekdays = "0"
    else:
        monkeypatch.setattr(settings, "ttlock_enabled", False)
    db.commit()
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    assert db.scalar(select(AccessPin)) is None
    configured.assert_not_called()


@pytest.mark.parametrize("offset", [timedelta(hours=-6), timedelta(hours=6)], ids=["before-shift", "after-shift"])
def test_outside_request_window_never_calls_api_or_inserts(db, admin, assignment, configured, offset):
    with pytest.raises(DoorAccessError) as failure:
        issue_pin(db, admin, assignment.id, NOW + offset)
    assert failure.value.status_code == 403
    assert db.scalar(select(AccessPin)) is None
    configured.assert_not_called()


def test_expired_pin_cannot_be_replaced(db, admin, assignment, configured):
    pin = issue_pin(db, admin, assignment.id, NOW)
    expired_at = as_utc(pin.valid_until_utc) + timedelta(hours=1)
    # Even an administrator moving this assignment into a new eligible window
    # must not allow a replacement for the expired reservation.
    assignment.schedule.start_time = time(16)
    assignment.schedule.end_time = time(17)
    db.commit()
    with pytest.raises(DoorAccessError, match="expirou"):
        issue_pin(db, admin, assignment.id, expired_at)
    door_access.expire_pins(db, expired_at)
    assert db.get(AccessPin, pin.id).encrypted_pin is None
    with pytest.raises(DoorAccessError):
        visible_pin(db, admin, pin.id, expired_at)
    configured.assert_called_once()


def test_pin_not_shortened_at_shift_end(db, admin, assignment, configured):
    assignment.schedule.end_time = time(13, 40)
    db.commit()
    pin = issue_pin(db, admin, assignment.id, NOW)
    assert as_utc(pin.valid_until_utc) == NOW.replace(minute=0) + timedelta(hours=2)


@pytest.mark.parametrize("uncertain", [True, False])
def test_failed_creation_never_retried_or_exposed(db, admin, assignment, configured, uncertain):
    configured.side_effect = TTLockError("test_failure", uncertain=uncertain)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    pin = db.scalar(select(AccessPin))
    assert pin.status == ("uncertain" if uncertain else "failed")
    assert pin.encrypted_pin is None
    with pytest.raises(DoorAccessError):
        visible_pin(db, admin, pin.id, NOW)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    configured.assert_called_once()


def test_reconciliation_recovers_generated_digits_with_exact_metadata(db, admin, assignment, configured, monkeypatch):
    configured.side_effect = TTLockError("timeout", uncertain=True)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    pin = db.scalar(select(AccessPin))
    assert pin.encrypted_pin is None
    digits = "012345678"
    record = {"lockId": 123, "keyboardPwdName": door_access.passcode_name(pin.request_key), "keyboardPwd": digits,
              "keyboardPwdType": 3, "keyboardPwdId": 42, "startDate": generated_result()["startDate"],
              "endDate": generated_result()["endDate"]}
    listing = Mock(return_value=[{**record, "endDate": record["endDate"] + 1000}])
    monkeypatch.setattr(door_access.ttlock_client, "list_passcodes", listing)
    assert not door_access.reconcile_pin(db, pin.id, NOW)
    listing.return_value = [record]
    assert door_access.reconcile_pin(db, pin.id, NOW)
    assert visible_pin(db, admin, pin.id, NOW) == digits
    configured.assert_called_once()


def test_other_users_and_pending_cannot_view(db, admin, assignment, configured):
    pin = issue_pin(db, admin, assignment.id, NOW)
    other = User(name="Other", username="other-access", password_hash="hash", is_active=True)
    db.add(other)
    db.commit()
    with pytest.raises(DoorAccessError):
        visible_pin(db, other, pin.id, NOW)
    pin.status = "pending"
    db.commit()
    with pytest.raises(DoorAccessError):
        visible_pin(db, admin, pin.id, NOW)


def test_http_auth_csrf_and_disabled_permission(logged_in, db, admin, assignment, configured):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', logged_in.get("/").text).group(1)
    assert logged_in.post("/access/pins", data={"assignment_id": assignment.id, "csrf_token": "bad"}).status_code == 400
    admin.can_request_pin = False
    db.commit()
    assert logged_in.post("/access/pins", data={"assignment_id": assignment.id, "csrf_token": csrf}).status_code == 403
    configured.assert_not_called()
    assert logged_in.get("/admin/access").headers["cache-control"] == "no-store"


def test_concurrent_reservation_calls_cloud_once(db, admin, assignment, configured):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.database import SessionLocal

    entered, release = Event(), Event()
    user_id, assignment_id = admin.id, assignment.id
    def create(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return generated_result()
    configured.side_effect = create
    def first():
        with SessionLocal() as session:
            return issue_pin(session, session.get(User, user_id), assignment_id, NOW).id
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert entered.wait(timeout=10)
            with pytest.raises(DoorAccessError):
                issue_pin(db, admin, assignment_id, NOW)
        finally:
            release.set()
        pin_id = future.result(timeout=10)
    assert issue_pin(db, admin, assignment_id, NOW).id == pin_id
    configured.assert_called_once()


def test_inflight_permission_change_does_not_revoke(db, admin, assignment, configured):
    def create(**kwargs):
        admin.can_request_pin = False
        db.commit()
        return generated_result()
    configured.side_effect = create
    pin = issue_pin(db, admin, assignment.id, NOW)
    assert visible_pin(db, admin, pin.id, NOW)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    configured.assert_called_once()


def test_http_issue_view_dashboard_and_root_path(logged_in, db, admin, assignment, configured, monkeypatch):
    from app.routers import access, dashboard
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(access, "datetime", Clock)
    monkeypatch.setattr(dashboard, "datetime", Clock)
    monkeypatch.setattr(settings, "root_path", "/shifts")
    page = logged_in.get("/")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    response = logged_in.post("/access/pins", data={"assignment_id": assignment.id, "csrf_token": csrf}, follow_redirects=False)
    pin = db.scalar(select(AccessPin))
    assert response.status_code == 303
    assert response.headers["location"] == f"/shifts/access/pins/{pin.id}"
    assert response.headers["cache-control"] == "no-store"
    digits = visible_pin(db, admin, pin.id, NOW)
    view = logged_in.get(f"/access/pins/{pin.id}")
    assert digits in view.text
    assert view.headers["cache-control"] == "no-store"
    assert view.headers["referrer-policy"] == "no-referrer"
    admin.can_request_pin = False
    assignment.team_id = None
    db.commit()
    monkeypatch.setattr(settings, "ttlock_enabled", False)
    assert digits not in logged_in.get("/admin/access").text
    assert digits in logged_in.get(f"/access/pins/{pin.id}").text


def test_anonymous_access_denied(client, configured):
    assert client.post("/access/pins", data={"assignment_id": 1, "csrf_token": "x"}).status_code == 401
    assert client.get("/access/pins/1").status_code == 401
    assert client.get("/admin/access").status_code == 401
    configured.assert_not_called()


def test_missing_configuration_reserves_nothing(db, admin, assignment, configured, monkeypatch):
    monkeypatch.setattr(settings, "ttlock_password", "")
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    assert db.scalar(select(AccessPin)) is None
    configured.assert_not_called()


def test_email_uniqueness_preserved_after_ttlock_migrations(db, admin):
    from sqlalchemy.exc import IntegrityError
    db.add(User(name="Duplicate", username="duplicate-email", password_hash="hash", email=admin.email))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_real_adapter_generates_after_digit_free_reservation(db, admin, assignment, configured, monkeypatch):
    from app.services import ttlock as adapter
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr("ttlock.client.datetime", Clock)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "private-token", "expires_in": 3600})
        assert request.url.path == "/v3/keyboardPwd/get"
        assert request.url.params["lockId"] == "123"
        assert request.url.params["keyboardPwdType"] == "3"
        assert "addType" not in request.url.params
        assert "keyboardPwd" not in request.url.params
        pending = db.scalar(select(AccessPin))
        assert pending.status == "pending"
        assert pending.encrypted_pin is None
        assert request.url.params["keyboardPwdName"] == door_access.passcode_name(pending.request_key)
        return httpx.Response(200, json={"keyboardPwdId": 42, "keyboardPwd": "012345678"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = adapter.TTLockClient(client=http)
        monkeypatch.setattr(adapter, "ttlock_client", api)
        monkeypatch.setattr(door_access, "ttlock_client", api)
        monkeypatch.setattr(door_access, "issue_pin_via_ttlock", adapter.issue_pin_via_ttlock)
        pin = issue_pin(db, admin, assignment.id, NOW)
    assert visible_pin(db, admin, pin.id, NOW) == "012345678"
    assert pin.encrypted_pin != "012345678"
    assert as_utc(pin.valid_until_utc) == NOW.replace(minute=0) + timedelta(hours=2)
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get"]


def test_pin_uses_provider_generation_window(db, admin, assignment, configured):
    configured.return_value = generated_result(NOW + timedelta(hours=1))
    pin = issue_pin(db, admin, assignment.id, NOW)
    assert as_utc(pin.valid_from_utc) == NOW.replace(minute=0) + timedelta(hours=1)
    assert as_utc(pin.valid_until_utc) == NOW.replace(minute=0) + timedelta(hours=3)
    assert visible_pin(db, admin, pin.id, NOW.replace(minute=0) + timedelta(hours=1)) == "012345678"


def test_uncertain_generation_keeps_actual_window_for_reconciliation(db, admin, assignment, configured, monkeypatch):
    result = generated_result(NOW + timedelta(hours=1))
    error = TTLockError("invalid_response", uncertain=True)
    error.start_date, error.end_date = result["startDate"], result["endDate"]
    configured.side_effect = error
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    pin = db.scalar(select(AccessPin))
    assert as_utc(pin.valid_until_utc) == NOW.replace(minute=0) + timedelta(hours=3)
    assert pin.encrypted_pin is None
    record = {**result, "keyboardPwdName": door_access.passcode_name(pin.request_key), "keyboardPwdType": 3}
    monkeypatch.setattr(door_access.ttlock_client, "list_passcodes", Mock(return_value=[record]))
    now = NOW.replace(minute=0) + timedelta(hours=1)
    assert door_access.reconcile_pin(db, pin.id, now)
    assert visible_pin(db, admin, pin.id, now) == "012345678"


@pytest.mark.parametrize("change", [{"keyboardPwd": "private-secret"}, {"keyboardPwd": None},
    {"keyboardPwdId": 0}, {"lockId": "456"}, {"endDate": "private-secret"},
    {"endDate": int((NOW + timedelta(minutes=15)).timestamp() * 1000)}])
def test_invalid_generation_metadata_is_uncertain_and_not_exposed(db, admin, assignment, configured, change):
    configured.return_value = generated_result(**change)
    with pytest.raises(DoorAccessError) as error:
        issue_pin(db, admin, assignment.id, NOW)
    assert "private-secret" not in str(error.value)
    pin = db.scalar(select(AccessPin))
    assert pin.status == "uncertain"
    assert pin.error_code == "invalid_generated_passcode_response"
    assert pin.encrypted_pin is None
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    configured.assert_called_once()


@pytest.mark.parametrize("change", [{"lockId": 456}, {"keyboardPwdName": "wrong-name"},
    {"keyboardPwdType": 1}, {"startDate": generated_result()["startDate"] + 1000},
    {"endDate": generated_result()["endDate"] + 1000}, {"keyboardPwdId": 0}, {"keyboardPwd": "bad-code"}])
def test_reconciliation_rejects_wrong_generated_record(db, admin, assignment, configured, monkeypatch, change):
    configured.side_effect = TTLockError("timeout", uncertain=True)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    pin = db.scalar(select(AccessPin))
    record = {**generated_result(), "keyboardPwdName": door_access.passcode_name(pin.request_key), "keyboardPwdType": 3, **change}
    monkeypatch.setattr(door_access.ttlock_client, "list_passcodes", Mock(return_value=[record]))
    assert not door_access.reconcile_pin(db, pin.id, NOW)
    assert pin.status == "uncertain"
    assert pin.encrypted_pin is None


def test_reconciliation_rejects_ambiguous_generated_records(db, admin, assignment, configured, monkeypatch):
    configured.side_effect = TTLockError("timeout", uncertain=True)
    with pytest.raises(DoorAccessError):
        issue_pin(db, admin, assignment.id, NOW)
    pin = db.scalar(select(AccessPin))
    record = {**generated_result(), "keyboardPwdName": door_access.passcode_name(pin.request_key), "keyboardPwdType": 3}
    monkeypatch.setattr(door_access.ttlock_client, "list_passcodes", Mock(return_value=[record, {**record, "keyboardPwdId": 43}]))
    assert not door_access.reconcile_pin(db, pin.id, NOW)
    assert pin.status == "uncertain"


def test_legacy_custom_reservation_still_requires_exact_digits(db, admin, assignment, configured, monkeypatch):
    key = door_access.request_key(admin.id, assignment.id, "123")
    pin = AccessPin(user_id=admin.id, assignment_id=assignment.id, request_key=key, lock_id="123",
                    status="uncertain", encrypted_pin=Fernet(settings.ttlock_encryption_key.encode()).encrypt(b"123456").decode(),
                    valid_from_utc=NOW.replace(tzinfo=None), valid_until_utc=(NOW + timedelta(minutes=15)).replace(tzinfo=None))
    db.add(pin)
    db.commit()
    record = {"lockId": "123", "keyboardPwdName": door_access.passcode_name(key), "keyboardPwdType": 3,
              "keyboardPwdId": 42, "keyboardPwd": "654321", "startDate": int(NOW.timestamp() * 1000),
              "endDate": int((NOW + timedelta(minutes=15)).timestamp() * 1000)}
    listing = Mock(return_value=[record])
    monkeypatch.setattr(door_access.ttlock_client, "list_passcodes", listing)
    assert not door_access.reconcile_pin(db, pin.id, NOW)
    listing.return_value = [{**record, "keyboardPwd": "123456"}]
    assert door_access.reconcile_pin(db, pin.id, NOW)
    assert visible_pin(db, admin, pin.id, NOW) == "123456"
    assert as_utc(pin.valid_until_utc) == NOW + timedelta(minutes=15)
    configured.assert_not_called()
