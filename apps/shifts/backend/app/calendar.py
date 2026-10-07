"""iCalendar feed of the rota, so members can subscribe from any calendar app.

Events carry the bar's timezone (`DTSTART;TZID=Europe/Lisbon:20261017T203000`)
plus a VTIMEZONE block with the European summer-time rules, so a shift shows at
20:30 in the reader's calendar and keeps the right offset across the year.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .i18n import day_long, day_numeric_long, window_label
from .models import Assignment, Schedule, Team

# How much of the rota the feed publishes: recent history and the next months.
MONTHS_BACK = 1
MONTHS_FORWARD = 6

DEFAULT_TIMEZONE = "Europe/Lisbon"


def feed_timezone() -> str:
    """The configured zone, falling back to Lisbon when it is unknown."""
    try:
        ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TIMEZONE
    return settings.timezone


def _timezone_block(tzid: str) -> list[str]:
    """European rules: the last Sunday in March moves to WEST, in October back to WET."""
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{tzid}",
        f"X-LIC-LOCATION:{tzid}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0000",
        "TZOFFSETTO:+0100",
        "TZNAME:WEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0000",
        "TZNAME:WET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _fold(line: str) -> list[str]:
    """RFC 5545 folds long lines at 75 octets, never cutting a character in half."""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    parts: list[str] = []
    current: list[str] = []
    used = 0
    limit = 75
    for character in line:
        size = len(character.encode("utf-8"))
        if used + size > limit:
            parts.append("".join(current))
            current = []
            used = 0
            limit = 74  # continuation lines start with a space
        current.append(character)
        used += size
    if current:
        parts.append("".join(current))
    return [parts[0]] + [" " + part for part in parts[1:]]


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _event(assignment: Assignment, team: Team | None, tzid: str) -> list[str]:
    schedule = assignment.schedule
    start = datetime.combine(assignment.date, schedule.start_time)
    end = datetime.combine(assignment.date, schedule.end_time)
    if end <= start:  # a shift that runs past midnight
        end += timedelta(days=1)
    # The team's name is part of the event title, so a list of shifts reads at a glance.
    summary = (
        f"{team.name} · {schedule.name}" if team is not None else f"{schedule.name}"
    )
    description = [
        day_long(assignment.date),
        f"{schedule.start_time:%H:%M}–{schedule.end_time:%H:%M}",
    ]
    if team is not None:
        description.append(f"Equipa: {team.name}")
    description.append(settings.app_name)
    return [
        "BEGIN:VEVENT",
        f"UID:assignment-{assignment.id}@{_host()}",
        f"DTSTAMP:{_stamp(datetime.utcnow())}",
        f"DTSTART;TZID={tzid}:{start:%Y%m%dT%H%M%S}",
        f"DTEND;TZID={tzid}:{end:%Y%m%dT%H%M%S}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(chr(10).join(description))}",
        f"LOCATION:{_escape(settings.app_name)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def _host() -> str:
    return (settings.base_url.split("//")[-1] or "localhost").split("/")[0]


def build_feed(db: Session, team: Team | None, name: str) -> str:
    """The whole rota, or only the shifts of one team."""
    today = date.today()
    first = (today.replace(day=1) - timedelta(days=31 * MONTHS_BACK)).replace(day=1)
    last = (today.replace(day=1) + timedelta(days=32 * MONTHS_FORWARD)).replace(
        day=1
    ) - timedelta(days=1)

    schedules = db.scalars(select(Schedule).where(Schedule.is_active.is_(True))).all()
    assignments = db.scalars(
        select(Assignment)
        .where(
            Assignment.date >= first,
            Assignment.date <= last,
            Assignment.schedule_id.in_([s.id for s in schedules]),
        )
        .options(selectinload(Assignment.schedule), selectinload(Assignment.team))
        .order_by(Assignment.date)
    ).all()
    if team is not None:
        assignments = [a for a in assignments if a.team_id == team.id]

    tzid = feed_timezone()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_escape(settings.app_name)}//Rota//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-CALDESC:{_escape(f'{settings.app_name} — {day_numeric_long(first)} a {day_numeric_long(last)}')}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        f"X-WR-TIMEZONE:{tzid}",
    ]
    lines.extend(_timezone_block(tzid))
    for assignment in assignments:
        lines.extend(_event(assignment, assignment.team, tzid))
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
