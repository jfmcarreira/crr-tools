from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..config import settings
from ..models import Assignment, Schedule, SwapRequest, Team
from ..i18n import day_numeric_long, day_short
from ..services.notifications import send_email_notification
from ..services.scheduling import in_scheduling_window, month_bounds, pattern_teams, rotation_team_for_date, scheduling_horizon
from .schedule_helpers import _pattern_map

def _apply_pattern_to_open_rows(db: Session, schedule: Schedule) -> int:
    """Fill empty generated nights from the pattern; never touch existing assignees."""
    patterns = _pattern_map(db, schedule)
    if not patterns:
        return 0
    today = date.today()
    rows = db.scalars(
        select(Assignment).where(
            Assignment.schedule_id == schedule.id,
            Assignment.team_id.is_(None),
            Assignment.source == "generated",
            Assignment.date >= today,
            Assignment.date <= scheduling_horizon(),
        )
    ).all()
    touched = 0
    for row in rows:
        team_id = patterns.get(row.date.day)
        if team_id and row.team_id != team_id:
            row.team_id = team_id
            touched += 1
    if touched:
        db.commit()
    return touched


def _apply_pattern_forward(db: Session, schedule: Schedule, first: date) -> int:
    """Explicit admin edit: push the monthly pattern onto generated assignments from `first` on.

    Never creates or deletes rows, keeps assignment IDs, and preserves manual
    assignments and completed swaps. A day with nobody in the pattern is left as
    it is, so an empty pattern entry cannot blank out a shift.
    """
    patterns = pattern_teams(db, schedule)
    if not patterns:
        return 0
    first = max(first, date.today())
    rows = db.scalars(
        select(Assignment)
        .where(
            Assignment.schedule_id == schedule.id,
            Assignment.date >= first,
            Assignment.date <= scheduling_horizon(),
            Assignment.source == "generated",
        )
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
        .order_by(Assignment.date)
    ).all()
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    touched = 0
    for row in rows:
        team_id = patterns.get(row.date.day)
        if team_id is None or row.team_id == team_id:
            continue
        old_team = db.get(Team, row.team_id) if row.team_id is not None else None
        new_team = db.get(Team, team_id)
        changed.append((row, old_team, new_team))
        for swap in db.scalars(
            select(SwapRequest).where(
                SwapRequest.assignment_id == row.id,
                SwapRequest.status.in_(["open", "pending_approval"]),
            )
        ).all():
            swap.status = "cancelled"
        row.team_id = team_id
        row.team = new_team
        touched += 1
    if changed:
        db.commit()
        _notify_assignment_changes(db, changed)
    return touched


def _clear_assignments_from(db: Session, schedule: Schedule, first: date) -> int:
    """Explicit admin edit: leave the shifts from `first` on without an assignee.

    Only `generated` rows are touched, so manual assignments and completed swaps
    survive. Rows keep their IDs, notes and swap history and stay `generated`, so
    applying the rotation again fills them.
    """
    rows = db.scalars(
        select(Assignment)
        .where(
            Assignment.schedule_id == schedule.id,
            Assignment.date >= max(first, date.today()),
            Assignment.date <= scheduling_horizon(),
            Assignment.source == "generated",
            Assignment.team_id.is_not(None),
        )
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
        .order_by(Assignment.date)
    ).all()
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    for row in rows:
        old_team = db.get(Team, row.team_id)
        changed.append((row, old_team, None))
        for swap in db.scalars(
            select(SwapRequest).where(
                SwapRequest.assignment_id == row.id,
                SwapRequest.status.in_(["open", "pending_approval"]),
            )
        ).all():
            swap.status = "cancelled"
        row.team_id = None
        row.team = None
    if changed:
        db.commit()
        _notify_assignment_changes(db, changed)
    return len(changed)


def _save_assignments(db: Session, assignments: Sequence[Assignment], form) -> int:
    teams_by_id = {t.id: t for t in db.scalars(select(Team).where(Team.is_active.is_(True))).all()}
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    for assignment in assignments:
        if not in_scheduling_window(assignment.date):
            continue  # past and beyond-horizon days are read-only
        raw = str(form.get(f"assignment_{assignment.id}", "")).strip()
        new_team_id = int(raw) if raw else None
        if new_team_id is not None and new_team_id not in teams_by_id:
            continue
        if assignment.team_id != new_team_id:
            old_team = assignment.team
            new_team = teams_by_id.get(new_team_id) if new_team_id else None
            assignment.team_id = new_team_id
            assignment.source = "manual"
            changed.append((assignment, old_team, new_team))
    db.commit()

    _notify_assignment_changes(db, changed)
    return len(changed)


