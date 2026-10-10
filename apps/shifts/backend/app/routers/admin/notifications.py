from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData
from ...database import get_db
from ...models import NotificationLog, NotificationSetting
from ...services.notification_settings import MASTER_SETTING_KEY, NOTIFICATION_CHANNELS, notification_enabled
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
        context=_context(request, db, logs=logs, notification_channels=NOTIFICATION_CHANNELS,
                         notifications_enabled={channel: notification_enabled(db, channel)
                                                for channel in NOTIFICATION_CHANNELS}),
    )


@router.post("/admin/notifications/settings")
def update_notification_settings(
    request: Request,
    form: FormData = Depends(_raw_form),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, str(form.get("csrf_token", "")))
    for channel in NOTIFICATION_CHANNELS:
        setting = db.get(NotificationSetting, (MASTER_SETTING_KEY[0], channel))
        if setting is None:
            setting = NotificationSetting(event_type=MASTER_SETTING_KEY[0], channel=channel)
            db.add(setting)
        setting.enabled = form.get(f"{channel}_enabled") == "on"
    db.commit()
    _flash(request, "Opções de envio de notificações guardadas.")
    return _redirect("/admin/notifications")
