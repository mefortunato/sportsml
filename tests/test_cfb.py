import datetime
import json

import numpy as np
import pandas as pd
import pytest

from sportsml.cfb.data import download as cfbd
from sportsml.cfb.data.download import FCS, build_games, market
from sportsml.cfb.data.features import SCHEMA
from sportsml.core.process import process
from sportsml.core.schema import mirror, validate

from .cfbd_fixtures import BOX, LINES, SCHEDULE

TODAY = datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc)


@pytest.fixture
def games():
    return build_games(SCHEDULE, BOX, LINES, today=TODAY)


def row(games, game_id, team_name):
    rows = games[(games.game_id == str(game_id)) & (games.team_name == team_name)]
    assert len(rows) == 1
    return rows.iloc[0]


def test_schema_columns_and_two_rows_per_game(games):
    validate(games, SCHEMA)
    assert games.groupby("game_id").size().eq(2).all()
    processed = process("cfb", games)
    assert len(processed) == len(games)


def test_fcs_opponents_are_pooled_and_fcs_only_games_dropped(games):
    assert "3" not in set(games.game_id)
    bama = row(games, 1, "Alabama")
    assert (bama.opp_team, bama.opp_name, bama.opp_conference) == (
        FCS,
        "Montana State",
        FCS,
    )
    msu = row(games, 1, "Montana State")
    assert (msu.team, msu.location, msu.result) == (FCS, -1, -42)
    assert np.isnan(msu.rest)


def test_neutral_sites_and_cancelled_and_upcoming_games(games):
    assert row(games, 2, "Georgia").location == 0
    assert row(games, 2, "Clemson").location == 0
    assert "5" not in set(games.game_id)  # cancelled
    sugar = row(games, 11, "Georgia")
    assert np.isnan(sugar.result) and np.isnan(sugar.totalYards)
    assert sugar.spread_line == 3.0


def test_bowl_weeks_follow_the_regular_season_in_order(games):
    week = games.drop_duplicates("game_id").set_index("game_id")["week"]
    assert list(week[["1", "4", "6"]]) == [1, 2, 3]
    # first round, a bowl a week later, semifinal, final: increasing weeks
    assert week["7"] == 4
    assert week["7"] < week["8"] < week["9"] < week["10"]
    types = games.drop_duplicates("game_id").set_index("game_id")["game_type"]
    assert (types["1"], types["7"], types["8"], types["10"]) == (
        "regular",
        "playoff",
        "bowl",
        "final",
    )


def test_lines_prefer_books_and_skip_placeholder_moneylines():
    lines = market(LINES).set_index("game_id")
    # Bovada's spread, but its moneyline is a placeholder: none from it
    assert lines.loc["1", "spread_line"] == 38.5
    assert np.isnan(lines.loc["1", "moneyline"])
    # DraftKings outranks numberfire for every market
    assert (lines.loc["2", "spread_line"], lines.loc["2", "total_line"]) == (13.5, 48.5)
    assert (lines.loc["2", "moneyline"], lines.loc["2", "opp_moneyline"]) == (-500, 375)


def test_market_columns_from_both_perspectives(games):
    home, away = row(games, 4, "Alabama"), row(games, 4, "Georgia")
    assert (home.spread_line, away.spread_line) == (-1.5, 1.5)
    assert (home.moneyline, home.opp_moneyline) == (105, -125)
    assert (away.moneyline, away.opp_moneyline) == (-125, 105)
    assert home.total_line == away.total_line == 50.5
    assert home.total == away.total == 75
    mirrored = mirror(games[games.game_id == "4"], SCHEMA)
    assert sorted(mirrored.spread_line) == [-1.5, 1.5]


def test_box_scores_join_both_sides(games):
    bama = row(games, 4, "Alabama")
    assert (bama.totalYards, bama.opp_totalYards) == (500, 480)
    assert (bama.passingCompletions, bama.passingAttempts) == (20, 31)
    assert (bama.thirdDownConv, bama.thirdDownAtt) == (5, 12)
    assert bama.possessionTime == pytest.approx(31.5)
    assert (bama.points, bama.opp_points, bama.result) == (41, 34, 7)
    # the FCS side keeps its own box score
    assert row(games, 1, "Alabama").opp_thirdDownAtt == 14
    # no box score: stats missing, result kept
    clemson = row(games, 6, "Clemson")
    assert clemson.result == -7 and np.isnan(clemson.totalYards)


def test_rest_days(games):
    bama = games[games.team_name == "Alabama"].set_index("game_id")
    assert bama.loc["1", "rest"] == cfbd.MAX_REST  # opener
    assert bama.loc["4", "rest"] == 7
    assert bama.loc["4", "opp_rest"] == 7
    assert bama.loc["7", "rest"] == cfbd.MAX_REST  # long layoff, capped