def _default_team(db: Session, schedule: Schedule, day: date) -> Team | None:
    """Who this shift would have by default: the rotation order or the night pattern."""
    if schedule.schedule_type == "rotation":
        return rotation_team_for_date(db, schedule, day)
    team_id = _pattern_map(db, schedule).get(day.day)
    return db.get(Team, team_id) if team_id else None


def _set_assignee(
    db: Session, assignment: Assignment, new_team: Team | None, source: str = "manual"
) -> None:
    """Put someone on a shift directly: no change request, and any stale one is closed."""
    assignment.team_id = new_team.id if new_team else None
    assignment.team = new_team
    assignment.source = source
    for swap in db.scalars(
        select(SwapRequest).where(
            SwapRequest.status.in_(["open", "pending_approval"]),
            (SwapRequest.assignment_id == assignment.id)
            | (SwapRequest.target_assignment_id == assignment.id),
        )
    ).all():
        swap.status = "cancelled"
    db.commit()


def _notify_assignment_changes(db: Session, changed: Sequence[tuple[Assignment, Team | None, Team | None]]) -> None:
    for assignment, old_team, new_team in changed:
        subject = f"Escala atualizada: {day_short(assignment.date)} – {assignment.schedule.name}"
        if new_team:
            send_email_notification(
                db,
                new_team,
                "assignment_updated",
                subject,
                f"Está atribuído ao turno de {assignment.schedule.name} a {day_numeric_long(assignment.date)}.\n\n"
                f"Ver a escala: {settings.normalized_base_url}/",
            )
        # One user, one mail: moving a shift between two of its own teams only
        # announces the shift it ends up with.
        same_user = (
            old_team is not None
            and new_team is not None
            and old_team.user_id is not None
            and old_team.user_id == new_team.user_id
        )
        if old_team and not same_user and (not new_team or old_team.id != new_team.id):
            send_email_notification(
                db,
                old_team,
                "assignment_changed",
                subject,
                f"Já não está atribuído ao turno de {assignment.schedule.name} a {day_numeric_long(assignment.date)}.\n\n"
                f"Ver a escala: {settings.normalized_base_url}/",
            )


def _month_assignments(db: Session, year: int, month: int) -> list[Assignment]:
    first, last = month_bounds(year, month)
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.date >= first, Assignment.date <= last)
            .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
            .order_by(Assignment.date)
        ).all()
    )


def _apply_rotation_to_rows(db: Session, schedule: Schedule, assignments: Sequence[Assignment]) -> int:
    """Explicit admin edit: retain assignment IDs and invalidate requests when ownership changes."""
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    touched = 0
    db.flush()
    for assignment in sorted(assignments, key=lambda row: row.date):
        new_team = rotation_team_for_date(db, schedule, assignment.date)
        new_team_id = new_team.id if new_team else None
        if assignment.team_id == new_team_id and assignment.source == "generated":
            continue
        if assignment.team_id != new_team_id:
            old_team = db.get(Team, assignment.team_id) if assignment.team_id is not None else None
            changed.append((assignment, old_team, new_team))
            if assignment.id is not None:
                requests = db.scalars(select(SwapRequest).where(
                    SwapRequest.assignment_id == assignment.id,
                    SwapRequest.status.in_(["open", "pending_approval"]),
                )).all()
                for swap in requests:
                    swap.status = "cancelled"
        assignment.team_id = new_team_id
        assignment.team = new_team
        assignment.source = "generated"
        # Later dates continue from the team selected for this date.
        db.flush()
        touched += 1
    db.commit()
    _notify_assignment_changes(db, changed)
    return touched


def _generate_rotation_range(db: Session, schedule: Schedule, first: date, last: date) -> tuple[int, int]:
    if first > last:
        return 0, 0
    first = max(first, date.today())
    last = min(last, scheduling_horizon())
    rows = {row.date: row for row in db.scalars(
        select(Assignment)
        .where(Assignment.schedule_id == schedule.id, Assignment.date >= first, Assignment.date <= last)
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
    ).all()}
    assignments = []
    created = 0
    day = first
    while day <= last:
        if day.weekday() not in schedule.weekday_set:
            day += timedelta(days=1)
            continue
        row = rows.get(day)
        if row is None:
            row = Assignment(schedule=schedule, date=day, source="generated")
            db.add(row)
            created += 1
        if row.source == "generated":
            assignments.append(row)
        day += timedelta(days=1)
    changed = _apply_rotation_to_rows(db, schedule, assignments)
    return created, changed
