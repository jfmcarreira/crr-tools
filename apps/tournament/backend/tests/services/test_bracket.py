from app.services.bracket import calculate_bracket, downstream_matches
from .factories import team


def test_winners_advance_and_champion_is_selected():
    result = calculate_bracket(2, {value: team(value) for value in range(1, 5)}, {(1, 1): (5, 2), (1, 2): (1, 3), (2, 1): (4, 2)})
    final = result.rounds[1].matches[0]
    assert (final.team_a.team.id, final.team_b.team.id, result.champion.id) == (1, 4, 1)


def test_draw_does_not_advance():
    result = calculate_bracket(1, {1: team(1), 2: team(2)}, {(1, 1): (3, 3)})
    assert result.rounds[0].matches[0].winner is None and result.champion is None


def test_bye_and_empty_branch():
    result = calculate_bracket(2, {1: team(1), 2: None, 3: None, 4: None}, {})
    assert result.rounds[0].matches[0].is_bye
    assert result.rounds[0].matches[0].winner == team(1)
    assert result.rounds[0].matches[1].winner is None
    assert result.rounds[1].matches[0].team_a.team.id == 1
    assert result.rounds[1].matches[0].team_b.pending is False


def test_third_place_uses_semifinal_losers():
    result = calculate_bracket(2, {value: team(value) for value in range(1, 5)}, {(1, 1): (5, 2), (1, 2): (1, 3), (2, 2): (2, 4)}, True)
    match = result.third_place_match
    assert result.third_place_enabled
    assert (match.match_index, match.team_a.team.id, match.team_b.team.id, match.score_a, match.score_b, match.winner.id) == (2, 2, 3, 2, 4, 3)


def test_downstream_results_are_identified():
    assert downstream_matches(4, 1, 3) == [(2, 2), (3, 1), (4, 1)]
