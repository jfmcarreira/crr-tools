from ..schemas.final_stage import QualifiedTeam, Seed, SeedPreview
from ..schemas.state import GroupStanding


def seed_order(slot_count: int) -> list[int]:
    if type(slot_count) is not int or slot_count < 1 or slot_count & (slot_count - 1):
        raise ValueError("O número de lugares da fase final tem de ser uma potência de dois.")
    if slot_count == 1:
        return [1]
    order, size = [1, 2], 4
    while size <= slot_count:
        order = [value for seed in order for value in (seed, size + 1 - seed)]
        size *= 2
    return order


def preview(qualifiers: list[QualifiedTeam], slot_count: int, mode: str, per_group: int | None) -> SeedPreview:
    if len(qualifiers) > slot_count:
        raise ValueError("Existem mais equipas apuradas do que lugares na fase final.")
    by_seed = {item.seed_number: item.team.id for item in qualifiers}
    return SeedPreview(mode=mode, qualifiers_per_group=per_group, qualifier_count=len(qualifiers),
                       qualifiers=qualifiers, seeds=[Seed(slot_index=index, team_id=by_seed.get(seed))
                                                    for index, seed in enumerate(seed_order(slot_count), 1)])


def group_qualification(standings: list[GroupStanding], per_group: int, slot_count: int) -> SeedPreview:
    if type(per_group) is not int or per_group < 1:
        raise ValueError("O número de apurados por grupo tem de ser positivo.")
    standings = sorted((item for item in standings if item.rows), key=lambda item: (item.group.sort_order, item.group.id))
    qualifiers = []
    for position in range(1, per_group + 1):
        for standing in standings:
            if len(standing.rows) >= position:
                qualifiers.append(QualifiedTeam(seed_number=len(qualifiers) + 1, group_position=position,
                                                team=standing.rows[position - 1].team))
    return preview(qualifiers, slot_count, "per-group", per_group)


def overall_qualification(standings: list[GroupStanding], count: int, slot_count: int, mode: str) -> SeedPreview:
    if type(count) is not int or count < 1:
        raise ValueError("O número total de apurados tem de ser positivo.")
    def key(row):
        return (-row.points, row.team.number) if mode == "total-points" else (-row.points, -row.goal_difference, -row.goals_for, row.team.number)
    rows = sorted((row for standing in standings for row in standing.rows), key=key)
    if count > len(rows):
        raise ValueError("Não existem equipas suficientes para esse número de apurados.")
    qualifiers = [QualifiedTeam(seed_number=index, group_position=row.position, team=row.team)
                  for index, row in enumerate(rows[:count], 1)]
    return preview(qualifiers, slot_count, "overall", None)
