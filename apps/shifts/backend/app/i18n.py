"""European Portuguese labels, dates and enum translations.

The interface, the notification emails and every rendered date are pt-PT.
`datetime.strftime` is locale-independent in the app container, so weekday and
month names come from the tables below instead of the `calendar` module.
"""

from __future__ import annotations

from datetime import date, datetime, time

MONTHS = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

MONTHS_SHORT = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)

WEEKDAYS_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

WEEKDAYS_LONG = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

SOURCE_LABELS = {
    "generated": "automático",
    "manual": "manual",
    "swap": "troca",
}

SWAP_STATUS_LABELS = {
    "open": "aberto",
    "pending_approval": "aguarda aprovação",
    "approved": "aprovado",
    "rejected": "recusado",
    "reverted": "revertida",
    "cancelled": "cancelado",
}

NOTIFICATION_STATUS_LABELS = {
    "sent": "enviado",
    "skipped": "ignorado",
    "failed": "falhou",
}

EVENT_TYPE_LABELS = {
    "swap_requested": "Pedido de troca",
    "swap_needs_approval": "Troca aguarda aprovação",
    "swap_accepted": "Troca aceite",
    "swap_approved": "Troca aprovada",
    "swap_rejected": "Troca recusada",
    "swap_reverted": "Troca revertida",
    "assignment_updated": "Turno atribuído",
    "assignment_changed": "Turno retirado",
    "shift_reminder": "Lembrete de turno",
    "reminder": "Lembrete",
}


def month_name(month: int) -> str:
    return MONTHS[month - 1]


def weekday_name(weekday: int, *, short: bool = False) -> str:
    names = WEEKDAYS_SHORT if short else WEEKDAYS_LONG
    return names[weekday].capitalize()


def weekday_names(weekdays: set[int]) -> str:
    names = [weekday_name(day) for day in sorted(weekdays)]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} e {names[1]}"
    return ", ".join(names[:-1]) + f" e {names[-1]}"


def day_short(day: date) -> str:
    """`sáb 03 jan`"""
    return f"{WEEKDAYS_SHORT[day.weekday()]} {day.day:02d} {MONTHS_SHORT[day.month - 1]}"


def day_long(day: date) -> str:
    """`sábado, 3 de janeiro de 2026`"""
    return (
        f"{weekday_name(day.weekday())}, {day.day} de {month_name(day.month).lower()} de {day.year}"
    )


def day_numeric(day: date) -> str:
    """`03/01/2026`"""
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def day_numeric_long(day: date) -> str:
    """`3 de janeiro de 2026`"""
    return f"{day.day} de {month_name(day.month).lower()} de {day.year}"


def moment(moment: datetime) -> str:
    """`03/01/2026 21:45`"""
    return f"{day_numeric(moment.date())} {moment.strftime('%H:%M')}"


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def swap_status_label(status: str) -> str:
    return SWAP_STATUS_LABELS.get(status, status.replace("_", " "))


def notification_status_label(status: str) -> str:
    return NOTIFICATION_STATUS_LABELS.get(status, status)


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type, event_type)


def window_label(start: time, end: time) -> str:
    """`20:30–00:00`, the hours a shift runs."""
    return f"{start:%H:%M}\u2013{end:%H:%M}"
