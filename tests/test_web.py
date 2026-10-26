import json
import random

import numpy as np
import pandas as pd
import pytest

from sportsml.core.predictor import load_predictor
from sportsml.web import export as export_module
from sportsml.web.build import build
from sportsml.web.export import export, load_snapshots
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
def snapshot(webdata):
    return Snapshot.load(webdata / "toy")


def test_build_writes_snapshot_files(webdata):
    names = {p.name for p in (webdata / "toy").iterdir()}
    assert {"games.csv", "teams.json", "pool.csv", "meta.json", "model"} <= names
    assert "rankings.csv" in names
    meta = json.loads((webdata / "toy" / "meta.json").read_text())
    assert meta["sport"] == "toy" and meta["backtest"]["seasons"] == [2023]


def test_sport_info(snapshot):
    info = snapshot.info()
    assert info["sport"] == "toy" and info["has_spread"]
    assert info["challenge_games"] > 0 and info["date_label"] == "Week"
    assert list(load_snapshots(snapshot.model_dir.rsplit("/", 2)[0])) == ["toy"]


def test_upcoming_games_have_spread_and_prediction(snapshot):
    week = snapshot.upcoming()
    assert (week["season"], week["date"], week["dates"]) == (2024, 12, [12])
    assert len(week["games"]) == 6
    for game in week["games"]:
        assert game["home"]["name"].startswith("Team")
        pred = game["prediction"]
        assert pred["edge"] == pytest.approx(pred["margin"] - game["spread"])
        assert pred["ats_pick"] == ("home" if pred["edge"] > 0 else "away")
        assert 0 < pred["win_prob"] < 1


def test_game_view(snapshot):
    upcoming_id = snapshot.upcoming()["games"][0]["game_id"]
    game = snapshot.game(upcoming_id)
    assert game["result"] is None and game["prediction"] is not None
    home = game["summaries"]["home"]
    assert home["current_season"] and home["games"] == 11
    assert sum(home["record"].values()) == 11
    assert len(home["recent"]) == 5 and {s["key"] for s in game["stats"]} == {
        "points", "allowed", "yards",
    }  # fmt: skip

    past_id = snapshot.pool.index[0]
    past = snapshot.game(past_id)
    assert past["result"]["margin"] is not None
    assert past["prediction"]["margin"] == pytest.approx(
        snapshot.pool.loc[past_id, "pred_margin"]
    )
    assert snapshot.game("nope") is None


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


def test_challenge_hides_the_outcome(snapshot):
    game = snapshot.challenge_next(random.Random(0))
    assert {"result", "prediction", "model"}.isdisjoint(game)
    assert game["game_id"] in snapshot.pool.index and game["spread"] is not None
    # the game itself never appears in either team's recent games
    for side in ("home", "away"):
        recent = game["summaries"][side]["recent"]
        assert game["game_id"] not in {r["game_id"] for r in recent}

    keep = snapshot.pool.index[0]
    exclude = [g for g in snapshot.pool.index if g != keep]
    assert snapshot.challenge_next(random.Random(0), exclude)["game_id"] == keep


@pytest.mark.parametrize("pick", ["home", "away"])
def test_challenge_answer_scores_player_and_model(snapshot, pick):
    game_id = snapshot.pool.index[3]
    row = snapshot.pool.loc[game_id]
    answer = snapshot.challenge_answer(game_id, pick)

    covered = "home" if row["margin"] > row["market_margin"] else "away"
    model_pick = "home" if row["pred_margin"] > row["market_margin"] else "away"
    assert answer["covered"] == covered
    assert answer["correct"] == (pick == covered)
    assert answer["model"]["ats_pick"] == model_pick
    assert answer["model"]["correct"] == (model_pick == covered)
    assert answer["result"]["margin"] == row["margin"]


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


