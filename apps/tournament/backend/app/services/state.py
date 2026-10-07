from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..schemas.calendar import LeagueMatch
from ..schemas.settings import DisplaySettings, TournamentSettings
from ..schemas.state import GroupStanding, PublicState
from ..schemas.teams import Group, Player, Team, TeamSummary
from .bracket import calculate_bracket
from .classification import calculate_classification


def get_settings(db: Session) -> TournamentSettings:
    row = db.get(m.TournamentSettings, 1)
    if row is None:
        raise RuntimeError("As definições do torneio não foram inicializadas.")
    return TournamentSettings(name=row.name, classification_mode=row.classification_mode,
                              final_round_count=row.final_round_count, third_place_enabled=bool(row.third_place_enabled))


def get_display(db: Session) -> DisplaySettings:
    row = db.get(m.DisplaySettings, 1)
    if row is None:
        raise RuntimeError("As definições do ecrã não foram inicializadas.")
    return DisplaySettings(active_panel=row.active_panel if row.active_panel in ("next-match", "latest-results", "classification") else "latest-results",
                           zoom_percent=row.zoom_percent if type(row.zoom_percent) is int and 50 <= row.zoom_percent <= 400 else 100)


def group_from_row(row: m.Group) -> Group:
    return Group(id=row.id, name=row.name, sort_order=row.sort_order)


def get_groups(db: Session) -> list[Group]:
    return [group_from_row(row) for row in db.scalars(select(m.Group).order_by(m.Group.sort_order, m.Group.id))]


def get_teams(db: Session) -> list[TeamSummary]:
    return [TeamSummary(id=team.id, number=team.number, name=team.name, group=group_from_row(group))
            for team, group in db.execute(select(m.Team, m.Group).join(m.Group, m.Team.group_id == m.Group.id).order_by(m.Team.number))]


def player_from_row(row: m.Player) -> Player:
    return Player(id=row.id, team_id=row.team_id, name=row.name, sort_order=row.sort_order)


def get_admin_teams(db: Session) -> list[Team]:
    teams = [Team(**team.model_dump()) for team in get_teams(db)]
    by_id = {team.id: team for team in teams}
    for player in db.scalars(select(m.Player).order_by(m.Player.team_id, m.Player.sort_order, m.Player.id)):
        if player.team_id in by_id:
            by_id[player.team_id].players.append(player_from_row(player))
    return teams


def get_matches(db: Session) -> list[LeagueMatch]:
    teams = {team.id: team for team in get_teams(db)}
    result = []
    for row, round_row in db.execute(select(m.LeagueMatch, m.LeagueRound).join(m.LeagueRound, m.LeagueRound.round_index == m.LeagueMatch.round_index).order_by(m.LeagueMatch.order_index)):
        a, b = teams[row.team_a_id], teams[row.team_b_id]
        result.append(LeagueMatch(id=row.id, game_number=row.order_index, round_number=row.round_index,
                                 counts_toward_standings=bool(round_row.counts_toward_standings),
                                 group=a.group if a.group.id == b.group.id else None,
                                 team_a=a, team_b=b, score_a=row.score_a, score_b=row.score_b))
    return result


def get_final_stage(db: Session):
    settings = get_settings(db)
    teams = {team.id: team for team in get_teams(db)}
    seeds = {row.slot_index: teams.get(row.team_id) for row in db.scalars(select(m.FinalSeed))}
    results = {(row.round_index, row.match_index): (row.score_a, row.score_b) for row in db.scalars(select(m.FinalResult))}
    return calculate_bracket(settings.final_round_count, seeds, results, settings.third_place_enabled)


def get_public_state(db: Session) -> PublicState:
    settings, groups, teams, matches = get_settings(db), get_groups(db), get_teams(db), get_matches(db)
    standings = [GroupStanding(group=group, rows=calculate_classification(
        [team for team in teams if team.group.id == group.id],
        [match for match in matches if match.counts_toward_standings and match.team_a.group.id == group.id and match.team_b.group.id == group.id],
        settings.classification_mode)) for group in groups]
    return PublicState(tournament=settings, display=get_display(db), groups=groups, matches=matches,
                       group_standings=standings, final_stage=get_final_stage(db))
