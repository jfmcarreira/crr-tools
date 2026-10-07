"""Execute actual Python services for the legacy deterministic-service assertions."""

import json
import os
import sys

sys.path.insert(0, os.environ["TOURNAMENT_BACKEND"])

from app.schemas.base import Schema
from app.schemas.state import GroupStanding
from app.schemas.teams import TeamSummary
from app.services.bracket import calculate_bracket, downstream_matches
from app.services.calendar import generate_calendar
from app.services.classification import calculate_classification
from app.services.seeding import group_qualification, overall_qualification, seed_order


class MatchScores(Schema):
    team_a: TeamSummary
    team_b: TeamSummary
    score_a: int | None
    score_b: int | None


def serialize(value):
    if isinstance(value, Schema):
        return value.model_dump(by_alias=True)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


def execute(name, args):
    if name == "calendar":
        return generate_calendar([TeamSummary.model_validate(item) for item in args[0]], args[1])
    if name == "classification":
        return calculate_classification([TeamSummary.model_validate(item) for item in args[0]],
                                        [MatchScores.model_validate(item) for item in args[1]],
                                        args[2] if len(args) > 2 else "standard")
    if name == "bracket":
        seeds = {item["slotIndex"]: TeamSummary.model_validate(item["team"]) if item["team"] else None for item in args[1]}
        results = {(item["roundIndex"], item["matchIndex"]): (item["scoreA"], item["scoreB"]) for item in args[2]}
        return calculate_bracket(args[0], seeds, results, args[3] if len(args) > 3 else False)
    if name == "downstream":
        return [{"roundIndex": index, "matchIndex": number} for index, number in downstream_matches(*args)]
    if name == "seed-order":
        return seed_order(args[0])
    standings = [GroupStanding.model_validate(item) for item in args[0]]
    if name == "group-qualification":
        return group_qualification(standings, args[1], args[2])
    if name == "overall-qualification":
        return overall_qualification(standings, args[1], args[2], args[3])
    raise ValueError(f"Unknown service: {name}")


if __name__ == "__main__":
    request = json.load(sys.stdin)
    try:
        response = {"result": serialize(execute(request["name"], request["args"]))}
    except ValueError as error:
        response = {"error": str(error)}
    print(json.dumps(response, ensure_ascii=False))
