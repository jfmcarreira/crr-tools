from ..schemas.final_stage import BracketMatch, BracketRound, FinalStage, Participant
from ..schemas.teams import TeamSummary


def calculate_bracket(round_count: int | None, seeds: dict[int, TeamSummary | None],
                      results: dict[tuple[int, int], tuple[int | None, int | None]],
                      third_place_enabled: bool = False) -> FinalStage:
    if round_count is None:
        return FinalStage(round_count=None)
    if type(round_count) is not int or not 1 <= round_count <= 8:
        raise ValueError("O número de rondas tem de estar entre 1 e 8.")
    rounds = []
    can_produce = {}
    for index in range(1, round_count + 1):
        matches = []
        for number in range(1, 2 ** (round_count - index) + 1):
            if index == 1:
                a, b = Participant(team=seeds.get(number * 2 - 1)), Participant(team=seeds.get(number * 2))
            else:
                previous = rounds[-1].matches
                a = Participant(team=previous[number * 2 - 2].winner,
                                pending=previous[number * 2 - 2].winner is None and can_produce[index - 1, number * 2 - 1])
                b = Participant(team=previous[number * 2 - 1].winner,
                                pending=previous[number * 2 - 1].winner is None and can_produce[index - 1, number * 2])
            both = a.team is not None and b.team is not None
            bye = not a.pending and not b.pending and ((a.team is None) != (b.team is None))
            empty = not a.pending and not b.pending and a.team is None and b.team is None
            score_a, score_b = results.get((index, number), (None, None)) if both else (None, None)
            winner = a.team or b.team if bye else None
            if both and score_a is not None and score_b is not None and score_a != score_b:
                winner = a.team if score_a > score_b else b.team
            match = BracketMatch(match_index=number, team_a=a, team_b=b, score_a=score_a,
                                 score_b=score_b, winner=winner, is_bye=bye)
            matches.append(match)
            can_produce[index, number] = not empty and (winner is not None or a.pending or b.pending or both)
        count = 2 ** (round_count - index + 1)
        name = {2: "Final", 4: "Meias-finais", 8: "Quartos de final", 16: "Oitavos de final"}.get(count, f"Ronda de {count}")
        rounds.append(BracketRound(round_index=index, name=name, matches=matches))
    third = None
    if third_place_enabled and round_count >= 2:
        def loser(match):
            if match.team_a.pending or match.team_b.pending:
                return Participant(team=None, pending=True)
            if match.team_a.team is None or match.team_b.team is None or match.winner is None:
                return Participant(team=None, pending=match.team_a.team is not None and match.team_b.team is not None)
            return Participant(team=match.team_b.team if match.winner.id == match.team_a.team.id else match.team_a.team)
        a, b = [loser(match) for match in rounds[-2].matches]
        score_a, score_b = results.get((round_count, 2), (None, None)) if a.team is not None and b.team is not None else (None, None)
        winner = None
        if score_a is not None and score_b is not None and score_a != score_b:
            winner = a.team if score_a > score_b else b.team
        third = BracketMatch(match_index=2, team_a=a, team_b=b, score_a=score_a, score_b=score_b, winner=winner)
    return FinalStage(round_count=round_count, third_place_enabled=third_place_enabled,
                      rounds=rounds, third_place_match=third, champion=rounds[-1].matches[0].winner)


def get_bracket_match(stage: FinalStage, round_index: int, match_index: int) -> BracketMatch | None:
    if stage.third_place_match is not None and round_index == stage.round_count and match_index == 2:
        return stage.third_place_match
    if 1 <= round_index <= len(stage.rounds) and 1 <= match_index <= len(stage.rounds[round_index - 1].matches):
        return stage.rounds[round_index - 1].matches[match_index - 1]
    return None


def downstream_matches(round_count: int, round_index: int, match_index: int) -> list[tuple[int, int]]:
    downstream = []
    for index in range(round_index + 1, round_count + 1):
        match_index = (match_index + 1) // 2
        downstream.append((index, match_index))
    return downstream
