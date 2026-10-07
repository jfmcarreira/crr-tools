from app.services.seeding import group_qualification, overall_qualification, seed_order
from .factories import group, standing, team


def test_standard_seed_order():
    assert seed_order(2) == [1, 2]
    assert seed_order(4) == [1, 4, 2, 3]
    assert seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]


def test_group_qualification_crosses_groups():
    a = standing(1, [team(1), team(2)])
    b = standing(2, [team(3, division=group(2, 1)), team(4, division=group(2, 1))])
    result = group_qualification([a, b], 2, 4)
    assert (result.mode, result.qualifiers_per_group, result.qualifier_count) == ("per-group", 2, 4)
    assert [entry.team.id for entry in result.qualifiers] == [1, 3, 2, 4]
    assert [(seed.slot_index, seed.team_id) for seed in result.seeds] == [(1, 1), (2, 4), (3, 3), (4, 2)]


def test_unused_seeds_are_empty():
    result = group_qualification([standing(1, [team(1)]), standing(2, [team(2, division=group(2, 1))])], 1, 4)
    assert [(seed.slot_index, seed.team_id) for seed in result.seeds] == [(1, 1), (2, None), (3, 2), (4, None)]


def test_overall_qualification_compares_groups():
    a = standing(1, [team(1), team(2)])
    b = standing(2, [team(3, division=group(2, 1)), team(4, division=group(2, 1))])
    b.rows[0].points, b.rows[0].goal_difference = 6, 4
    result = overall_qualification([a, b], 2, 4, "standard")
    assert (result.mode, result.qualifiers_per_group, result.qualifier_count) == ("overall", None, 2)
    assert [entry.team.id for entry in result.qualifiers] == [3, 1]
    assert [(seed.slot_index, seed.team_id) for seed in result.seeds] == [(1, 3), (2, None), (3, 1), (4, None)]
