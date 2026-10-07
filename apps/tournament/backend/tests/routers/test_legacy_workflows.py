"""Native equivalents of the nineteen frozen legacy HTTP integration scenarios."""

from copy import deepcopy
from itertools import combinations
import socket
from threading import Thread
import time

import httpx
import uvicorn

from app.main import create_app


def call(client, method, path, payload=None, status=200):
    response = client.request(method, path, json=payload)
    assert response.status_code == status, (method, path, response.text)
    return response.json()


def team(client, number, name=None, group_id=1):
    return call(client, "POST", "/api/admin/teams", {"number": number, "name": name or f"Equipa {number}", "groupId": group_id}, 201)


def teams(client, count=4, group_id=1, offset=0):
    return [team(client, offset + number, group_id=group_id) for number in range(1, count + 1)]


def preview(client, legs=1):
    return call(client, "POST", "/api/admin/calendar/generate-preview", {"legs": legs})


def save(client, generation, confirmed=False):
    return call(client, "POST", "/api/admin/calendar/generate", {"generation": generation, **({"confirmReplace": True} if confirmed else {})})


def schedule(matches):
    return [(match["gameNumber"], match["roundNumber"], match["group"]["id"] if match["group"] else None,
             match["teamA"]["id"], match["teamB"]["id"]) for match in matches]


def pair(match):
    return tuple(sorted((match["teamA"]["id"], match["teamB"]["id"])))


def include(client, number):
    assert call(client, "PUT", f"/api/admin/rounds/{number}/standings", {"countsTowardStandings": True}) == {"roundNumber": number, "countsTowardStandings": True}


def result(client, match, a, b):
    return call(client, "PUT", f"/api/admin/matches/{match['id']}/result", {"scoreA": a, "scoreB": b})


def test_authentication_contract(client):
    assert "error" in call(client, "GET", "/api/admin/teams", status=401)
    assert call(client, "GET", "/api/auth/session") == {"authenticated": False}
    call(client, "POST", "/api/auth/login", {"password": "wrong"}, 401)
    response = client.post("/api/auth/login", json={"password": "migration-fixture-password"})
    assert response.status_code == 200 and response.json() == {"authenticated": True}
    client.headers["cookie"] = f"tournament_admin_session={response.cookies['tournament_admin_session']}"
    assert call(client, "GET", "/api/auth/session") == {"authenticated": True}


def test_deployment_cookie_path(client):
    response = client.post("/api/auth/login", json={"password": "migration-fixture-password"})
    assert response.status_code == 200
    assert "Path=/jogo/" in response.headers["set-cookie"]


def test_display_selection_and_zoom(admin, client):
    assert call(admin, "GET", "/api/public/state")["display"] == {"activePanel": "latest-results", "zoomPercent": 100}
    cookie = admin.headers.pop("cookie")
    call(client, "PUT", "/api/admin/display", {"activePanel": "classification", "zoomPercent": 137}, 401)
    admin.headers["cookie"] = cookie
    call(admin, "PUT", "/api/admin/display", {"activePanel": "unknown-panel", "zoomPercent": 137}, 400)
    call(admin, "PUT", "/api/admin/display", {"activePanel": "classification", "zoomPercent": 401}, 400)
    expected = {"activePanel": "classification", "zoomPercent": 137}
    assert call(admin, "PUT", "/api/admin/display", expected) == expected
    assert call(admin, "GET", "/api/admin/display") == expected
    assert call(admin, "GET", "/api/public/state")["display"] == expected


def test_live_sse_notifies_connected_displays(settings):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error", proxy_headers=False))
    thread = Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
            login = client.post("/api/auth/login", json={"password": "migration-fixture-password"})
            client.headers["cookie"] = f"tournament_admin_session={login.cookies['tournament_admin_session']}"
            with client.stream("GET", "/api/public/events") as response:
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
                assert response.headers["cache-control"] == "no-cache, no-transform"
                lines = response.iter_lines()
                assert next(lines) == "retry: 3000" and next(lines) == ""
                call(client, "PUT", "/api/admin/display", {"activePanel": "classification", "zoomPercent": 137})
                assert next(lines) == "event: state-changed"
                assert next(lines) == 'data: {"type":"state-changed"}'
    finally:
        server.should_exit = True
        thread.join(10)
        listener.close()
        assert not thread.is_alive()


