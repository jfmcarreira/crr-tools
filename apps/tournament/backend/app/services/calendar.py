from ..schemas.calendar import CalendarMatch
from ..schemas.teams import TeamSummary


def group_rounds(teams: list[TeamSummary]) -> list[list[tuple[TeamSummary, TeamSummary]]]:
    if len(teams) < 2:
        return []
    rotation = list(teams)
    if len(rotation) % 2:
        rotation.append(None)
    rounds = []
    for round_index in range(len(rotation) - 1):
        pairs = []
        for index in range(len(rotation) // 2):
            a, b = rotation[index], rotation[-index - 1]
            if a is not None and b is not None:
                pairs.append((b, a) if round_index % 2 and index == 0 else (a, b))
        rounds.append(pairs)
        rotation.insert(1, rotation.pop())
    return rounds


def generate_calendar(teams: list[TeamSummary], legs: int) -> list[CalendarMatch]:
    if type(legs) is not int or legs not in (1, 2):
        raise ValueError("O número de voltas tem de ser 1 ou 2.")
    groups = {team.group.id: team.group for team in teams}
    rounds = [(group, group_rounds([team for team in teams if team.group.id == group.id]))
              for group in sorted(groups.values(), key=lambda group: (group.sort_order, group.id))]
    round_count = max((len(items) for _, items in rounds), default=0)
    matches = []
    for index in range(round_count):
        for group, items in rounds:
            for a, b in items[index] if index < len(items) else []:
                matches.append(CalendarMatch(game_number=len(matches) + 1, round_number=index + 1,
                                             group=group, team_a=a, team_b=b))
    if legs == 2:
        matches += [CalendarMatch(game_number=len(matches) + index + 1,
                                 round_number=match.round_number + round_count,
                                 group=match.group, team_a=match.team_b, team_b=match.team_a)
                    for index, match in enumerate(matches)]
    return matches