def test_v1_snake_case_responses_parse_the_same():
    snake = [
        {cfbd.snake(k): v for k, v in g.items()} | {"home_division": "fbs"}
        for g in SCHEDULE
    ]
    for g in snake:
        g["home_division"] = g.pop("home_classification")
        g["away_division"] = g.pop("away_classification")
    games = build_games(snake, BOX, LINES, today=TODAY)
    expected = build_games(SCHEDULE, BOX, LINES, today=TODAY)
    pd.testing.assert_frame_equal(games, expected)


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fake_api(calls):
    def get(url, params, headers, timeout):
        calls.append((url, dict(params)))
        path = url.removeprefix(cfbd.API)
        season_type = params.get("seasonType")
        if path in ("/games", "/lines"):
            assert season_type == "both"
            return FakeResponse(SCHEDULE if path == "/games" else LINES)
        if path == "/games/teams":
            return FakeResponse(BOX if params["week"] == 1 else [])
        raise AssertionError(path)

    return get


def test_download_caches_finished_seasons(monkeypatch, tmp_path):
    monkeypatch.setenv("CFBD_API_KEY", "test")
    calls = []
    monkeypatch.setattr(cfbd.httpx, "get", fake_api(calls))
    out = tmp_path / "raw.csv"
    games = cfbd.download(str(out), 2024, 2024, cache_dir=str(tmp_path / "cache"))
    assert out.exists() and len(games) == len(pd.read_csv(out))
    assert {c[0].removeprefix(cfbd.API) for c in calls} == {
        "/games",
        "/lines",
        "/games/teams",
    }
    first = len(calls)
    # 2024 is finished: the second download makes no calls
    cfbd.download(None, 2024, 2024, cache_dir=str(tmp_path / "cache"))
    assert len(calls) == first
    cached = list((tmp_path / "cache").glob("*.json"))
    assert cached and all(json.loads(p.read_text()) is not None for p in cached)


def test_client_retries_rate_limits(monkeypatch):
    monkeypatch.setenv("CFBD_API_KEY", "test")
    monkeypatch.setattr(cfbd.time, "sleep", lambda s: None)
    responses = [FakeResponse(None, 429), FakeResponse([1])]
    monkeypatch.setattr(cfbd.httpx, "get", lambda *a, **k: responses.pop(0))
    assert cfbd.Client().get("/games", year=2024) == [1]


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("CFBD_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CFBD_API_KEY"):
        cfbd.Client()


def test_playoff_marks(games):
    from sportsml.web.sports.cfb import playoffs

    assert playoffs(games[games.result.notna()]) == {
        2024: {
            "Alabama": "semifinal",
            "Notre Dame": "runner_up",
            "Ohio State": "champion",
        }
    }


def test_kickoff_in_eastern_time(games):
    from sportsml.web.sports.cfb import kickoff

    assert kickoff(row(games, 4, "Alabama")) == "2024-09-07 19:30"
    assert kickoff(pd.Series({"start_date": None})) is None
    tbd = pd.Series({"start_date": "2024-09-07T16:00:00.000Z", "start_time_tbd": True})
    assert kickoff(tbd) == "2024-09-07"


def test_view_stats_compute_on_games(games):
    from sportsml.web.sports.cfb import VIEW

    bama = games[(games.game_id == "4") & (games.team_name == "Alabama")]
    values = {s.key: s.value(bama).iloc[0] for s in VIEW.stats}
    assert values["yards"] == 500 and values["points_allowed"] == 34
    assert values["third_down_pct"] == pytest.approx(100 * 5 / 12)


def test_team_metadata():
    from sportsml.cfb.data.teams import teams_frame
    from sportsml.web.views import TEAM_COLUMNS

    teams = teams_frame(
        [
            {"school": "Air Force", "mascot": "Falcons", "conference": "Mountain West",
             "division": None, "color": "#003594", "alternateColor": "ffffff",
             "logos": ["https://cdn.collegefootballdata.com/logos/500/2005.png"]},
            {"school": "Army", "mascot": "Black Knights", "conference": "American",
             "division": "West", "color": None, "alternateColor": None, "logos": []},
        ]
    ).set_index("team")  # fmt: skip
    assert set(TEAM_COLUMNS) <= {"team", *teams.columns}
    assert teams.loc["Air Force", "color2"] == "#ffffff"
    assert teams.loc["Army", "division"] == "American West"
    assert teams.loc[FCS, "conference"] == FCS