def test_team_creation_global_number_uniqueness_and_group_validation(admin):
    created = team(admin, 10, "Falcons")
    assert created["number"] == 10 and created["name"] == "Falcons" and created["players"] == []
    assert created["group"] == {"id": 1, "name": "Grupo A", "sortOrder": 0}
    group = call(admin, "POST", "/api/admin/groups", {"name": "Grupo B"}, 201)
    assert "error" in call(admin, "POST", "/api/admin/teams", {"number": 10, "name": "Duplicate Falcons", "groupId": group["id"]}, 409)
    moved = call(admin, "PUT", f"/api/admin/teams/{created['id']}", {"number": 10, "name": "Falcons", "groupId": group["id"]})
    assert moved["id"] == created["id"] and moved["group"] == group
    call(admin, "POST", "/api/admin/teams", {"number": 11, "name": "No Group"}, 400)
    call(admin, "POST", "/api/admin/teams", {"number": 11, "name": "Unknown Group", "groupId": 99999}, 404)


def test_automatic_team_numbering(admin):
    first = call(admin, "POST", "/api/admin/teams", {"name": "Primeira", "groupId": 1}, 201)
    second = call(admin, "POST", "/api/admin/teams", {"name": "Segunda", "groupId": 1}, 201)
    assert (first["number"], first["name"], second["number"], second["name"]) == (1, "Primeira", 2, "Segunda")


def test_group_crud_nonempty_and_last_group_rules(admin):
    assert call(admin, "GET", "/api/admin/groups") == [{"id": 1, "name": "Grupo A", "sortOrder": 0}]
    call(admin, "POST", "/api/admin/groups", {"name": "  "}, 400)
    group = call(admin, "POST", "/api/admin/groups", {"name": "Grupo B"}, 201)
    call(admin, "POST", "/api/admin/groups", {"name": "grupo b"}, 409)
    assert call(admin, "PUT", f"/api/admin/groups/{group['id']}", {"name": "Grupo Norte"}) == {**group, "name": "Grupo Norte"}
    call(admin, "DELETE", f"/api/admin/groups/{group['id']}")
    assert call(admin, "DELETE", "/api/admin/groups/1", status=409) == {"error": "Não é possível eliminar o último grupo."}
    call(admin, "POST", "/api/admin/groups", {"name": "Grupo Sul"}, 201)
    team(admin, 1)
    assert call(admin, "DELETE", "/api/admin/groups/1", status=409) == {"error": "Não é possível eliminar um grupo com equipas."}


def test_one_leg_preview_persistence_and_round_participants(admin):
    members = teams(admin)
    generated = preview(admin)
    assert (generated["matchCount"], generated["roundCount"], generated["generation"]["legs"]) == (6, 3, 1)
    order = generated["generation"]["teamOrder"]
    assert sorted(order, key=lambda value: value["teamId"]) == [{"teamId": value["id"], "groupId": 1} for value in members]
    a, b, c, d = [value["teamId"] for value in order]
    assert schedule(generated["matches"]) == [(1, 1, 1, a, d), (2, 1, 1, b, c), (3, 2, 1, c, a), (4, 2, 1, d, b), (5, 3, 1, a, b), (6, 3, 1, c, d)]
    assert sorted(pair(match) for match in generated["matches"]) == sorted(combinations([value["id"] for value in members], 2))
    for number in (1, 2, 3):
        participants = [value[side]["id"] for value in generated["matches"] if value["roundNumber"] == number for side in ("teamA", "teamB")]
        assert len(participants) == len(set(participants))
    saved = save(admin, generated["generation"])
    assert schedule(saved["matches"]) == schedule(generated["matches"])
    assert (saved["matchCount"], saved["roundCount"]) == (6, 3)
    assert all(match["scoreA"] is None and match["scoreB"] is None for match in saved["matches"])
    assert call(admin, "GET", "/api/admin/calendar") == saved


def test_generation_requires_two_teams_in_one_group(admin):
    teams(admin, 1)
    assert call(admin, "POST", "/api/admin/calendar/generate-preview", {"legs": 1}, 409) == {"error": "São necessárias pelo menos duas equipas no mesmo grupo para gerar o calendário."}


