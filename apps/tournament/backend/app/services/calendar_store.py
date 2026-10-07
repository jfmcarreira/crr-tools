from random import SystemRandom

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as m
from ..errors import AppError
from ..schemas.calendar import Generation, GenerationInput, GenerationTeam
from .calendar import generate_calendar
from .state import get_groups, get_matches, get_teams


def summary(matches):
    return {"matches": matches, "matchCount": len(matches), "roundCount": max((match.round_number for match in matches), default=0)}


def ordered_teams(db: Session, generation: Generation):
    teams = get_teams(db)
    if len(generation.team_order) != len(teams):
        raise AppError(409, "As equipas foram alteradas. Sorteie novamente o calendário.")
    by_id, seen, ordered = {team.id: team for team in teams}, set(), []
    for entry in generation.team_order:
        team = by_id.get(entry.team_id)
        if team is None or team.group.id != entry.group_id or entry.team_id in seen:
            raise AppError(409, "As equipas ou os grupos foram alterados. Sorteie novamente o calendário.")
        seen.add(entry.team_id)
        ordered.append(team)
    return ordered


def matches_for_generation(db: Session, generation: Generation):
    matches = generate_calendar(ordered_teams(db, generation), generation.legs)
    if not matches:
        raise AppError(409, "São necessárias pelo menos duas equipas no mesmo grupo para gerar o calendário.")
    return matches


def generate_preview(db: Session, legs: int):
    teams = get_teams(db)
    order = []
    for group in get_groups(db):
        members = [team for team in teams if team.group.id == group.id]
        SystemRandom().shuffle(members)
        order += [GenerationTeam.model_validate({"teamId": team.id, "groupId": group.id}) for team in members]
    generation = Generation.model_validate({"legs": legs, "teamOrder": order})
    return {"generation": generation, **summary(matches_for_generation(db, generation))}


def save_calendar(db: Session, body: GenerationInput):
    matches = matches_for_generation(db, body.generation)
    has_scores = db.scalar(select(m.LeagueMatch.id).where(m.LeagueMatch.score_a.is_not(None)).limit(1)) is not None
    if has_scores and not body.confirm_replace:
        raise AppError(409, "Já existem resultados registados. Confirme a substituição do calendário para eliminar esses resultados.")
    clear_calendar(db)
    for round_number in sorted({match.round_number for match in matches}):
        db.add(m.LeagueRound(round_index=round_number))
    for match in matches:
        db.add(m.LeagueMatch(order_index=match.game_number, round_index=match.round_number,
                            team_a_id=match.team_a.id, team_b_id=match.team_b.id))
    db.flush()
    return summary(get_matches(db))


def clear_calendar(db: Session):
    db.execute(delete(m.LeagueMatch))
    db.execute(delete(m.LeagueRound))