def test_export_refresh_uses_new_results_and_fails_loudly(
    webdata, games, tmp_path, monkeypatch
):
    newer = games.copy()
    late = newer.season.eq(2024) & newer.week.eq(12)
    newer.loc[late, "margin"] = np.where(newer.loc[late, "location"] >= 0, 3, -3)
    monkeypatch.setattr(export_module, "download_games", lambda sport: newer)
    export(data_dir=str(webdata), output_dir=str(tmp_path / "fresh"), refresh=True)
    data = tmp_path / "fresh" / "data"
    (info,) = json.loads((data / "sports.json").read_text())
    assert info["refreshed_at"]
    upcoming = json.loads((data / "toy" / "upcoming.json").read_text())["data"]
    assert upcoming["default"]["games"] == []  # last week is now played

    def broken(sport):
        raise ConnectionError("offline")

    # a failed download fails the run, so the last published site stays up
    monkeypatch.setattr(export_module, "download_games", broken)
    with pytest.raises(ConnectionError):
        export(data_dir=str(webdata), output_dir=str(tmp_path / "x"), refresh=True)
    assert not (tmp_path / "x").exists()


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
    """A snapshot answer as the export writes it: no logos, 6-decimal floats."""
    if isinstance(value, dict):
        return {k: None if k == "logo" else _as_exported(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_exported(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _exported(value):
    """Through JSON first: integer keys (seasons) become strings."""
    return _as_exported(json.loads(json.dumps(value)))


def test_export_matches_the_snapshot(webdata, snapshot, tmp_path):
    export(data_dir=str(webdata), output_dir=str(tmp_path))
    data = tmp_path / "data"
    assert json.loads((data / "sports.json").read_text()) == [snapshot.info()]

    upcoming = _revive(data / "toy" / "upcoming.json")
    assert upcoming["default"] == _exported(snapshot.upcoming())
    for key, week in upcoming["by_date"].items():
        season, date = key.split("-")
        assert week == _exported(snapshot.upcoming(int(season), int(date)))

    games = _revive(data / "toy" / "games.json")
    ids = {g["game_id"] for week in upcoming["by_date"].values() for g in week["games"]}
    assert set(games) == ids
    for game_id, game in games.items():
        assert game == _exported(snapshot.game(game_id))

    challenge = _revive(data / "toy" / "challenge.json")
    assert len(challenge) == snapshot.info()["challenge_games"]
    for entry in challenge[:10]:
        game_id = entry["game"]["game_id"]
        assert entry["game"] == _exported(snapshot.challenge_game(game_id))
        for pick in ("home", "away"):
            # the browser adds the pick-dependent fields (static-api.ts scoreAnswer)
            scored = {
                **entry["answer"],
                "pick": pick,
                "correct": pick == entry["answer"]["covered"],
            }
            assert scored == _exported(snapshot.challenge_answer(game_id, pick))
    assert "logo.png" not in (data / "toy" / "challenge.json").read_text()
    assert _revive(data / "toy" / "rankings.json") == _exported(snapshot.rankings())
    assert _revive(data / "toy" / "performance.json") == _exported(
        snapshot.performance()
    )


def test_rankings_cover_backtest_and_current_season(snapshot, games):
    rankings = snapshot.rankings()
    sources = {s["season"]: s["source"] for s in rankings["seasons"]}
    assert sources == {2024: "current", 2023: "backtest"}
    for season in rankings["seasons"]:
        playing = set(games.loc[games["season"] == season["season"], "team"])
        assert {t["team"]["team"] for t in season["teams"]} == playing
        for i, _ in enumerate(season["dates"]):
            ratings = [t["ratings"][i] for t in season["teams"]]
            # average margin vs every other team: antisymmetric, so they cancel
            assert abs(np.mean(ratings)) < 0.01
    current = next(s for s in rankings["seasons"] if s["source"] == "current")
    upcoming_date = snapshot.upcoming()["date"]
    assert current["dates"][-1] == upcoming_date


def test_performance_summarizes_the_walk_forward_pool(snapshot):
    from sportsml.backtest import summarize

    perf = snapshot.performance()
    results = snapshot.results
    expected = summarize(results, snapshot.schema)["overall"]["model"]
    assert perf["overall"]["model"]["accuracy"] == pytest.approx(expected["accuracy"])
    assert perf["seasons"] == [2023]
    decided = (results.dropna(subset=["market_margin"])["margin"] != 0).sum()
    assert sum(b["n"] for b in perf["calibration"]["model"]) == decided
    assert set(perf["ats_by_season"]) == {2023}


def test_nfl_playoffs_marks_the_last_four():
    from sportsml.web.sports.nfl import playoffs

    rows = [
        # season, game_type, team, result (team's margin)
        (2024, "CON", "KC", 3), (2024, "CON", "BUF", -3),
        (2024, "CON", "PHI", 32), (2024, "CON", "WAS", -32),
        (2024, "SB", "PHI", 18), (2024, "SB", "KC", -18),
        (2024, "DIV", "DET", -14), (2024, "REG", "NYG", -10),
    ]  # fmt: skip
    games = pd.DataFrame(rows, columns=["season", "game_type", "team", "result"])
    assert playoffs(games) == {
        2024: {
            "PHI": "champion",
            "KC": "runner_up",
            "BUF": "semifinal",
            "WAS": "semifinal",
        }
    }


def test_rankings_carry_the_views_playoff_results(webdata, monkeypatch):
    from dataclasses import replace

    from sportsml.web import views

    toy = views.get_view("toy")
    marked = replace(
        toy,
        playoffs=lambda games: {2023: {"T00": "champion", "T01": "runner_up"}},
        playoff_labels={"champion": "Won the final", "runner_up": "Lost the final"},
    )
    monkeypatch.setitem(views._views, "toy", marked)
    rankings = Snapshot.load(webdata / "toy").rankings()
    by_season = {s["season"]: s["playoffs"] for s in rankings["seasons"]}
    assert by_season == {2024: {}, 2023: {"T00": "champion", "T01": "runner_up"}}
    assert rankings["playoff_labels"]["champion"] == "Won the final"
