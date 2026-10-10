from __future__ import annotations

import json
from datetime import datetime

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import NotificationLog, PushSubscription, Team
from .notification_settings import notification_enabled


def send_push_notification(db: Session, team: Team, event_type: str, subject: str, body: str) -> None:
    user = team.user
    if not settings.push_enabled or user is None or not user.is_active:
        return
    subscriptions = list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)))
    enabled = notification_enabled(db, "push")
    for subscription in subscriptions:
        log = NotificationLog(
            team_id=team.id, user_id=user.id, event_type=event_type, channel="push",
            subject=subject, body=body, status="failed",
        )
        if not enabled:
            log.status = "skipped"
            log.error = "Envio de notificações push em pausa pelo interruptor geral"
            db.add(log)
            db.commit()
            continue
        try:
            webpush(
                subscription_info={"endpoint": subscription.endpoint, "keys": {
                    "p256dh": subscription.p256dh, "auth": subscription.auth,
                }},
                data=json.dumps({"title": subject, "body": body[:1000], "url": settings.url("/my-days")}),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
                timeout=10,
            )
            log.status = "sent"
            log.sent_at = datetime.utcnow()
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            # Do not log provider responses, subscription URLs or credentials.
            log.error = f"Falha no envio push (HTTP {status})" if status else "Falha no envio push"
            if status in (404, 410):
                db.delete(subscription)
        except Exception:
            log.error = "Falha no envio push"
        db.add(log)
        db.commit()