def test_round_standings_are_opt_in(admin):
    teams(admin, 2)
    match = save(admin, preview(admin)["generation"])["matches"][0]
    assert not match["countsTowardStandings"]
    scored = result(admin, match, 4, 1)
    assert (scored["id"], scored["scoreA"], scored["scoreB"]) == (match["id"], 4, 1)
    disabled = call(admin, "GET", "/api/public/state")
    assert not disabled["matches"][0]["countsTowardStandings"]
    assert all(row["played"] == 0 and row["points"] == 0 for row in disabled["groupStandings"][0]["rows"])
    include(admin, match["roundNumber"])
    state = call(admin, "GET", "/api/public/state")
    assert state["matches"][0]["countsTowardStandings"]
    winner, loser = state["groupStandings"][0]["rows"]
    assert (winner["position"], winner["team"]["id"], winner["played"], winner["wins"], winner["draws"], winner["losses"], winner["goalsFor"], winner["goalsAgainst"], winner["goalDifference"], winner["points"]) == (1, match["teamA"]["id"], 1, 1, 0, 0, 4, 1, 3, 3)
    assert (loser["position"], loser["team"]["id"], loser["played"], loser["wins"], loser["draws"], loser["losses"], loser["goalsFor"], loser["goalsAgainst"], loser["goalDifference"], loser["points"]) == (2, match["teamB"]["id"], 1, 0, 0, 1, 1, 4, -3, 0)


def test_total_game_points_use_direct_match_tie_breaker(admin):
    a, b, c = teams(admin, 3)
    calendar = save(admin, preview(admin)["generation"])
    for number in {match["roundNumber"] for match in calendar["matches"]}:
        include(admin, number)
    assert call(admin, "PUT", "/api/admin/settings", {"name": "Torneio", "classificationMode": "total-points"})["classificationMode"] == "total-points"
    for participants, scores in [((a, b), {a["id"]: 1, b["id"]: 0}), ((a, c), {a["id"]: 4, c["id"]: 10}), ((b, c), {b["id"]: 5, c["id"]: 0})]:
        match = next(value for value in calendar["matches"] if pair(value) == tuple(sorted(value["id"] for value in participants)))
        result(admin, match, scores[match["teamA"]["id"]], scores[match["teamB"]["id"]])
    state = call(admin, "GET", "/api/public/state")
    assert state["tournament"]["classificationMode"] == "total-points"
    assert [(row["team"]["id"], row["points"], row["goalDifference"]) for row in state["groupStandings"][0]["rows"]] == [(c["id"], 10, 1), (a["id"], 5, -5), (b["id"], 5, 4)]


def test_group_schedules_and_public_classifications_align(admin):
    division = call(admin, "POST", "/api/admin/groups", {"name": "Grupo B"}, 201)
    members = teams(admin, 3) + teams(admin, 2, division["id"], 3)
    generated = preview(admin)
    assert (generated["matchCount"], generated["roundCount"]) == (4, 3)
    assert [match["roundNumber"] for match in generated["matches"]] == [1, 1, 2, 3]
    assert all(match["group"]["id"] == match["teamA"]["group"]["id"] == match["teamB"]["group"]["id"] for match in generated["matches"])
    assert sorted(pair(match) for match in generated["matches"]) == [(1, 2), (1, 3), (2, 3), (4, 5)]
    calendar = save(admin, generated["generation"])
    assert schedule(calendar["matches"]) == schedule(generated["matches"])
    for number in {match["roundNumber"] for match in calendar["matches"]}:
        include(admin, number)
    assert call(admin, "PUT", "/api/admin/teams/1", {"number": 1, "name": "Equipa 1", "groupId": division["id"]}, 409) == {"error": "Não é possível alterar o grupo de uma equipa utilizada no calendário. Limpe ou substitua o calendário primeiro."}
    for match in calendar["matches"]:
        result(admin, match, 2, 0)
    state = call(admin, "GET", "/api/public/state")
    assert state["groups"] == [{"id": 1, "name": "Grupo A", "sortOrder": 0}, division]
    assert schedule(state["matches"]) == schedule(calendar["matches"])
    assert all(match["scoreA"] == 2 and match["scoreB"] == 0 for match in state["matches"])
    for standing in state["groupStandings"]:
        matches = [value for value in state["matches"] if value["group"]["id"] == standing["group"]["id"]]
        assert sorted(row["team"]["id"] for row in standing["rows"]) == sorted(value["id"] for value in members if value["group"]["id"] == standing["group"]["id"])
        for row in standing["rows"]:
            wins = sum(match["teamA"]["id"] == row["team"]["id"] for match in matches)
            losses = sum(match["teamB"]["id"] == row["team"]["id"] for match in matches)
            assert (row["played"], row["wins"], row["draws"], row["losses"], row["goalsFor"], row["goalsAgainst"], row["goalDifference"], row["points"]) == (wins + losses, wins, 0, losses, wins * 2, losses * 2, (wins - losses) * 2, wins * 3)
        assert sum(row["played"] for row in standing["rows"]) == 2 * len(matches)


