from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData
from ...database import get_db
from ...models import NotificationLog, NotificationSetting
from ...services.notification_settings import MASTER_SETTING_KEY, notification_enabled
from ..dependencies import _check_csrf, _context, _flash, _raw_form, _redirect, _require_admin

router = APIRouter()

@router.get("/admin/notifications", response_class=HTMLResponse)
def admin_notifications(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    logs = db.scalars(
        select(NotificationLog)
        .options(selectinload(NotificationLog.team), selectinload(NotificationLog.user))
        .order_by(NotificationLog.created_at.desc())
        .limit(200)
    ).all()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_notifications.html",
        context=_context(request, db, logs=logs, notifications_enabled=notification_enabled(db)),
    )


@router.post("/admin/notifications/settings")
def update_notification_settings(
    request: Request,
    form: FormData = Depends(_raw_form),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, str(form.get("csrf_token", "")))
    setting = db.get(NotificationSetting, MASTER_SETTING_KEY)
    if setting is None:
        setting = NotificationSetting(event_type=MASTER_SETTING_KEY[0], channel=MASTER_SETTING_KEY[1])
        db.add(setting)
    setting.enabled = form.get("notifications_enabled") == "on"
    db.commit()
    _flash(request, "Envio de notificações ativado." if setting.enabled else "Envio de notificações em pausa.")
    return _redirect("/admin/notifications")
