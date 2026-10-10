from __future__ import annotations

import code
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .services.bootstrap import ensure_initial_data
from .config import settings
from .database import (
    SessionLocal,
    current_revision,
    run_migrations,
)
from . import models
from .models import (
    Assignment,
    User,
    MonthlyPattern,
    NotificationLog,
    RotationMember,
    Schedule,
    Team,
)
from .i18n import day_long, day_numeric
from .services.notifications import send_email_notification
from .services.scheduling import ensure_month_assignments
from .security import hash_password


def migrate() -> None:
    run_migrations()
    print(f"Database at revision {current_revision()}.")


def init_db() -> None:
    migrate()
    with SessionLocal() as db:
        ensure_initial_data(db)
    print("Database initialized.")


def seed_demo() -> None:
    init_db()
    # Carla and Diogo are two teams covered by the same user, as a real team would be.
    # E-mail belongs to the user, so the shared account has a single address.
    demo_teams = [
        ("Alice", "alice"),
        ("Bruno", "bruno"),
        ("Carla", "sabado"),
        ("Diogo", "sabado"),
    ]
    demo_emails = {
        "alice": "alice@example.com",
        "bruno": "bruno@example.com",
        "sabado": "diogo@example.com",
    }
    with SessionLocal() as db:
        for name, username in demo_teams:
            if db.scalar(select(Team.id).where(Team.name == name)):
                continue  # this team is already there, whoever signs in for it
            user = db.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    name=username.capitalize(),
                    username=username,
                    password_hash=hash_password("demo-password"),
                    email=demo_emails.get(username),
                    is_admin=False,
                    is_active=True,
                )
                db.add(user)
                db.flush()
            db.add(
                Team(
                    name=name,
                    user=user,
                    is_active=True,
                )
            )
        db.commit()
        teams = db.scalars(
            select(Team)
            .join(User)
            .where(User.username.in_([x[1] for x in demo_teams]))
            .order_by(Team.name)
        ).all()
        schedules = db.scalars(
            select(Schedule).where(Schedule.slug.in_(["saturday-lunch", "sunday-lunch"])).order_by(Schedule.id)
        ).all()
        for schedule in schedules:
            if not db.scalar(select(RotationMember.id).where(RotationMember.schedule_id == schedule.id)):
                for pos, team in enumerate(teams, start=1):
                    db.add(RotationMember(schedule_id=schedule.id, team_id=team.id, position=pos))

        night = db.scalar(select(Schedule).where(Schedule.slug == "night"))
        if night is not None and not db.scalar(
            select(MonthlyPattern.id).where(MonthlyPattern.schedule_id == night.id)
        ):
            for day in range(1, 32):
                db.add(MonthlyPattern(
                    schedule_id=night.id,
                    day_of_month=day,
                    team_id=teams[(day - 1) % len(teams)].id,
                ))
        db.commit()

        today = date.today()
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        for month in (today, next_month):
            ensure_month_assignments(db, month.year, month.month)
    print("Demo data seeded for this month and next. Existing assignments and configuration preserved.")
    print("Demo users: alice, bruno, sabado (Carla e Diogo entram com o mesmo utilizador). "
          "Password: demo-password (new accounts only).")


def db_shell() -> None:
    """An interactive SQLAlchemy session against the configured application database."""
    init_db()
    with SessionLocal() as db:
        namespace = {"db": db, "select": select, "models": models}
        namespace.update({name: getattr(models, name) for name in (
            "Team", "User", "Schedule", "MonthlyPattern", "RotationMember", "Assignment", "SwapRequest", "NotificationLog"
        )})
        code.interact(
            banner="Database console: db, select, models and model classes are available.\n"
            "Example: db.scalars(select(Team)).all()\n"
            "Use db.commit() to save edits, db.rollback() to discard them; Ctrl-D to exit.",
            local=namespace,
        )


def send_reminders() -> None:
    migrate()
    target = date.today() + timedelta(days=settings.reminder_days_ahead)
    with SessionLocal() as db:
        ensure_initial_data(db)
        ensure_month_assignments(db, target.year, target.month)
        assignments = db.scalars(
            select(Assignment)
            .where(Assignment.date == target, Assignment.team_id.is_not(None))
            .options(selectinload(Assignment.team).selectinload(Team.user), selectinload(Assignment.schedule))
        ).all()
        count = 0
        for assignment in assignments:
            if not assignment.team or not assignment.team.user:
                continue  # a rota-only team has nobody to remind
            subject = f"Lembrete de turno: {assignment.schedule.name} a {day_numeric(assignment.date)}"
            # One user, one reminder: two of its teams on the same schedule and day is one mail.
            already_sent = db.scalar(
                select(NotificationLog.id).where(
                    NotificationLog.user_id == assignment.team.user_id,
                    NotificationLog.event_type == "shift_reminder",
                    NotificationLog.subject == subject,
                    NotificationLog.status == "sent",
                )
            )
            if already_sent:
                continue
            send_email_notification(
                db,
                assignment.team,
                "shift_reminder",
                subject,
                f"Lembrete: está atribuído ao turno de {assignment.schedule.name} a "
                f"{day_long(assignment.date)}.\n\nVer a escala: {settings.normalized_base_url}/",
            )
            count += 1
    print(f"Processed {count} reminder(s) for {target.isoformat()}.")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    commands = {
        "init-db": init_db,
        "migrate": migrate,
        "seed-demo": seed_demo,
        "db-shell": db_shell,
        "send-reminders": send_reminders,
        "expire-access-pins": expire_access_pins,
    }
    if command not in commands:
        print("Usage: python -m app.cli [init-db|migrate|seed-demo|db-shell|send-reminders|expire-access-pins]")
        raise SystemExit(2)
    commands[command]()


def expire_access_pins() -> None:
    from .services.door_access import expire_pins

    with SessionLocal() as db:
        expire_pins(db, datetime.now(timezone.utc))
    print("Expired access PIN digits cleared. No lock codes were deleted.")


if __name__ == "__main__":
    main()
