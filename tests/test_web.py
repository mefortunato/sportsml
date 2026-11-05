import dataclasses
import json
import random

import numpy as np
import pandas as pd
import pytest

from sportsml.core.predictor import load_predictor
from sportsml.web import export as export_module
from sportsml.web.build import build
from sportsml.web.export import export, load_snapshots, refresh_snapshots
from sportsml.web.snapshot import Snapshot, cover_side

from .conftest import TOY_SCHEMA, make_games


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


def test_games_whose_kickoff_day_has_passed_are_not_upcoming(snapshot, monkeypatch):
    """A game still missing its result (in progress at download, or a late
    refresh) leaves the upcoming page once its day is over."""
    from sportsml.web import snapshot as snapshot_module

    ids = [g["game_id"] for g in snapshot.upcoming()["games"]]
    yesterday = set(ids[:2])

    def kickoff(row):
        played = str(row["game_id"]) in yesterday
        return "2026-10-27 19:30" if played else "2026-10-31"

    monkeypatch.setattr(snapshot_module, "_today_eastern", lambda: "2026-10-28")
    view = dataclasses.replace(snapshot.view, kickoff=kickoff)
    teams = pd.DataFrame(list(snapshot.teams.values()))
    predictor = load_predictor(snapshot.model_dir)
    later = Snapshot(
        view, snapshot.games, predictor, snapshot.results, teams, snapshot.meta
    )
    week = later.upcoming()
    assert [g["game_id"] for g in week["games"]] == ids[2:]
    assert later.game(ids[0])["prediction"] is None


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


def test_recent_games_are_the_last_played_dates_newest_first(snapshot):
    dates = snapshot.recent_dates()
    assert [(d["season"], d["date"]) for d in dates] == [
        (2024, 11), (2024, 10), (2024, 9), (2024, 8),
    ]  # fmt: skip
    day = snapshot.recent()
    assert (day["season"], day["date"]) == (2024, 11)
    assert len(day["games"]) == 6
    for game in day["games"]:
        result, pred = game["result"], game["prediction"]
        assert result["margin"] is not None and result["covered"] is not None
        # the current season is not backtested: replayed
        assert game["prediction_source"] == "replay"
        assert pred["edge"] == pytest.approx(pred["margin"] - game["spread"])
        assert 0 < pred["win_prob"] < 1
    assert snapshot.recent(2024, 8)["games"][0]["date"] == 8


def test_recent_replays_use_only_earlier_games(snapshot, games, webdata):
    """A replayed prediction is the one the model made before the date:
    later results (here, everything after week 9) do not change it."""
    cut = games[(games.season < 2024) | (games.week <= 9)]
    earlier = Snapshot(
        snapshot.view,
        cut,
        load_predictor(str(webdata / "toy" / "model")),
        snapshot.pool.reset_index(),
        pd.DataFrame(list(snapshot.teams.values())),
    )
    assert earlier.recent_dates()[0]["date"] == 9
    for game in earlier.recent(2024, 9)["games"]:
        now = snapshot.game(game["game_id"])
        assert now["prediction"]["margin"] == pytest.approx(
            game["prediction"]["margin"], abs=1e-5
        )


def test_recent_games_from_the_backtest_keep_its_predictions(snapshot, webdata):
    view = dataclasses.replace(snapshot.view, recent_dates=200)
    full = Snapshot(
        view,
        snapshot.games,
        load_predictor(str(webdata / "toy" / "model")),
        snapshot.results,
        pd.DataFrame(list(snapshot.teams.values())),
    )
    tested = [
        g
        for d in full.recent_dates()
        if d["season"] == 2023
        for g in full.recent(d["season"], d["date"])["games"]
    ]
    assert tested and {g["prediction_source"] for g in tested} == {"backtest"}
    results = snapshot.results.set_index("game_id")
    for game in tested[:5]:
        assert game["prediction"]["margin"] == pytest.approx(
            results.loc[game["game_id"], "pred_margin"]
        )


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

    playable = [g for g in snapshot.pool.index if "spread" in snapshot.markets(g)]
    keep = playable[0]
    exclude = [g for g in snapshot.pool.index if g != keep]
    assert snapshot.challenge_next(random.Random(0), exclude)["game_id"] == keep
    # every market draws only games it can be played on
    for market in ("spread", "moneyline", "total"):
        game = snapshot.challenge_next(random.Random(1), market=market)
        assert market in game["markets"]
        assert {"moneyline", "total_line", "total_odds"} <= set(game)


