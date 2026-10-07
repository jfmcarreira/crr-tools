from random import SystemRandom

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..errors import AppError
from ..schemas.base import MAX_SAFE_INTEGER
from ..schemas.teams import TeamCreate, TeamInput
from .state import get_admin_teams, get_groups, group_from_row


def existing_group(db: Session, identifier: int):
    row = db.get(m.Group, identifier)
    if row is None:
        raise AppError(404, "O grupo não existe.")
    return row


def existing_team(db: Session, identifier: int):
    row = db.get(m.Team, identifier)
    if row is None:
        raise AppError(404, "A equipa não existe.")
    return row


def available_group_name(db: Session, name: str, except_id: int | None = None):
    query = select(m.Group).where(m.Group.name == name)
    if except_id is not None:
        query = query.where(m.Group.id != except_id)
    if db.scalar(query) is not None:
        raise AppError(409, "Já existe um grupo com esse nome.")


def create_group(db: Session, name: str):
    available_group_name(db, name)
    order = db.scalar(select(func.max(m.Group.sort_order)))
    row = m.Group(name=name, sort_order=0 if order is None else order + 1)
    db.add(row)
    db.flush()
    return group_from_row(row)


def update_group(db: Session, identifier: int, name: str):
    row = existing_group(db, identifier)
    available_group_name(db, name, identifier)
    row.name, row.updated_at = name, func.current_timestamp()
    db.flush()
    return group_from_row(row)


def delete_group(db: Session, identifier: int):
    row = existing_group(db, identifier)
    if db.scalar(select(m.Team.id).where(m.Team.group_id == identifier).limit(1)) is not None:
        raise AppError(409, "Não é possível eliminar um grupo com equipas.")
    if db.scalar(select(func.count()).select_from(m.Group)) <= 1:
        raise AppError(409, "Não é possível eliminar o último grupo.")
    db.delete(row)


def used_in_calendar(db: Session, identifier: int) -> bool:
    return db.scalar(select(m.LeagueMatch.id).where(or_(m.LeagueMatch.team_a_id == identifier,
                                                      m.LeagueMatch.team_b_id == identifier)).limit(1)) is not None


def create_team(db: Session, body: TeamCreate):
    existing_group(db, body.group_id)
    number = body.number
    if number is None:
        maximum = db.scalar(select(func.max(m.Team.number))) or 0
        if maximum >= MAX_SAFE_INTEGER:
            raise AppError(409, "Não é possível atribuir outro número de equipa.")
        number = maximum + 1
    row = m.Team(number=number, name=body.name, group_id=body.group_id)
    db.add(row)
    db.flush()
    return next(team for team in get_admin_teams(db) if team.id == row.id)


def update_team(db: Session, identifier: int, body: TeamInput):
    row = existing_team(db, identifier)
    existing_group(db, body.group_id)
    if row.group_id != body.group_id and used_in_calendar(db, identifier):
        raise AppError(409, "Não é possível alterar o grupo de uma equipa utilizada no calendário. Limpe ou substitua o calendário primeiro.")
    row.number, row.name, row.group_id, row.updated_at = body.number, body.name, body.group_id, func.current_timestamp()
    db.flush()
    return next(team for team in get_admin_teams(db) if team.id == identifier)


def delete_team(db: Session, identifier: int):
    row = existing_team(db, identifier)
    if used_in_calendar(db, identifier):
        raise AppError(409, "Não é possível eliminar esta equipa porque está a ser utilizada no calendário.")
    if db.scalar(select(m.FinalSeed.slot_index).where(m.FinalSeed.team_id == identifier).limit(1)) is not None:
        raise AppError(409, "Não é possível eliminar esta equipa porque está a ser utilizada na fase final.")
    db.delete(row)


def randomize_teams(db: Session):
    teams = list(db.scalars(select(m.Team).order_by(m.Team.number)))
    groups = get_groups(db)
    has_calendar = db.scalar(select(m.LeagueMatch.id).limit(1)) is not None
    if has_calendar:
        db.execute(delete(m.LeagueMatch))
        db.execute(delete(m.LeagueRound))
    maximum = max((row.number for row in teams), default=0)
    numbers, shuffled_groups = [row.number for row in teams], list(groups)
    SystemRandom().shuffle(numbers)
    SystemRandom().shuffle(shuffled_groups)
    for index, row in enumerate(teams, 1):
        row.number = maximum + index
    db.flush()
    for index, row in enumerate(teams):
        row.number, row.group_id, row.updated_at = numbers[index], shuffled_groups[index % len(groups)].id, func.current_timestamp()
    db.flush()
    return {"teams": get_admin_teams(db), "calendarCleared": has_calendar}
