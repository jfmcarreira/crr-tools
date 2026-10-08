from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..models import Assignment, MonthlyPattern, RotationMember, Schedule, Team


def scheduling_horizon() -> date:
    """The last day that may be scheduled: today's month plus the configured months."""
    today = date.today()
    index = today.year * 12 + today.month - 1 + settings.scheduling_horizon_months
    year, month = divmod(index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def in_scheduling_window(day: date) -> bool:
    """Whether `day` may be scheduled: from today through the horizon, both included."""
    return date.today() <= day <= scheduling_horizon()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def iter_month_dates(year: int, month: int):
    first, last = month_bounds(year, month)
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def _rotation_occurrence_index(schedule: Schedule, target: date) -> int:
    """Return zero-based matching-day occurrence index from the schedule anchor."""
    if schedule.rotation_anchor_date is None:
        raise ValueError("Rotation schedule is missing an anchor date")

    anchor = schedule.rotation_anchor_date
    weekdays = schedule.weekday_set
    step = 1 if target >= anchor else -1
    current = anchor
    count = 0

    if step == 1:
        while current < target:
            if current.weekday() in weekdays:
                count += 1
            current += timedelta(days=1)
        return count

    while current > target:
        current -= timedelta(days=1)
        if current.weekday() in weekdays:
            count -= 1
    return count


def rotation_team_for_date(db: Session, schedule: Schedule, target: date) -> Team | None:
    """Continue after the last actual assignee in this schedule, with anchor fallback."""
    if schedule.schedule_type != "rotation" or target.weekday() not in schedule.weekday_set:
        return None

    members = db.scalars(
        select(RotationMember)
        .join(Team, RotationMember.team_id == Team.id)
        .where(RotationMember.schedule_id == schedule.id)
        .order_by(RotationMember.position)
        .options(selectinload(RotationMember.team))
    ).all()
    active_members = [member for member in members if member.team.is_active]
    if not active_members:
        return None

    previous_team_id = db.scalar(
        select(Assignment.team_id)
        .where(
            Assignment.schedule_id == schedule.id,
            Assignment.date < target,
            Assignment.team_id.is_not(None),
        )
        .order_by(Assignment.date.desc())
        .limit(1)
    )
    for idx, member in enumerate(members):
        if member.team_id == previous_team_id:
            for offset in range(1, len(members) + 1):
                next_member = members[(idx + offset) % len(members)]
                if next_member.team.is_active:
                    return next_member.team

    # No usable reference yet (or the last assignee left the rotation).
    idx = _rotation_occurrence_index(schedule, target) % len(active_members)
    return active_members[idx].team


def pattern_team_for_date(db: Session, schedule: Schedule, target: date) -> Team | None:
    """The team configured for this calendar day of the month, if any."""
    row = db.scalar(
        select(MonthlyPattern)
        .where(MonthlyPattern.schedule_id == schedule.id, MonthlyPattern.day_of_month == target.day)
        .options(selectinload(MonthlyPattern.team))
    )
    if row is None or row.team is None or not row.team.is_active:
        return None
    return row.team


def pattern_teams(db: Session, schedule: Schedule) -> dict[int, int]:
    """Active team per calendar day of the month, for a `fixed` schedule."""
    rows = db.scalars(
        select(MonthlyPattern)
        .where(MonthlyPattern.schedule_id == schedule.id)
        .options(selectinload(MonthlyPattern.team))
    ).all()
    return {row.day_of_month: row.team.id for row in rows if row.team is not None and row.team.is_active}


def ensure_month_assignments(db: Session, year: int, month: int) -> list[Assignment]:
    schedules = db.scalars(select(Schedule).where(Schedule.is_active.is_(True))).all()
    first, last = month_bounds(year, month)
    existing = db.scalars(
        select(Assignment).where(Assignment.date >= first, Assignment.date <= last)
    ).all()
    existing_keys = {(a.schedule_id, a.date) for a in existing}

    changed = False
    for schedule in schedules:
        patterns = pattern_teams(db, schedule) if schedule.schedule_type == "fixed" else {}
        for day in iter_month_dates(year, month):
            if day.weekday() not in schedule.weekday_set:
                continue
            key = (schedule.id, day)
            if key in existing_keys:
                continue

            team_id = None
            if schedule.schedule_type == "rotation":
                team = rotation_team_for_date(db, schedule, day)
                team_id = team.id if team else None
            else:
                team_id = patterns.get(day.day)

            db.add(
                Assignment(
                    schedule_id=schedule.id,
                    date=day,
                    team_id=team_id,
                    source="generated",
                )
            )
            # SessionLocal disables autoflush: the next date must see this assignee.
            db.flush()
            changed = True

    if changed:
        db.commit()

    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.date >= first, Assignment.date <= last)
            .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
            .order_by(Assignment.date, Assignment.schedule_id)
        ).all()
    )


def assignments_by_date(assignments: list[Assignment]) -> dict[date, list[Assignment]]:
    result: dict[date, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        result[assignment.date].append(assignment)
    return dict(result)
