from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import AccessPin, Assignment, Schedule, Team, User
from ..config import settings
from .ttlock import TTLockError, issue_pin_via_ttlock, ttlock_client

LISBON_TZ = ZoneInfo("Europe/Lisbon")


def _shift_interval_utc(assignment: Assignment) -> tuple[datetime, datetime] | None:
    """Return (shift_start_utc, request_window_end_utc) for the assignment's local shift."""
    if assignment.schedule is None:
        return None
    schedule = assignment.schedule
    start_local = datetime.combine(assignment.date, schedule.start_time, tzinfo=LISBON_TZ)
    end_local = datetime.combine(assignment.date, schedule.end_time, tzinfo=LISBON_TZ)
    if schedule.end_time <= schedule.start_time:
        end_local += timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc) - timedelta(minutes=30)
    end_utc = end_local.astimezone(timezone.utc)
    window_end_utc = min(start_utc + timedelta(minutes=60), end_utc)
    return start_utc, window_end_utc


def can_request_pin(db: Session, current_user: User | None, assignment_id: int, now_utc: datetime) -> bool:
    """True when the request is allowed to issue a new timed TTLock PIN."""
    if current_user is None:
        return False
    now_utc = as_utc(now_utc)
    user = db.get(User, current_user.id, populate_existing=True)
    if user is None or not user.is_active or not user.can_request_pin:
        return False

    assignment = db.get(Assignment, assignment_id, populate_existing=True)
    if assignment is None or assignment.team_id is None:
        return False

    team = db.get(Team, assignment.team_id, populate_existing=True)
    if team is None or not team.is_active or team.user_id != user.id:
        return False

    schedule = db.get(Schedule, assignment.schedule_id, populate_existing=True)
    if schedule is None or not schedule.is_active:
        return False
    assignment.schedule = schedule
    if schedule.slug not in settings.ttlock_eligible_schedule_ids:
        return False

    if assignment.date.weekday() not in {int(value) for value in schedule.weekdays.split(",") if value.strip()}:
        return False

    shift_window = _shift_interval_utc(assignment)
    if shift_window is None:
        return False

    start_utc, window_end_utc = shift_window
    if not (start_utc <= now_utc < window_end_utc):
        return False

    return True


def can_view_pin(db: Session, current_user: User | None, pin_id: int, now_utc: datetime) -> bool:
    """Only the owning user can see a still-valid PIN."""
    if current_user is None:
        return False
    user = db.get(User, current_user.id, populate_existing=True)
    if user is None or not user.is_active:
        return False

    now_utc = as_utc(now_utc)
    pin = db.get(AccessPin, pin_id, populate_existing=True)
    if pin is None or pin.user_id != user.id:
        return False

    if pin.status != "active":
        return False
    if now_utc < as_utc(pin.valid_from_utc) or now_utc >= as_utc(pin.valid_until_utc):
        return False

    return True