def test_info_lists_the_challenge_markets(snapshot):
    assert snapshot.info()["markets"] == ["spread", "moneyline", "total"]


@pytest.mark.parametrize("pick", ["home", "away"])
def test_challenge_answer_scores_player_and_model_on_the_spread(snapshot, pick):
    game_id = next(g for g in snapshot.pool.index if "spread" in snapshot.markets(g))
    row = snapshot.pool.loc[game_id]
    answer = snapshot.challenge_answer(game_id, pick)

    covered = "home" if row["margin"] > row["market_margin"] else "away"
    model_pick = "home" if row["pred_margin"] > row["market_margin"] else "away"
    assert answer["covered"] == answer["outcome"] == covered
    assert answer["correct"] == (pick == covered)
    assert answer["units"] == pytest.approx(100 / 110 if pick == covered else -1)
    assert answer["model"]["ats_pick"] == answer["model"]["pick"] == model_pick
    assert answer["model"]["correct"] == (model_pick == covered)
    assert answer["result"]["margin"] == row["margin"]


@pytest.mark.parametrize("pick", ["home", "away"])
def test_moneyline_answer_pays_the_posted_odds(snapshot, pick):
    from sportsml.backtest import no_vig_probability

    game_id = next(g for g in snapshot.pool.index if "moneyline" in snapshot.markets(g))
    row = snapshot.pool.loc[game_id]
    answer = snapshot.challenge_answer(game_id, pick, market="moneyline")
    winner = "home" if row["margin"] > 0 else "away"
    assert answer["outcome"] == winner
    odds = {"home": row["moneyline"], "away": row["opp_moneyline"]}[pick]
    win = odds / 100 if odds > 0 else 100 / -odds
    assert answer["units"] == pytest.approx(win if pick == winner else -1)
    # the model takes the side it rates above the market's no-vig odds
    market = no_vig_probability(row["moneyline"], row["opp_moneyline"])
    value = "home" if row["win_prob"] > market else "away"
    assert answer["model"]["pick"] == answer["model"]["ml_pick"] == value
    assert answer["model"]["market_prob"] == pytest.approx(market)


@pytest.mark.parametrize("pick", ["over", "under"])
def test_total_answer_scores_over_and_under(snapshot, pick):
    game_id = next(g for g in snapshot.pool.index if "total" in snapshot.markets(g))
    row = snapshot.pool.loc[game_id]
    answer = snapshot.challenge_answer(game_id, pick, market="total")
    went = "over" if row["total"] > row["total_line"] else "under"
    assert answer["outcome"] == answer["result"]["went"] == went
    assert answer["correct"] == (pick == went)
    model = "over" if row["pred_total"] > row["total_line"] else "under"
    assert answer["model"]["pick"] == answer["model"]["ou_pick"] == model
    assert answer["model"]["total"] == pytest.approx(row["pred_total"])
    with pytest.raises(LookupError):
        snapshot.challenge_answer(game_id, pick, market="parlay")


def test_a_push_is_only_unplayable_on_its_own_market(snapshot):
    pool = snapshot.pool.reset_index()
    game_id = pool.loc[0, "game_id"]
    games = snapshot.games.copy()
    rows = games["game_id"] == game_id
    # land the home team's margin exactly on the spread (both perspectives)
    spread = games.loc[rows, "spread"]
    games.loc[rows, "margin"] = spread.round()
    games.loc[rows, "spread"] = spread.round()
    home = rows & (games["team"] == pool.loc[0, "team"])
    pool.loc[0, "market_margin"] = games.loc[home, "spread"].iloc[0]
    rebuilt = Snapshot(
        snapshot.view,
        games,
        load_predictor(snapshot.model_dir),
        pool,
        pd.DataFrame(list(snapshot.teams.values())),
    )
    markets = rebuilt.markets(game_id)
    assert "spread" not in markets and "moneyline" in markets
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


