from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..errors import AppError
from ..schemas.final_stage import ConfigInput, OverallInput, PerGroupInput, SeedsInput
from .bracket import downstream_matches, get_bracket_match
from .seeding import group_qualification, overall_qualification
from .state import get_final_stage, get_public_state, get_settings
from .teams import existing_team


def configure(db: Session, body: ConfigInput) -> bool:
    if body.third_place_enabled and body.round_count < 2:
        raise AppError(400, "O jogo do 3.º lugar requer pelo menos duas rondas.")
    current = get_settings(db)
    changed = current.final_round_count != body.round_count or current.third_place_enabled != body.third_place_enabled
    if changed and current.final_round_count is not None and not body.confirm_clear_results:
        raise AppError(409, "Alterar a configuração elimina as equipas e os resultados da fase final. Confirme esta alteração.")
    if changed:
        row = db.get(m.TournamentSettings, 1)
        row.final_round_count, row.third_place_enabled, row.updated_at = body.round_count, int(body.third_place_enabled), func.current_timestamp()
        db.execute(delete(m.FinalSeed))
        db.execute(delete(m.FinalResult))
        db.flush()
    return changed


def clear(db: Session):
    row = db.get(m.TournamentSettings, 1)
    row.final_round_count, row.third_place_enabled, row.updated_at = None, 0, func.current_timestamp()
    db.execute(delete(m.FinalSeed))
    db.execute(delete(m.FinalResult))
    db.flush()


def seed_preview(db: Session, body: PerGroupInput | OverallInput):
    state = get_public_state(db)
    if state.tournament.final_round_count is None:
        raise AppError(409, "Configure primeiro o número de rondas da fase final.")
    standings = [standing for standing in state.group_standings if standing.rows]
    if not standings:
        raise AppError(409, "Ainda não existem equipas classificadas para preencher a fase final.")
    if not any(row.played > 0 for standing in standings for row in standing.rows):
        raise AppError(409, "Ainda não existem resultados contabilizados na classificação.")
    if any(match.counts_toward_standings and (match.score_a is None or match.score_b is None) for match in state.matches):
        raise AppError(409, "Conclua primeiro todos os jogos que contam para a classificação.")
    slots = 2 ** state.tournament.final_round_count
    if isinstance(body, PerGroupInput):
        for standing in standings:
            if len(standing.rows) < body.qualifiers_per_group:
                raise AppError(400, f"{standing.group.name} não tem {body.qualifiers_per_group} equipas para apurar.")
        if len(standings) * body.qualifiers_per_group > slots:
            raise AppError(400, f"A fase final só tem {slots} lugares. Reduza o número de apurados por grupo.")
        return group_qualification(standings, body.qualifiers_per_group, slots)
    count = sum(len(standing.rows) for standing in standings)
    if body.qualifier_count > slots:
        raise AppError(400, f"A fase final só tem {slots} lugares. Reduza o número total de apurados.")
    if body.qualifier_count > count:
        raise AppError(400, f"Só existem {count} equipas classificadas.")
    return overall_qualification(standings, body.qualifier_count, slots, state.tournament.classification_mode)


def save_seeds(db: Session, body: SeedsInput) -> bool:
    settings = get_settings(db)
    if settings.final_round_count is None:
        raise AppError(409, "Configure primeiro o número de rondas da fase final.")
    slots = 2 ** settings.final_round_count
    if len(body.seeds) != slots or {seed.slot_index for seed in body.seeds} != set(range(1, slots + 1)):
        raise AppError(400, f"Indique exatamente as {slots} posições iniciais da fase final.")
    assigned = [seed.team_id for seed in body.seeds if seed.team_id is not None]
    if len(set(assigned)) != len(assigned):
        raise AppError(400, "A mesma equipa não pode ser atribuída a mais do que uma posição.")
    for identifier in assigned:
        existing_team(db, identifier)
    current = {row.slot_index: row.team_id for row in db.scalars(select(m.FinalSeed))}
    changed = len(current) != len(body.seeds) or any(current.get(seed.slot_index) != seed.team_id for seed in body.seeds)
    if changed and db.scalar(select(m.FinalResult.round_index).limit(1)) is not None and not body.confirm_clear_results:
        raise AppError(409, "Alterar as equipas iniciais elimina todos os resultados da fase final. Confirme esta alteração.")
    if changed:
        db.execute(delete(m.FinalSeed))
        db.execute(delete(m.FinalResult))
        db.add_all([m.FinalSeed(slot_index=seed.slot_index, team_id=seed.team_id) for seed in body.seeds])
        db.flush()
    return changed


def match_for_result(db: Session, round_index: int, match_index: int, require_teams: bool):
    stage = get_final_stage(db)
    if stage.round_count is None:
        raise AppError(409, "A fase final ainda não está configurada.")
    match = get_bracket_match(stage, round_index, match_index)
    if match is None:
        raise AppError(404, "O jogo da fase final não existe.")
    if require_teams and (match.team_a.team is None or match.team_b.team is None or match.team_a.pending or match.team_b.pending):
        raise AppError(409, "Só pode registar um resultado quando as duas equipas estiverem apuradas.")
    return stage, match


def invalidate_results(db: Session, stage, round_index: int, match_index: int, previous_winner: int | None):
    db.flush()
    match = get_bracket_match(get_final_stage(db), round_index, match_index)
    next_winner = match.winner.id if match.winner else None
    if previous_winner == next_winner:
        return
    downstream = downstream_matches(stage.round_count, round_index, match_index)
    if stage.third_place_enabled and round_index == stage.round_count - 1 and match_index <= 2:
        downstream.append((stage.round_count, 2))
    for index, number in downstream:
        db.execute(delete(m.FinalResult).where(m.FinalResult.round_index == index, m.FinalResult.match_index == number))


def save_result(db: Session, round_index: int, match_index: int, score_a: int, score_b: int):
    if score_a == score_b:
        raise AppError(400, "Os jogos da fase final não podem terminar empatados.")
    stage, match = match_for_result(db, round_index, match_index, True)
    previous = match.winner.id if match.winner else None
    row = db.get(m.FinalResult, (round_index, match_index))
    if row is None:
        row = m.FinalResult(round_index=round_index, match_index=match_index)
        db.add(row)
    row.score_a, row.score_b = score_a, score_b
    invalidate_results(db, stage, round_index, match_index, previous)


def clear_result(db: Session, round_index: int, match_index: int):
    stage, match = match_for_result(db, round_index, match_index, False)
    previous = match.winner.id if match.winner else None
    db.execute(delete(m.FinalResult).where(m.FinalResult.round_index == round_index, m.FinalResult.match_index == match_index))
    invalidate_results(db, stage, round_index, match_index, previous)