class DoorAccessError(RuntimeError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def as_utc(value: datetime) -> datetime:
    # SQLite DateTime is deliberately stored as naive UTC throughout this ledger.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _cipher() -> Fernet:
    try:
        if settings.ttlock_encryption_key == settings.secret_key:
            raise ValueError
        return Fernet(settings.ttlock_encryption_key.encode())
    except (ValueError, TypeError):
        raise DoorAccessError("O acesso à porta não está configurado.", 503) from None


def request_key(user_id: int, assignment_id: int, lock_id: str) -> str:
    return hashlib.sha256(f"{lock_id}:{assignment_id}:{user_id}".encode()).hexdigest()


def passcode_name(key: str) -> str:
    return f"CRR-{key[:32]}"


def _generation_window(result: dict, now: datetime) -> tuple[datetime, datetime]:
    try:
        start = datetime.fromtimestamp(int(result["startDate"]) / 1000, timezone.utc)
        end = datetime.fromtimestamp(int(result["endDate"]) / 1000, timezone.utc)
        expected_start = now.replace(minute=0, second=0, microsecond=0)
        if (start not in (expected_start, expected_start + timedelta(hours=1))
                or end != start + timedelta(hours=2)):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise TTLockError("invalid_generated_passcode_response", uncertain=True) from None
    return start, end


def _generated_details(result: dict, lock_id: str, now: datetime) -> tuple[str, str, datetime, datetime]:
    """Validate generation metadata without leaking provider data in errors."""
    start, end = _generation_window(result, now)
    try:
        digits = result["keyboardPwd"]
        code_id = str(result["keyboardPwdId"])
        if (str(result["lockId"]) != lock_id or not isinstance(digits, str)
                or not digits.isascii() or not digits.isdigit()
                or not code_id.isascii() or not code_id.isdigit() or int(code_id) <= 0):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise TTLockError("invalid_generated_passcode_response", uncertain=True) from None
    return digits, code_id, start, end


def expire_pins(db: Session, now: datetime) -> None:
    db.execute(update(AccessPin).where(
        AccessPin.valid_until_utc <= as_utc(now).replace(tzinfo=None),
        AccessPin.status != "expired",
    ).values(
        encrypted_pin=None, status="expired",
    ))
    db.commit()


def _existing(pin: AccessPin, now: datetime) -> AccessPin:
    if pin.status == "active" and as_utc(pin.valid_until_utc) > now:
        return pin
    if as_utc(pin.valid_until_utc) <= now:
        raise DoorAccessError("O código expirou.")
    raise DoorAccessError("Não é possível emitir outro código para este turno. Contacte um administrador.")


def issue_pin(db: Session, user: User, assignment_id: int, now: datetime) -> AccessPin:
    now = as_utc(now)
    # Authorization is mandatory in the service, including for non-HTTP callers.
    if not can_request_pin(db, user, assignment_id, now):
        raise DoorAccessError("Não tem permissão para pedir um código neste turno.", 403)
    if not settings.ttlock_enabled or not settings.ttlock_lock_id:
        raise DoorAccessError("O acesso à porta está indisponível.", 503)
    try:
        # Validate credentials, HTTPS origin and the bound lock before reserving.
        ttlock_client.lock_id
    except TTLockError:
        raise DoorAccessError("O acesso à porta não está configurado.", 503) from None
    cipher = _cipher()
    key = request_key(user.id, assignment_id, settings.ttlock_lock_id)
    existing = db.scalar(select(AccessPin).where(AccessPin.request_key == key))
    if existing:
        return _existing(existing, now)
    assignment = db.get(Assignment, assignment_id)
    start = now.replace(minute=0, second=0, microsecond=0)
    pin = AccessPin(
        user_id=user.id, team_id=assignment.team_id, assignment_id=assignment_id,
        lock_id=settings.ttlock_lock_id, request_key=key, status="pending",
        # TTLock chooses the digits; no code exists locally until confirmed.
        encrypted_pin=None,
        valid_from_utc=start.replace(tzinfo=None),
        valid_until_utc=(start + timedelta(hours=2)).replace(tzinfo=None),
    )
    db.add(pin)
    try:
        # Unique reservation is committed BEFORE contacting TTLock.
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AccessPin).where(AccessPin.request_key == key))
        if existing is None:
            raise DoorAccessError("Não foi possível reservar o código.", 503) from None
        return _existing(existing, now)
    try:
        result = issue_pin_via_ttlock(
            lock_id=pin.lock_id, name=passcode_name(key),
        )
        digits, code_id, actual_start, actual_end = _generated_details(result, pin.lock_id, now)
    except TTLockError as exc:
        pin.status = "uncertain" if exc.uncertain else "failed"
        pin.error_code = exc.code
        if exc.uncertain and exc.start_date is not None and exc.end_date is not None:
            try:
                actual_start, actual_end = _generation_window(
                    {"startDate": exc.start_date, "endDate": exc.end_date}, now,
                )
            except TTLockError:
                pass
            else:
                pin.valid_from_utc = actual_start.replace(tzinfo=None)
                pin.valid_until_utc = actual_end.replace(tzinfo=None)
        db.commit()
        raise DoorAccessError("Não foi possível confirmar o código. Contacte um administrador.", 503) from None
    pin.keyboard_pwd_id = code_id
    pin.encrypted_pin = cipher.encrypt(digits.encode()).decode()
    # Use the actual requested window returned by the module, even across an hour boundary.
    pin.valid_from_utc = actual_start.replace(tzinfo=None)
    pin.valid_until_utc = actual_end.replace(tzinfo=None)
    pin.status = "active"
    db.commit()
    return pin


def visible_pin(db: Session, user: User, pin_id: int, now: datetime) -> str:
    if not can_view_pin(db, user, pin_id, now):
        raise DoorAccessError("O código não está disponível ou expirou.", 404)
    pin = db.get(AccessPin, pin_id)
    try:
        return _cipher().decrypt(pin.encrypted_pin.encode()).decode()
    except (InvalidToken, AttributeError, UnicodeError):
        raise DoorAccessError("O código não está disponível.", 503) from None


def reconcile_pin(db: Session, pin_id: int, now: datetime) -> bool:
    """Confirm one exact reserved code against the cloud; never generate or delete."""
    now = as_utc(now)
    pin = db.get(AccessPin, pin_id, populate_existing=True)
    if pin is None or pin.status not in {"pending", "uncertain"} or as_utc(pin.valid_until_utc) <= now:
        raise DoorAccessError("Não existe um código pendente válido.")
    try:
        cipher = _cipher()
        # Existing custom-PIN reservations retain their exact-digit check.
        digits = cipher.decrypt(pin.encrypted_pin.encode()).decode() if pin.encrypted_pin else None
        records = ttlock_client.list_passcodes(pin.lock_id)
    except (TTLockError, InvalidToken, AttributeError, UnicodeError):
        raise DoorAccessError("Não foi possível consultar os códigos da fechadura.", 503) from None
    matches = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if (str(record.get("lockId")) == pin.lock_id
                and record.get("keyboardPwdName") == passcode_name(pin.request_key)
                and isinstance(record.get("keyboardPwd"), str)
                and record["keyboardPwd"].isascii() and record["keyboardPwd"].isdigit()
                and (digits is None or record["keyboardPwd"] == digits)
                and str(record.get("keyboardPwdType")) == "3"
                and str(record.get("startDate")) == str(int(as_utc(pin.valid_from_utc).timestamp() * 1000))
                and str(record.get("endDate")) == str(int(as_utc(pin.valid_until_utc).timestamp() * 1000))
                and str(record.get("keyboardPwdId", "")).isascii()
                and str(record.get("keyboardPwdId", "")).isdigit()
                and int(record["keyboardPwdId"]) > 0):
            matches.append(record)
    if len(matches) == 1:
        record = matches[0]
        pin.keyboard_pwd_id = str(record["keyboardPwdId"])
        pin.encrypted_pin = cipher.encrypt(record["keyboardPwd"].encode()).decode()
        pin.status = "active"
        pin.error_code = None
        db.commit()
        return True
    # Absence is not proof a delayed create cannot still arrive. No automatic retry.
    return False