def test_a_failed_refresh_keeps_that_sports_built_data(monkeypatch):
    class Snap:
        def refreshed(self, games):
            return games

    def download(sport):
        if sport == "cfb":
            raise ConnectionError("429 Too Many Requests")
        return f"{sport} fresh"

    monkeypatch.setattr(export_module, "download_games", download)
    cfb, nba = Snap(), Snap()
    assert refresh_snapshots({"cfb": cfb, "nba": nba}) == {
        "cfb": cfb,
        "nba": "nba fresh",
    }
    with pytest.raises(ConnectionError):
        refresh_snapshots({"cfb": cfb})


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

    recent = _revive(data / "toy" / "recent.json")
    assert recent["dates"] == _exported(snapshot.recent_dates())
    for key, day in recent["by_date"].items():
        season, date = key.split("-")
        assert day == _exported(snapshot.recent(int(season), int(date))["games"])
    recent_games = _revive(data / "toy" / "recent_games.json")
    assert set(recent_games) == {
        g["game_id"] for d in recent["by_date"].values() for g in d
    }
    for game_id, game in recent_games.items():
        assert game == _exported(snapshot.game(game_id))
        assert game["result"] is not None and game["prediction"] is not None

    index = _revive(data / "toy" / "challenge" / "index.json")
    shards = sorted({shard for _, shard, _ in index["games"]})
    challenge = [
        entry
        for shard in shards
        for entry in _revive(data / "toy" / "challenge" / f"{shard}.json")
    ]
    assert len(challenge) == snapshot.info()["challenge_games"]
    assert [e["game"]["game_id"] for e in challenge] == [
        g for g, _, _ in index["games"]
    ]
    for entry, (_, _, markets) in zip(challenge, index["games"]):
        assert markets == list(entry["answers"])
    for entry in challenge[:10]:
        game_id = entry["game"]["game_id"]
        assert entry["game"] == _exported(snapshot.challenge_game(game_id))
        assert set(entry["answers"]) == set(entry["game"]["markets"])
        for market, answer in entry["answers"].items():
            for pick in answer["odds"]:
                # the browser adds the pick-dependent fields (api.ts scoreAnswer)
                correct = pick == answer["outcome"]
                odds = answer["odds"][pick]
                scored = {
                    **answer,
                    "pick": pick,
                    "correct": correct,
                    "units": (odds / 100 if odds > 0 else 100 / -odds)
                    if correct
                    else -1.0,
                }
                expected = snapshot.challenge_answer(game_id, pick, market)
                assert _as_exported(scored) == _exported(expected)
    assert "logo.png" not in (data / "toy" / "challenge" / "0.json").read_text()
    assert _revive(data / "toy" / "rankings.json") == _exported(snapshot.rankings())
    assert _revive(data / "toy" / "performance.json") == _exported(
        snapshot.performance()
    )


def test_challenge_shards_carry_only_their_own_teams(tmp_path):
    from sportsml.web.export import write_challenge

    def entry(game_id, home, away):
        game = {"game_id": game_id, "home": TEAMS[home], "away": TEAMS[away]}
        return {"game": game, "answers": {"spread": {"outcome": "home"}}}

    TEAMS = {k: {"team": k, "name": k} for k in "ABCD"}
    pool = [entry("1", "A", "B"), entry("2", "C", "A"), entry("3", "D", "C")]
    (tmp_path / "challenge.json").write_text("stale")
    write_challenge(tmp_path, pool, TEAMS, shard_size=2)

    assert not (tmp_path / "challenge.json").exists()
    index = json.loads((tmp_path / "challenge" / "index.json").read_text())["data"]
    assert index["games"] == [
        ["1", 0, ["spread"]],
        ["2", 0, ["spread"]],
        ["3", 1, ["spread"]],
    ]
    shard = json.loads((tmp_path / "challenge" / "1.json").read_text())
    assert set(shard["teams"]) == {"C", "D"}
    assert shard["data"][0]["game"]["home"] == {"$team": "D"}
    # a smaller re-export leaves no stale shards behind
    write_challenge(tmp_path, pool[:1], TEAMS, shard_size=2)
    assert sorted(p.name for p in (tmp_path / "challenge").iterdir()) == [
        "0.json",
        "index.json",
    ]


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