def test_two_leg_preview_reverses_venues(admin):
    teams(admin)
    generated = preview(admin, 2)
    assert (generated["matchCount"], generated["roundCount"], generated["generation"]["legs"]) == (12, 6, 2)
    assert schedule(generated["matches"][6:]) == [(index + 7, match["roundNumber"] + 3, match["group"]["id"], match["teamB"]["id"], match["teamA"]["id"]) for index, match in enumerate(generated["matches"][:6])]


def test_tampered_and_stale_descriptors_are_rejected(admin):
    teams(admin)
    generated = preview(admin)["generation"]
    tampered = deepcopy(generated)
    tampered["teamOrder"][1] = deepcopy(tampered["teamOrder"][0])
    assert call(admin, "POST", "/api/admin/calendar/generate", {"generation": tampered}, 409) == {"error": "As equipas ou os grupos foram alterados. Sorteie novamente o calendário."}
    team(admin, 5)
    assert call(admin, "POST", "/api/admin/calendar/generate", {"generation": generated}, 409) == {"error": "As equipas foram alteradas. Sorteie novamente o calendário."}


def test_scored_calendar_replacement_requires_confirmation(admin):
    teams(admin)
    first = save(admin, preview(admin)["generation"])["matches"][0]
    result(admin, first, 3, 1)
    replacement = preview(admin)
    assert call(admin, "POST", "/api/admin/calendar/generate", {"generation": replacement["generation"]}, 409) == {"error": "Já existem resultados registados. Confirme a substituição do calendário para eliminar esses resultados."}
    persisted = next(match for match in call(admin, "GET", "/api/admin/calendar")["matches"] if match["id"] == first["id"])
    assert (persisted["scoreA"], persisted["scoreB"]) == (3, 1)
    replaced = save(admin, replacement["generation"], True)
    assert schedule(replaced["matches"]) == schedule(replacement["matches"])
    assert all(match["scoreA"] is None and match["scoreB"] is None for match in replaced["matches"])


def test_randomization_preserves_ids_numbers_and_balances_groups(admin):
    division = call(admin, "POST", "/api/admin/groups", {"name": "Grupo B"}, 201)
    members = [team(admin, number) for number in (11, 24, 37)]
    assert save(admin, preview(admin)["generation"])["matches"]
    call(admin, "POST", "/api/admin/teams/randomize", {}, 409)
    randomized = call(admin, "POST", "/api/admin/teams/randomize", {"confirm": True})
    assert randomized["calendarCleared"]
    assert sorted(value["number"] for value in randomized["teams"]) == [11, 24, 37]
    assert sorted(value["id"] for value in randomized["teams"]) == sorted(value["id"] for value in members)
    assert {value["group"]["id"] for value in randomized["teams"]} == {1, division["id"]}
    assert abs(sum(value["group"]["id"] == 1 for value in randomized["teams"]) - sum(value["group"]["id"] == division["id"] for value in randomized["teams"])) <= 1
    assert call(admin, "GET", "/api/admin/calendar")["matches"] == []


