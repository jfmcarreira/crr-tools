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
    """Send one notification for an event the `team` is concerned by.

    The address is the user's, never the team's: several teams of the same user
    are one recipient, and a rota-only team has nobody to write to.
    """
    user = team.user
    recipient = user.email if user else None
    log = NotificationLog(
        team_id=team.id,
        user_id=user.id if user else None,
        event_type=event_type,
        channel="email",
        recipient=recipient,
        subject=subject,
        body=body,
        status="skipped",
    )

    if user is None:
        log.error = "A equipa não tem utilizador a quem enviar notificações"
        db.add(log)
        db.commit()
        return log

    if not user.notify_email or not recipient:
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
    """One message per user: teams sharing a signer-in are a single recipient."""
    seen_users: set[int] = set()
    seen_teams: set[int] = set()
    for team in teams:
        if team.id in seen_teams:
            continue
        seen_teams.add(team.id)
        user = team.user
        if user is not None:
            if user.id in seen_users:
                continue
            seen_users.add(user.id)
        send_email_notification(db, team, event_type, subject, body)