def test_team_map_lays_out_the_latest_seasons_teams(snapshot, games):
    team_map = snapshot.rankings()["map"]
    current = next(
        s for s in snapshot.rankings()["seasons"] if s["source"] == "current"
    )
    assert (team_map["season"], team_map["date"]) == (2024, current["dates"][-1])
    playing = set(games.loc[games["season"] == 2024, "team"])
    assert {p["team"]["team"] for p in team_map["points"]} == playing
    latest = {t["team"]["team"]: t["ratings"][-1] for t in current["teams"]}
    for point in team_map["points"]:
        assert -1 <= point["x"] <= 1 and -1 <= point["y"] <= 1
        assert point["rating"] == pytest.approx(latest[point["team"]["team"]])
    # a fixed seed: the same layout on every export
    from sportsml.web.snapshot import umap_2d

    vectors = np.random.default_rng(0).normal(size=(12, 8)).astype(np.float32)
    np.testing.assert_allclose(umap_2d(vectors), umap_2d(vectors))


def test_a_date_in_progress_is_ranked_once(snapshot):
    """Some of the next date's games already played (a week in progress):
    that date is both played and upcoming, and gets one rating per team."""
    s = snapshot.schema
    games = snapshot.games.copy()
    week = games[games[s.target].isna()][s.date].min()
    first = games.index[(games[s.date] == week) & games[s.target].isna()][:2]
    games.loc[first, s.target] = 3.0
    games.loc[first, s.total] = 40.0
    later = snapshot.refreshed(games)
    table = later.rankings_table
    current = table[table["season"] == table["season"].max()]
    assert not current.duplicated(["date", "team"]).any()
    assert later.rankings()["map"]["date"] == week


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


def test_performance_and_games_cover_every_market(snapshot):
    perf = snapshot.performance()
    assert {"ats", "moneyline", "totals"} <= set(perf)
    assert set(perf["moneyline_by_season"]) == set(perf["totals_by_season"]) == {2023}
    assert {"model", "market"} == set(perf["over_calibration"])
    decided = sum(b["n"] for b in perf["over_calibration"]["model"])
    assert decided == perf["totals"]["n"] - sum(
        r["pushes"] for r in perf["totals"]["record"][:1]
    )

    game = snapshot.upcoming()["games"][0]
    assert game["total_line"] is not None and game["moneyline"] is not None
    pred = game["prediction"]
    assert pred["total_edge"] == pytest.approx(pred["total"] - game["total_line"])
    assert pred["ou_pick"] == ("over" if pred["total_edge"] > 0 else "under")
    assert pred["ml_edge"] == pytest.approx(pred["win_prob"] - pred["market_prob"])
    played = snapshot.game(snapshot.pool.index[0])
    result = played["result"]
    assert result["total"] == result["home_score"] + result["away_score"]
    assert result["winner"] in ("home", "away", "push")


def test_info_carries_what_the_browser_prices_lines_with(snapshot):
    pricing = snapshot.info()["pricing"]
    assert pricing["sigma"] == pytest.approx(snapshot.sigma)
    assert pricing["total_sigma"] > 0
    assert set(pricing["trust"]) == {"spread", "moneyline", "total"}
    assert all(0 <= k <= 1 for k in pricing["trust"].values())


def test_trust_is_the_brier_optimal_shrink_toward_the_market():
    import dataclasses

    from sportsml.web.snapshot import Snapshot

    # disagreements that are right half as often as the model claims
    rng = np.random.default_rng(0)
    n = 20000
    market = rng.uniform(0.3, 0.7, n)
    model = np.clip(market + rng.normal(0, 0.1, n), 0.01, 0.99)
    truth = market + 0.5 * (model - market)
    won = rng.random(n) < truth
    results = pd.DataFrame(
        {"margin": np.where(won, 3.0, -3.0), "win_prob": model, "market_prob": market}
    )
    fake = object.__new__(Snapshot)
    fake.schema = dataclasses.replace(TOY_SCHEMA, market_spread=None)
    fake.results, fake.total_sigma, fake.sigma = results, None, 13.0
    assert fake._trust()["moneyline"] == pytest.approx(0.5, abs=0.05)


