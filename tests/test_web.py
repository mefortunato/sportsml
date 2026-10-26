import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sportsml.core.predictor import load_predictor
from sportsml.web.api import SnapshotStore
from sportsml.web.app import create_app, load_store
from sportsml.web.build import build
from sportsml.web.export import export
from sportsml.web.refresh import refresh_sport
from sportsml.web.snapshot import Snapshot, cover_side

from .conftest import make_games


@pytest.fixture(scope="module")
def games():
    return make_games(persistence=0.7)


@pytest.fixture(scope="module")
def webdata(games, tmp_path_factory):
    out = tmp_path_factory.mktemp("webdata")
    build(sports=["toy"], output_dir=str(out), games=games, backtest_seasons=1,
          max_epochs=2)  # fmt: skip
    return out


@pytest.fixture(scope="module")
def client(webdata, tmp_path_factory):
    static = tmp_path_factory.mktemp("static")
    (static / "index.html").write_text("<html>app shell</html>")
    (static / "app.js").write_text("console.log(1)")
    app = create_app(webdata, static, refresh=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def snapshot(client):
    return client.app.state.store.get("toy")


def test_build_writes_snapshot_files(webdata):
    names = {p.name for p in (webdata / "toy").iterdir()}
    assert {"games.csv", "teams.json", "pool.csv", "meta.json", "model"} <= names
    meta = json.loads((webdata / "toy" / "meta.json").read_text())
    assert meta["sport"] == "toy" and meta["backtest"]["seasons"] == [2023]


def test_sports_list(client):
    (info,) = client.get("/api/sports").json()
    assert info["sport"] == "toy" and info["has_spread"]
    assert info["challenge_games"] > 0 and info["date_label"] == "Week"


def test_upcoming_games_have_spread_and_prediction(client):
    week = client.get("/api/toy/upcoming").json()
    assert (week["season"], week["date"], week["dates"]) == (2024, 12, [12])
    assert len(week["games"]) == 6
    for game in week["games"]:
        assert game["home"]["name"].startswith("Team")
        pred = game["prediction"]
        assert pred["edge"] == pytest.approx(pred["margin"] - game["spread"])
        assert pred["ats_pick"] == ("home" if pred["edge"] > 0 else "away")
        assert 0 < pred["win_prob"] < 1


def test_game_view(client, snapshot):
    upcoming_id = client.get("/api/toy/upcoming").json()["games"][0]["game_id"]
    game = client.get(f"/api/toy/games/{upcoming_id}").json()
    assert game["result"] is None and game["prediction"] is not None
    home = game["summaries"]["home"]
    assert home["current_season"] and home["games"] == 11
    assert sum(home["record"].values()) == 11
    assert len(home["recent"]) == 5 and {s["key"] for s in game["stats"]} == {
        "points", "allowed", "yards",
    }  # fmt: skip

    past_id = snapshot.pool.index[0]
    past = client.get(f"/api/toy/games/{past_id}").json()
    assert past["result"]["margin"] is not None
    assert past["prediction"]["margin"] == pytest.approx(
        snapshot.pool.loc[past_id, "pred_margin"]
    )
    assert client.get("/api/toy/games/nope").status_code == 404


def test_summaries_only_use_earlier_games(snapshot, games, webdata):
    cut = games[(games.season < 2024) | (games.week < 6)]
    earlier = Snapshot(
        snapshot.view,
        cut,
        load_predictor(str(webdata / "toy" / "model")),
        snapshot.pool.reset_index(),
        pd.DataFrame(list(snapshot.teams.values())),
    )
    for team in ("T00", "T05"):
        assert snapshot.team_summary(team, 2024, 6) == earlier.team_summary(
            team, 2024, 6
        )


def test_season_opener_falls_back_to_last_season(snapshot):
    summary = snapshot.team_summary("T00", 2024, 1)
    assert summary["season"] == 2023 and not summary["current_season"]
    assert summary["games"] == 12


def test_challenge_hides_the_outcome(client, snapshot):
    game = client.get("/api/toy/challenge/next").json()
    assert {"result", "prediction", "model"}.isdisjoint(game)
    assert game["game_id"] in snapshot.pool.index and game["spread"] is not None
    # the game itself never appears in either team's recent games
    for side in ("home", "away"):
        recent = game["summaries"][side]["recent"]
        assert game["game_id"] not in {r["game_id"] for r in recent}

    keep = snapshot.pool.index[0]
    exclude = [g for g in snapshot.pool.index if g != keep]
    again = client.get("/api/toy/challenge/next", params={"exclude": exclude})
    assert again.json()["game_id"] == keep


@pytest.mark.parametrize("pick", ["home", "away"])
def test_challenge_answer_scores_player_and_model(client, snapshot, pick):
    game_id = snapshot.pool.index[3]
    row = snapshot.pool.loc[game_id]
    answer = client.post(f"/api/toy/challenge/{game_id}", json={"pick": pick}).json()

    covered = "home" if row["margin"] > row["market_margin"] else "away"
    model_pick = "home" if row["pred_margin"] > row["market_margin"] else "away"
    assert answer["covered"] == covered
    assert answer["correct"] == (pick == covered)
    assert answer["model"]["ats_pick"] == model_pick
    assert answer["model"]["correct"] == (model_pick == covered)
    assert answer["result"]["margin"] == row["margin"]

    bad = client.post(f"/api/toy/challenge/{game_id}", json={"pick": "draw"})
    assert bad.status_code == 422


def test_pushes_are_left_out_of_the_pool(snapshot):
    pool = snapshot.pool.reset_index()
    pushed = pool.iloc[:1].assign(game_id="push", margin=3.0, market_margin=3.0)
    rebuilt = Snapshot(
        snapshot.view,
        snapshot.games,
        load_predictor(snapshot.model_dir),
        pd.concat([pool, pushed]),
        pd.DataFrame(list(snapshot.teams.values())),
    )
    assert "push" not in rebuilt.pool.index
    assert cover_side(3, 3.0) == "push" and cover_side(4, 3.5) == "home"


def test_frontend_routes_fall_back_to_the_app_shell(client):
    assert client.get("/").text == "<html>app shell</html>"
    assert client.get("/toy/games/2024_01_0_1").text == "<html>app shell</html>"
    assert client.get("/app.js").text == "console.log(1)"
    missing = client.get("/api/does/not/exist")
    assert missing.status_code == 404 and "detail" in missing.json()


def test_refresh_replaces_snapshot_and_survives_errors(webdata, games):
    store = load_store(webdata)
    before = store.get("toy")

    newer = games.copy()
    late = newer.season.eq(2024) & newer.week.eq(12)
    newer.loc[late, "margin"] = np.where(newer.loc[late, "location"] >= 0, 3, -3)
    assert refresh_sport(store, "toy", download=lambda sport: newer)
    after = store.get("toy")
    assert after is not before and after.meta["refreshed_at"]
    assert after.upcoming()["games"] == []  # last week is now played

    def broken(sport):
        raise ConnectionError("offline")

    assert not refresh_sport(store, "toy", download=broken)
    assert store.get("toy") is after


def test_unknown_sport(client):
    assert client.get("/api/nba/upcoming").status_code == 404
    assert isinstance(SnapshotStore().snapshots, dict)


def _revive(path):
    payload = json.loads(path.read_text())

    def resolve(value):
        if isinstance(value, dict):
            if "$team" in value:
                return payload["teams"][value["$team"]]
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return resolve(payload["data"])


def _as_exported(value):
    """An API response as the export writes it: no logos, 4-decimal floats."""
    if isinstance(value, dict):
        return {k: None if k == "logo" else _as_exported(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_exported(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def test_export_matches_the_api(webdata, client, tmp_path):
    export(data_dir=str(webdata), output_dir=str(tmp_path))
    data = tmp_path / "data"
    assert (
        json.loads((data / "sports.json").read_text())
        == client.get("/api/sports").json()
    )

    upcoming = _revive(data / "toy" / "upcoming.json")
    assert upcoming["default"] == _as_exported(client.get("/api/toy/upcoming").json())
    for key, week in upcoming["by_date"].items():
        season, date = key.split("-")
        api = client.get(f"/api/toy/upcoming?season={season}&date={date}").json()
        assert week == _as_exported(api)

    games = _revive(data / "toy" / "games.json")
    ids = {g["game_id"] for week in upcoming["by_date"].values() for g in week["games"]}
    assert set(games) == ids
    for game_id, game in games.items():
        assert game == _as_exported(client.get(f"/api/toy/games/{game_id}").json())

    challenge = _revive(data / "toy" / "challenge.json")
    assert len(challenge) == client.get("/api/toy").json()["challenge_games"]
    for entry in challenge[:10]:
        game_id = entry["game"]["game_id"]
        for pick in ("home", "away"):
            api = client.post(
                f"/api/toy/challenge/{game_id}", json={"pick": pick}
            ).json()
            # the client adds the pick-dependent fields (static-api.ts scoreAnswer)
            scored = {
                **entry["answer"],
                "pick": pick,
                "correct": pick == entry["answer"]["covered"],
            }
            assert scored == _as_exported(api)
    assert "logo.png" not in (data / "toy" / "challenge.json").read_text()
