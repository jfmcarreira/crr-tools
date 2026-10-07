from app.services.classification import calculate_classification
from .factories import score, team


def test_standard_is_the_default():
    a, b, c = [team(value) for value in (1, 2, 3)]
    matches = [score(a, b, 2, 0), score(c, b, 4, 1)]
    explicit = calculate_classification([a, b, c], matches, "standard")
    assert calculate_classification([a, b, c], matches) == explicit
    assert [(row.team.id, row.points) for row in explicit] == [(3, 3), (1, 3), (2, 0)]


def test_wins_draws_losses_and_incomplete_results():
    a, b, c = [team(value) for value in (1, 2, 3)]
    rows = calculate_classification([a, b, c], [score(a, b, 3, 1), score(a, c, 2, 2), score(b, c, None, None)])
    first = rows[0]
    assert (first.team, first.played, first.wins, first.draws, first.losses,
            first.goals_for, first.goals_against, first.goal_difference, first.points) == (a, 2, 1, 1, 0, 5, 3, 2, 4)
    by_id = {row.team.id: row for row in rows}
    assert (by_id[2].played, by_id[2].losses, by_id[2].points) == (1, 1, 0)
    assert (by_id[3].played, by_id[3].draws, by_id[3].points) == (1, 1, 1)


def test_standard_primary_order():
    a, b, c = [team(value) for value in (1, 2, 3)]
    assert [row.team.id for row in calculate_classification([a, b, c], [score(a, b, 2, 0), score(c, b, 4, 1)])] == [3, 1, 2]


def test_standard_head_to_head():
    a, b, c, d = [team(value) for value in (1, 2, 3, 4)]
    ids = [row.team.id for row in calculate_classification([a, b, c, d], [score(a, b, 1, 0), score(a, c, 0, 1), score(b, d, 1, 0)])]
    assert ids.index(1) < ids.index(2)


def test_standard_team_number_fallback():
    assert [row.team.number for row in calculate_classification([team(10, 9), team(11, 2)], [])] == [2, 9]


def test_total_points_accumulates_scored_totals():
    a, b, c = [team(value) for value in (1, 2, 3)]
    rows = calculate_classification([a, b, c], [score(a, b, 8, 5), score(a, c, 3, 4), score(b, c, 7, 6)], "total-points")
    assert [(row.team.id, row.points) for row in rows] == [(2, 12), (1, 11), (3, 10)]
    row = next(row for row in rows if row.team.id == 1)
    assert (row.played, row.wins, row.draws, row.losses, row.goals_for, row.goals_against, row.goal_difference) == (2, 1, 0, 1, 11, 9, 2)


def test_total_points_uses_direct_match_before_global_difference():
    a, b, c, d = [team(value) for value in (1, 2, 3, 4)]
    rows = calculate_classification([a, b, c, d], [score(a, b, 0, 1), score(a, c, 5, 0), score(b, d, 4, 10)], "total-points")
    assert [row.team.id for row in rows] == [4, 2, 1, 3]
    by_id = {row.team.id: row for row in rows}
    assert (by_id[1].points, by_id[1].goal_difference) == (5, 4)
    assert (by_id[2].points, by_id[2].goal_difference) == (5, -5)


def test_total_points_team_number_fallback():
    rows = calculate_classification([team(10, 9), team(11, 2), team(12, 5)], [], "total-points")
    assert [row.team.number for row in rows] == [2, 5, 9]


def test_total_points_ignores_half_complete_results():
    a, b, c = [team(value) for value in (1, 2, 3)]
    rows = calculate_classification([a, b, c], [score(a, b, 7, 3), score(a, c, 9, None), score(b, c, None, 8)], "total-points")
    assert [(row.team.id, row.played, row.points, row.goals_for) for row in rows] == [(1, 1, 7, 7), (2, 1, 3, 3), (3, 0, 0, 0)]