def test_nba_playoffs_come_from_the_bracket():
    from sportsml.web.sports.nba import playoffs

    rows = [
        # season, day, team, opp_team, result (team's margin)
        (2025, 200, "BOS", "MIA", 9), (2025, 200, "MIA", "BOS", -9),  # 1st round
        (2025, 220, "BOS", "NYK", -4), (2025, 220, "NYK", "BOS", 4),
        (2025, 221, "OKC", "MIN", 12), (2025, 221, "MIN", "OKC", -12),
        (2025, 230, "NYK", "OKC", 3), (2025, 230, "OKC", "NYK", -3),
    ]  # fmt: skip
    for day in (232, 234, 236, 238):  # the Finals
        rows += [(2025, day, "OKC", "NYK", 7), (2025, day, "NYK", "OKC", -7)]
    columns = ["season", "day", "team", "opp_team", "result"]
    games = pd.DataFrame(rows, columns=columns).assign(game_type="playoffs")
    # until the champion's fourth win, nothing is marked
    assert playoffs(games[games.day < 238]) == {}
    assert playoffs(games) == {
        2025: {"OKC": "champion", "NYK": "runner_up", "BOS": "semifinal",
               "MIN": "semifinal"}
    }  # fmt: skip


def test_views_can_name_dates_and_cap_the_upcoming_ones(webdata, monkeypatch):
    from dataclasses import replace

    from sportsml.web import views

    named = replace(
        views.get_view("toy"),
        date_name=lambda row: f"Game day {row[TOY_SCHEMA.date]}",
        upcoming_dates=1,
    )
    monkeypatch.setitem(views._views, "toy", named)
    snap = Snapshot.load(webdata / "toy")
    upcoming = snap.upcoming()
    date = upcoming["date"]
    assert upcoming["dates"] == [date]
    assert upcoming["date_names"] == {date: f"Game day {date}"}
    game = upcoming["games"][0]
    assert game["date_name"] == f"Game day {date}"
    recent = snap.game(game["game_id"])["summaries"]["home"]["recent"][0]
    assert recent["date_name"] == f"Game day {recent['date']}"
    season = snap.rankings()["seasons"][0]
    assert season["date_names"] == [f"Game day {d}" for d in season["dates"]]


def test_nba_view_stats_and_dates_on_nba_games():
    from sportsml.nba.data.download import build_games
    from sportsml.web.sports.nba import VIEW, date_name, kickoff

    from .test_nba import BOX, LINES, SCHEDULE, TODAY

    games = build_games(SCHEDULE, BOX, LINES, today=TODAY)
    played = games[games.result.notna()]
    for stat in VIEW.stats:
        assert stat.value(played).notna().all(), stat.key
    first = games[games.game_id == "2"].iloc[0]
    assert date_name(first) == "Oct 25"
    assert kickoff(first) == "2024-10-25 22:00"


