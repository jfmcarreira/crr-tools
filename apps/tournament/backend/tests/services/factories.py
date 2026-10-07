from app.schemas.calendar import LeagueMatch
from app.schemas.state import ClassificationRow, GroupStanding
from app.schemas.teams import Group, TeamSummary


def group(identifier=1, order=0):
    return Group(id=identifier, name=f"Grupo {identifier}", sort_order=order)


def team(identifier, number=None, division=None):
    return TeamSummary(id=identifier, number=number or identifier, name=f"Equipa {number or identifier}",
                       group=division or group())


def score(a, b, score_a, score_b):
    return LeagueMatch(id=1, game_number=1, round_number=1, group=a.group, counts_toward_standings=True,
                       team_a=a, team_b=b, score_a=score_a, score_b=score_b)


def standing(identifier, teams):
    return GroupStanding(group=group(identifier, identifier - 1), rows=[
        ClassificationRow(position=index + 1, team=value, played=1, wins=int(index == 0),
                          losses=int(index != 0), goals_for=3 if index == 0 else 1,
                          goals_against=1 if index == 0 else 3, goal_difference=2 if index == 0 else -2,
                          points=3 if index == 0 else 0)
        for index, value in enumerate(teams)
    ])
