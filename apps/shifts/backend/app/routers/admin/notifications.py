from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ...database import get_db
from ...models import NotificationLog
from ..dependencies import _context, _require_admin

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
        context=_context(request, db, logs=logs),
    )
