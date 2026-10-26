import numpy as np
import pandas as pd

from sportsml.nfl.data.download import build_games
from sportsml.nfl.data.features import SCHEMA, STATS_COLUMNS
from sportsml.nfl.data.names import odds_map


def nflverse_frames():
    """Two games shaped like nflverse; SD's stats are missing from game 2."""
    schedule = pd.DataFrame(
        {
            "game_id": ["2010_01_OAK_KC", "2010_02_SD_STL"],
            "season": [2010, 2010],
            "week": [1, 2],
            "game_type": ["REG", "REG"],
            "location": ["Home", "Neutral"],
            "home_team": ["KC", "STL"],
            "away_team": ["OAK", "SD"],
            "home_score": [21, 10],
            "away_score": [14, 13],
            "result": [7, -3],
            "spread_line": [3.5, -1.0],
            "home_rest": [7, 7],
            "away_rest": [7, 6],
        }
    )
    stats = {col: 0.0 for col in STATS_COLUMNS}
    team_stats = pd.DataFrame(
        [
            {**stats, "season": 2010, "week": 1, "team": "KC", "passing_yards": 250},
            {**stats, "season": 2010, "week": 1, "team": "OAK", "passing_yards": 180},
            {**stats, "season": 2010, "week": 2, "team": "STL", "passing_yards": 300},
            {**stats, "season": 2010, "week": 2, "team": None, "passing_yards": 1},
        ]
    )
    return schedule, team_stats


def test_each_game_has_two_correctly_paired_rows():
    games = build_games(*nflverse_frames())
    assert games.groupby("game_id").size().eq(2).all()
    assert not games.duplicated(["season", "week", "team"]).any()

    kc = games[games.team == "KC"].iloc[0]
    assert (kc.opp_team, kc.location, kc.result, kc.rest, kc.opp_rest) == (
        "LV",
        1,
        7,
        7,
        7,
    )
    assert (kc.passing_yards, kc.opp_passing_yards) == (250, 180)
    lv = games[games.team == "LV"].iloc[0]
    assert (lv.location, lv.result, lv.spread_line) == (-1, -7, -3.5)


def test_missing_stats_are_missing_not_self_paired():
    """Regression: a row without a counterpart used to be paired with itself."""
    games = build_games(*nflverse_frames())
    la = games[games.team == "LA"].iloc[0]
    lac = games[games.team == "LAC"].iloc[0]
    assert la.location == 0 and lac.location == 0
    assert la.passing_yards == 300 and np.isnan(la.opp_passing_yards)
    assert np.isnan(lac.passing_yards) and lac.opp_passing_yards == 300
    assert lac.result == 3


def test_schema_columns_exist_in_built_games():
    games = build_games(*nflverse_frames())
    needed = set(SCHEMA.stats) | {SCHEMA.target, SCHEMA.location, *SCHEMA.key_columns}
    assert needed <= set(games.columns)


def test_odds_names_map_to_current_teams():
    current = {
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET",
        "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO",
        "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
    }  # fmt: skip
    assert set(odds_map.values()) == current
    assert odds_map["Las Vegas Raiders"] == "LV"
