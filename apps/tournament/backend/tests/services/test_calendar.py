from collections import Counter

import pytest

from app.services.calendar import generate_calendar
from .factories import group, team


def test_four_team_rounds():
    games = generate_calendar([team(value) for value in range(1, 5)], 1)
    assert [(game.game_number, game.round_number, game.group.id, game.team_a.id, game.team_b.id) for game in games] == [
        (1, 1, 1, 1, 4), (2, 1, 1, 2, 3), (3, 2, 1, 3, 1),
        (4, 2, 1, 4, 2), (5, 3, 1, 1, 2), (6, 3, 1, 3, 4),
    ]


def test_odd_group_has_byes():
    games = generate_calendar([team(value) for value in range(1, 4)], 1)
    assert [(game.round_number, game.team_a.id, game.team_b.id) for game in games] == [(1, 2, 3), (2, 3, 1), (3, 1, 2)]


def test_groups_are_ordered_and_never_cross_or_duplicate_participants():
    a, b, c = group(1, 0), group(2, 0), group(3, 1)
    teams = [team(21, division=b), team(11, division=a), team(31, division=c),
             team(22, division=b), team(12, division=a), team(32, division=c),
             team(23, division=b), team(13, division=a), team(14, division=a)]
    games = generate_calendar(teams, 1)
    assert [(game.round_number, game.group.id) for game in games] == [
        (1, 1), (1, 1), (1, 2), (1, 3), (2, 1), (2, 1), (2, 2), (3, 1), (3, 1), (3, 2),
    ]
    assert all(game.team_a.group.id == game.group.id == game.team_b.group.id for game in games)
    for number in (1, 2, 3):
        participants = [value for game in games if game.round_number == number for value in (game.team_a.id, game.team_b.id)]
        assert len(participants) == len(set(participants))


def test_second_leg_mirrors_first():
    teams = [team(value) for value in range(1, 5)]
    first, both = generate_calendar(teams, 1), generate_calendar(teams, 2)
    assert both[:6] == first
    assert [(game.game_number, game.round_number, game.team_a.id, game.team_b.id) for game in both[6:]] == [
        (index + 7, game.round_number + 3, game.team_b.id, game.team_a.id) for index, game in enumerate(first)
    ]


def test_every_pair_occurs_once_per_leg():
    teams = [team(value) for value in range(1, 5)]
    for legs in (1, 2):
        counts = Counter(tuple(sorted((game.team_a.id, game.team_b.id))) for game in generate_calendar(teams, legs))
        assert counts == {(1, 2): legs, (1, 3): legs, (1, 4): legs, (2, 3): legs, (2, 4): legs, (3, 4): legs}


def test_inputs_are_not_mutated():
    a, b = group(1, 1), group(2, 0)
    teams = [team(1, division=a), team(4, division=b), team(3, division=a), team(2, division=b)]
    before = [value.model_dump() for value in teams]
    generate_calendar(teams, 2)
    assert [value.model_dump() for value in teams] == before


def test_invalid_legs_are_rejected():
    with pytest.raises(ValueError, match="1 ou 2"):
        generate_calendar([], 3)
