from itertools import groupby

from ..schemas.calendar import LeagueMatch
from ..schemas.state import ClassificationRow
from ..schemas.teams import TeamSummary


def calculate_classification(teams: list[TeamSummary], matches: list[LeagueMatch], mode: str = "standard") -> list[ClassificationRow]:
    statistics = {team.id: ClassificationRow(team=team) for team in teams}
    completed = [match for match in matches if match.score_a is not None and match.score_b is not None]
    for match in completed:
        a, b = statistics.get(match.team_a.id), statistics.get(match.team_b.id)
        if a is None or b is None:
            continue
        a.played += 1
        b.played += 1
        a.goals_for += match.score_a
        a.goals_against += match.score_b
        b.goals_for += match.score_b
        b.goals_against += match.score_a
        if mode == "total-points":
            a.points += match.score_a
            b.points += match.score_b
        if match.score_a > match.score_b:
            a.wins += 1
            b.losses += 1
            if mode == "standard":
                a.points += 3
        elif match.score_b > match.score_a:
            b.wins += 1
            a.losses += 1
            if mode == "standard":
                b.points += 3
        else:
            a.draws += 1
            b.draws += 1
            if mode == "standard":
                a.points += 1
                b.points += 1
    for row in statistics.values():
        row.goal_difference = row.goals_for - row.goals_against

    def primary(row):
        return (-row.points,) if mode == "total-points" else (-row.points, -row.goal_difference, -row.goals_for)

    ordered = []
    for _, group in groupby(sorted(statistics.values(), key=primary), key=primary):
        tied = list(group)
        head = {row.team.id: [0, 0, 0] for row in tied}
        for match in completed:
            if match.team_a.id not in head or match.team_b.id not in head:
                continue
            a, b = head[match.team_a.id], head[match.team_b.id]
            a[1] += match.score_a
            a[2] += match.score_b
            b[1] += match.score_b
            b[2] += match.score_a
            a[0] += 3 if match.score_a > match.score_b else 1 if match.score_a == match.score_b else 0
            b[0] += 3 if match.score_b > match.score_a else 1 if match.score_a == match.score_b else 0
        tied.sort(key=lambda row: (-head[row.team.id][0], -(head[row.team.id][1] - head[row.team.id][2]),
                                   -head[row.team.id][1], row.team.number))
        ordered.extend(tied)
    for position, row in enumerate(ordered, 1):
        row.position = position
    return ordered