def test_final_stage_advancement_third_place_invalidation_and_clear(admin):
    members = teams(admin)
    assert call(admin, "PUT", "/api/admin/final-stage/config", {"roundCount": 1, "thirdPlaceEnabled": True}, 400) == {"error": "O jogo do 3.º lugar requer pelo menos duas rondas."}
    configured = call(admin, "PUT", "/api/admin/final-stage/config", {"roundCount": 2, "thirdPlaceEnabled": True})
    assert configured["roundCount"] == 2 and configured["thirdPlaceEnabled"] and configured["champion"] is None
    assert [(row["roundIndex"], row["name"], len(row["matches"])) for row in configured["rounds"]] == [(1, "Meias-finais", 2), (2, "Final", 1)]
    seeded = call(admin, "PUT", "/api/admin/final-stage/seeds", {"seeds": [{"slotIndex": index + 1, "teamId": value["id"]} for index, value in enumerate(members)]})
    assert [(match["teamA"]["team"]["id"], match["teamB"]["team"]["id"]) for match in seeded["rounds"][0]["matches"]] == [(1, 2), (3, 4)]
    def final_result(round_number, match_number, a, b):
        return call(admin, "PUT", f"/api/admin/final-stage/matches/{round_number}/{match_number}/result", {"scoreA": a, "scoreB": b})
    first = final_result(1, 1, 3, 1)["rounds"][1]["matches"][0]
    assert first["teamA"]["team"]["id"] == 1 and first["teamA"]["pending"] is False
    assert first["teamB"] == {"team": None, "pending": True}
    second = final_result(1, 2, 1, 3)["rounds"][1]["matches"][0]
    assert (second["teamA"]["team"]["id"], second["teamB"]["team"]["id"]) == (1, 4)
    third = final_result(2, 2, 1, 3)["thirdPlaceMatch"]
    assert (third["teamA"]["team"]["id"], third["teamB"]["team"]["id"], third["scoreA"], third["scoreB"], third["winner"]["id"]) == (2, 3, 1, 3, 3)
    completed = final_result(2, 1, 2, 1)
    assert completed["champion"] == {key: value for key, value in members[0].items() if key != "players"}
    assert call(admin, "GET", "/api/public/state")["finalStage"] == completed
    corrected = final_result(1, 1, 1, 3)
    assert corrected["champion"] is None and corrected["rounds"][0]["matches"][0]["winner"]["id"] == 2
    match = corrected["rounds"][1]["matches"][0]
    assert (match["teamA"]["team"]["id"], match["teamB"]["team"]["id"], match["scoreA"], match["scoreB"], match["winner"]) == (2, 4, None, None, None)
    match = corrected["thirdPlaceMatch"]
    assert (match["teamA"]["team"]["id"], match["teamB"]["team"]["id"], match["scoreA"], match["scoreB"], match["winner"]) == (1, 3, None, None, None)
    assert call(admin, "GET", "/api/public/state")["finalStage"]["champion"] is None
    call(admin, "DELETE", "/api/admin/final-stage/config", {}, 409)
    expected = {"roundCount": None, "thirdPlaceEnabled": False, "rounds": [], "thirdPlaceMatch": None, "champion": None}
    assert call(admin, "DELETE", "/api/admin/final-stage/config", {"confirm": True}) == expected
    assert call(admin, "GET", "/api/public/state")["finalStage"] == expected


def test_next_match_panel(admin):
    expected = {"activePanel": "next-match", "zoomPercent": 100}
    assert call(admin, "PUT", "/api/admin/display", expected) == expected
    assert call(admin, "GET", "/api/public/state")["display"]["activePanel"] == "next-match"


def test_automatic_group_and_overall_qualification(admin):
    division = call(admin, "POST", "/api/admin/groups", {"name": "Grupo B"}, 201)
    a1, a2 = teams(admin, 2)
    b1, b2 = teams(admin, 2, division["id"], 2)
    calendar = save(admin, preview(admin)["generation"])
    for number in {match["roundNumber"] for match in calendar["matches"]}:
        include(admin, number)
    for match in calendar["matches"]:
        winner = a1["id"] if match["group"]["id"] == 1 else b1["id"]
        result(admin, match, 3 if match["teamA"]["id"] == winner else 1, 3 if match["teamB"]["id"] == winner else 1)
    call(admin, "PUT", "/api/admin/final-stage/config", {"roundCount": 2, "thirdPlaceEnabled": False})
    selected = call(admin, "POST", "/api/admin/final-stage/auto-seed-preview", {"mode": "per-group", "qualifiersPerGroup": 2})
    assert (selected["mode"], selected["qualifiersPerGroup"], selected["qualifierCount"]) == ("per-group", 2, 4)
    assert [(value["seedNumber"], value["groupPosition"], value["team"]["id"]) for value in selected["qualifiers"]] == [(1, 1, a1["id"]), (2, 1, b1["id"]), (3, 2, a2["id"]), (4, 2, b2["id"])]
    assert selected["seeds"] == [{"slotIndex": 1, "teamId": a1["id"]}, {"slotIndex": 2, "teamId": b2["id"]}, {"slotIndex": 3, "teamId": b1["id"]}, {"slotIndex": 4, "teamId": a2["id"]}]
    call(admin, "POST", "/api/admin/final-stage/auto-seed-preview", {"mode": "per-group", "qualifiersPerGroup": 3}, 400)
    overall = call(admin, "POST", "/api/admin/final-stage/auto-seed-preview", {"mode": "overall", "qualifierCount": 2})
    assert (overall["mode"], overall["qualifiersPerGroup"], overall["qualifierCount"]) == ("overall", None, 2)
    assert [(value["seedNumber"], value["team"]["id"]) for value in overall["qualifiers"]] == [(1, a1["id"]), (2, b1["id"])]
    assert overall["seeds"] == [{"slotIndex": 1, "teamId": a1["id"]}, {"slotIndex": 2, "teamId": None}, {"slotIndex": 3, "teamId": b1["id"]}, {"slotIndex": 4, "teamId": None}]
