from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AccessPin
from ..services.door_access import (
    DoorAccessError, LISBON_TZ, as_utc, expire_pins, issue_pin, reconcile_pin, visible_pin,
)
from .dependencies import _check_csrf, _context, _flash, _redirect, _require_admin, _require_user

router = APIRouter()
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


@router.post("/access/pins")
def request_pin(request: Request, assignment_id: int = Form(...), csrf_token: str = Form(...),
                db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _check_csrf(request, csrf_token)
    try:
        pin = issue_pin(db, user, assignment_id, datetime.now(timezone.utc))
    except DoorAccessError as exc:
        raise HTTPException(exc.status_code, str(exc), headers=PRIVATE_HEADERS) from None
    response = _redirect(f"/access/pins/{pin.id}")
    response.headers.update(PRIVATE_HEADERS)
    return response


@router.get("/access/pins/{pin_id}")
def view_pin(request: Request, pin_id: int, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    now = datetime.now(timezone.utc)
    expire_pins(db, now)
    try:
        digits = visible_pin(db, user, pin_id, now)
    except DoorAccessError as exc:
        raise HTTPException(exc.status_code, str(exc), headers=PRIVATE_HEADERS) from None
    pin = db.get(AccessPin, pin_id)
    return request.app.state.templates.TemplateResponse(
        request=request, name="access_pin.html", headers=PRIVATE_HEADERS,
        context=_context(request, db, digits=digits,
                         expires=as_utc(pin.valid_until_utc).astimezone(LISBON_TZ).strftime("%d/%m/%Y %H:%M:%S %Z")),
    )


@router.get("/admin/access")
def access_status(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    expire_pins(db, datetime.now(timezone.utc))
    pins = db.scalars(select(AccessPin).order_by(AccessPin.id.desc()).limit(100)).all()
    return request.app.state.templates.TemplateResponse(
        request=request, name="admin_access.html", headers=PRIVATE_HEADERS,
        context=_context(request, db, pins=pins),
    )


@router.post("/admin/access/{pin_id}/reconcile")
def reconcile(request: Request, pin_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    _require_admin(request, db)
    _check_csrf(request, csrf_token)
    try:
        found = reconcile_pin(db, pin_id, datetime.now(timezone.utc))
    except DoorAccessError as exc:
        raise HTTPException(exc.status_code, str(exc), headers=PRIVATE_HEADERS) from None
    _flash(request, "Código confirmado." if found else "Código não confirmado. Não será emitido outro código.")
    response = _redirect("/admin/access")
    response.headers.update(PRIVATE_HEADERS)
    return response
