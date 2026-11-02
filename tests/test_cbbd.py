import datetime

import pandas as pd
import pytest

from sportsml import espn
from sportsml.cbb.data import cbbd
from sportsml.cbb.data import download as college

TODAY = datetime.datetime(2025, 3, 20, 12, tzinfo=datetime.timezone.utc)

# CBBD's /games (its own id -> ESPN's sourceId) and /lines, as its API spec
# describes them
GAMES = [
    {"id": 1, "sourceId": "401700001"},
    {"id": 2, "sourceId": "401700002"},
    {"id": 3, "sourceId": "401700003"},
]
LINES = [
    {
        "gameId": 1, "homeScore": 80, "awayScore": 70,
        "lines": [
            {"provider": "teamrankings", "spread": -20, "overUnder": 100,
             "homeMoneyline": -5000, "awayMoneyline": 2000},
            {"provider": "Bovada", "spread": -7.5, "overUnder": 141.5,
             "homeMoneyline": -320, "awayMoneyline": 255},
            {"provider": "ESPN Bet", "spread": -7, "overUnder": None,
             "homeMoneyline": None, "awayMoneyline": None},
        ],
    },
    # CBBD has home and away the other way around: left out
    {"gameId": 2, "homeScore": 60, "awayScore": 75,
     "lines": [{"provider": "Bovada", "spread": 3}]},
]  # fmt: skip


def schedule(*rows):
    return pd.DataFrame(
        rows, columns=["game_id", "start", "home_score", "away_score"]
    ).assign(start=lambda f: pd.to_datetime(f["start"], utc=True))


@pytest.fixture
def api(monkeypatch):
    calls = []

    def rows(path, key, **params):
        calls.append((path, params))
        assert key == "secret"
        return {"games": GAMES, "lines": LINES}[path]

    monkeypatch.setattr(cbbd, "_rows", rows)
    return calls


def test_parse_lines_prefers_books_and_skips_prediction_sites():
    assert cbbd.parse_lines(LINES[0]["lines"]) == {
        "spread_line": 7.0,  # the home team's margin: ESPN Bet's -7
        "spread_provider": "ESPN Bet",
        "total_line": 141.5,
        "total_provider": "Bovada",
        "moneyline": -320.0,
        "opp_moneyline": 255.0,
        "moneyline_provider": "Bovada",
    }
    assert cbbd.parse_lines([]) == {}


def test_season_lines_by_espn_id(api):
    games = schedule(
        ("401700001", "2025-03-01T20:00Z", 80, 70),
        ("401700002", "2025-03-02T20:00Z", 75, 60),
        ("401700003", "2025-03-03T20:00Z", 66, 64),  # settled, no lines
        ("401700004", "2025-03-19T20:00Z", 66, 64),  # lines may still come
    )
    lines = cbbd.season_lines(2025, games, "secret", TODAY)
    assert lines["401700001"]["spread_line"] == 7.0
    assert "401700002" not in lines
    assert lines["401700003"] == {}
    assert "401700004" not in lines
    # only the windows holding these games' dates: March, two endpoints
    assert [path for path, _ in api] == ["games", "lines"]
    assert api[0][1]["startDateRange"] == "2025-02-28T20:00:00Z"


def test_full_windows_are_split(monkeypatch):
    sizes = iter([cbbd.LIMIT, 2, 3])
    calls = []

    def rows(path, key, **params):
        calls.append(params)
        return [{"gameId": len(calls) * 10 + i} for i in range(next(sizes))]

    monkeypatch.setattr(cbbd, "_rows", rows)
    start = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2025, 2, 1, tzinfo=datetime.timezone.utc)
    assert len(cbbd._fetch("lines", "k", 2025, start, end)) == 5
    assert len(calls) == 3


def test_season_lines_cache_bulk_finished_games(api, tmp_path):
    cache = espn.Cache(str(tmp_path))
    games = schedule(("401700001", "2025-03-01T20:00Z", 80, 70))
    fetched = []

    def fetch(game_id):
        fetched.append(game_id)
        return {"spread_line": 1.0}

    def bulk(ids):
        return cbbd.season_lines(2025, games[games.game_id.isin(ids)], "secret", TODAY)

    lines = espn.season_lines(
        2025, ["401700001"], ["401700009"], cache, fetch, workers=1, bulk=bulk
    )
    # finished games in bulk, upcoming ones from ESPN
    assert lines["401700001"]["spread_line"] == 7.0
    assert fetched == ["401700009"]
    assert set(cache.read_json("odds_2025.json")) == {"401700001"}
    # cached: no second request
    espn.season_lines(2025, ["401700001"], [], cache, fetch, workers=1, bulk=bulk)
    assert len(api) == 2


def test_bulk_lines_only_for_men_with_a_key(monkeypatch):
    monkeypatch.delenv(cbbd.KEY_ENV, raising=False)
    assert college.bulk_lines(college.MEN, TODAY) is None
    monkeypatch.setenv(cbbd.KEY_ENV, "secret")
    assert college.bulk_lines(college.MEN, TODAY) is not None
    assert college.bulk_lines(college.WOMEN, TODAY) is None
