from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..config import settings
from ..models import NotificationLog, Team


def send_email_notification(
    db: Session,
    team: Team,
    event_type: str,
    subject: str,
    body: str,
) -> NotificationLog:
    recipient = team.email
    log = NotificationLog(
        team_id=team.id,
        event_type=event_type,
        channel="email",
        recipient=recipient,
        subject=subject,
        body=body,
        status="skipped",
    )

    if not team.notify_email or not recipient:
        log.error = "Notificações por e-mail desativadas ou sem endereço de e-mail"
        db.add(log)
        db.commit()
        return log

    if not settings.smtp_host:
        log.error = "SMTP_HOST não está configurado"
        db.add(log)
        db.commit()
        return log

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        log.status = "sent"
        log.sent_at = datetime.utcnow()
    except Exception as exc:  # keep scheduling operations usable if email is unavailable
        log.status = "failed"
        log.error = str(exc)

    db.add(log)
    db.commit()
    return log


def send_many(
    db: Session,
    teams: list[Team],
    event_type: str,
    subject: str,
    body: str,
) -> None:
    seen: set[int] = set()
    for team in teams:
        if team.id in seen:
            continue
        seen.add(team.id)
        send_email_notification(db, team, event_type, subject, body)