def test_build_reuses_unchanged_backtest_seasons(tmp_path, monkeypatch):
    import sportsml.backtest
    from sportsml.web.build import backtest_key, code_hash

    from .conftest import make_games

    games = make_games(seasons=(2020, 2021, 2022, 2023, 2024))
    backtested = []
    real = sportsml.backtest.backtest

    def spy(*args, seasons=None, **kwargs):
        backtested.append(list(seasons))
        return real(*args, seasons=seasons, **kwargs)

    monkeypatch.setattr(sportsml.backtest, "backtest", spy)

    def run(**kwargs):
        backtested.clear()
        build(sports=["toy"], output_dir=str(tmp_path), games=games,
              backtest_seasons=2, max_epochs=1, **kwargs)  # fmt: skip
        meta = json.loads((tmp_path / "toy" / "meta.json").read_text())
        pool = pd.read_csv(tmp_path / "toy" / "pool.csv")
        rankings = pd.read_csv(tmp_path / "toy" / "rankings.csv")
        return backtested[:], meta, pool, rankings

    calls, meta, pool, rankings = run()
    assert calls == [[2022, 2023]]
    assert set(meta["backtest_cache"]) == {"2022", "2023"}
    assert set(pool["season"]) == set(rankings["season"]) == {2022, 2023}

    # nothing changed: no backtest, the same rows and summary
    calls, again, pool2, rankings2 = run()
    assert calls == []
    pd.testing.assert_frame_equal(pool2, pool)
    pd.testing.assert_frame_equal(rankings2, rankings)

    # summarized from the stored CSV rather than in memory: equal to ~1e-8
    def close(a, b):
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(map(close, a, b))
        if isinstance(a, float):
            return a == pytest.approx(b, rel=1e-6, abs=1e-9, nan_ok=True)
        return a == b

    assert close(again["backtest"], meta["backtest"])

    # one season's key no longer matches: only that season runs again
    stale = json.loads((tmp_path / "toy" / "meta.json").read_text())
    stale["backtest_cache"]["2022"] = "older model"
    (tmp_path / "toy" / "meta.json").write_text(json.dumps(stale))
    calls, _, pool3, _ = run()
    assert calls == [[2022]]
    assert list(pool3["season"].unique()) == [2022, 2023]
    pd.testing.assert_frame_equal(
        pool3[pool3["season"] == 2023].reset_index(drop=True),
        pool[pool["season"] == 2023].reset_index(drop=True),
    )

    calls, *_ = run(refresh_backtest=True)
    assert calls == [[2022, 2023]]

    # the key follows the training settings and the code
    code = code_hash()
    assert backtest_key("toy", 2022, 1, code) == backtest_key("toy", 2022, 1, code)
    assert backtest_key("toy", 2022, 1, code) != backtest_key("toy", 2022, 2, code)
    assert backtest_key("toy", 2022, 1, code) != backtest_key("toy", 2023, 1, code)
    assert backtest_key("toy", 2022, 1, code) != backtest_key("toy", 2022, 1, "x")


def test_ranking_dates_keep_the_first_last_and_every_nth():
    from sportsml.web.build import ranking_dates

    assert ranking_dates([3, 1, 2]) == [1, 2, 3]
    assert ranking_dates(range(1, 16), 7) == [1, 8, 15]
    assert ranking_dates(range(1, 13), 5) == [1, 6, 11, 12]
    # game days with gaps: the next one at least `every` after the last kept
    assert ranking_dates([1, 3, 6, 9, 10], 4) == [1, 6, 10]
    assert ranking_dates([4, 9], 7) == [4, 9]


def test_ranking_every_thins_backtest_and_current_rankings(
    games, tmp_path, monkeypatch
):
    from sportsml.web import views
    from sportsml.web.build import backtest_key, code_hash, ranking_dates

    toy = views.get_view("toy")
    monkeypatch.setitem(views._views, "toy", dataclasses.replace(toy, ranking_every=5))
    build(sports=["toy"], output_dir=str(tmp_path), games=games,
          backtest_seasons=1, max_epochs=1)  # fmt: skip

    played = games[games["margin"].notna()]
    weeks = {s: sorted(w["week"].unique()) for s, w in played.groupby("season")}
    rankings = pd.read_csv(tmp_path / "toy" / "rankings.csv")
    assert sorted(rankings["date"].unique()) == ranking_dates(weeks[2023], 5)
    assert len(ranking_dates(weeks[2023], 5)) < len(weeks[2023])
    # every game is still predicted
    pool = pd.read_csv(tmp_path / "toy" / "pool.csv")
    assert sorted(pool["week"].unique()) == weeks[2023]

    # the setting is part of the key: not reused by a build ranking every date
    # (2023, the main model's validation season, is backtested with it)
    meta = json.loads((tmp_path / "toy" / "meta.json").read_text())
    code = code_hash("toy")
    key = backtest_key("toy", 2023, 1, code, 5, main_model=True)
    assert meta["backtest_cache"]["2023"] == key
    assert key != backtest_key("toy", 2023, 1, code, main_model=True)

    current = next(
        s
        for s in Snapshot.load(tmp_path / "toy").rankings()["seasons"]
        if s["source"] == "current"
    )
    upcoming_week = games.loc[games["margin"].isna(), "week"].min()
    assert current["dates"] == [*ranking_dates(weeks[2024], 5), upcoming_week]
