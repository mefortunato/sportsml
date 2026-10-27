"""Source parsers fed with data shaped like each API's real responses."""

import pandas as pd

from sportsml.cbb.data.features import SCHEMA as CBB_SCHEMA
from sportsml.cbb.data.kaggle import format_games
from sportsml.nba.data.download import process_games
from sportsml.nba.data.features import SCHEMA as NBA_SCHEMA
from sportsml.nba.data.names import odds_map as nba_odds_map
from sportsml.odds.utils import process_odds


def test_kaggle_rows_become_two_perspectives_with_names():
    stats = ["FGM", "FGA", "FGM3", "FGA3", "FTM", "FTA", "OR", "DR", "Ast", "TO"]
    stats += ["Stl", "Blk", "PF"]
    row = {"Season": 2026, "DayNum": 30, "NumOT": 0, "WLoc": "A"}
    row |= {"WTeamID": 1104, "WScore": 80, "LTeamID": 1101, "LScore": 70}
    row |= {f"W{s}": 10 for s in stats} | {f"L{s}": 5 for s in stats}
    teams = pd.DataFrame(
        {"TeamID": [1101, 1104], "TeamName": ["Abilene Chr", "Alabama"]}
    )
    games = format_games(pd.DataFrame([row]), teams)

    assert len(games) == 2 and games["_id"].nunique() == 1
    bama = games[games.TeamID == 1104].iloc[0]
    acu = games[games.TeamID == 1101].iloc[0]
    assert (bama.Team, bama.Loc, bama.PlusMinus, bama.FGM, bama.FGM_OPP) == (
        "Alabama",
        -1,
        10,
        10,
        5,
    )
    assert (acu.Team_OPP, acu.Loc, acu.PlusMinus, acu.Win) == ("Alabama", 1, -10, 0)
    assert set(CBB_SCHEMA.stats) <= set(games.columns)


def nba_rows():
    base = {"FGM": 40, "FGA": 85, "FG3M": 12, "FG3A": 30, "FTM": 15, "FTA": 20}
    base |= {"OREB": 10, "DREB": 30, "AST": 25, "STL": 7, "BLK": 5, "TOV": 12, "PF": 18}
    rows = []
    for season_id, game_id, date in [
        ("12025", "001", "2025-10-05"),  # preseason
        ("22025", "002", "2025-10-22"),
        ("22025", "003", "2025-10-25"),
    ]:
        rows += [
            {**base, "SEASON_ID": season_id, "GAME_ID": game_id, "GAME_DATE": date,
             "TEAM_ID": 1, "TEAM_ABBREVIATION": "BOS", "TEAM_NAME": "Boston Celtics",
             "MATCHUP": "BOS vs. NYK", "PTS": 110},
            {**base, "SEASON_ID": season_id, "GAME_ID": game_id, "GAME_DATE": date,
             "TEAM_ID": 2, "TEAM_ABBREVIATION": "NYK", "TEAM_NAME": "New York Knicks",
             "MATCHUP": "NYK @ BOS", "PTS": 104},
        ]  # fmt: skip
    return pd.DataFrame(rows)


def test_nba_games_are_paired_and_preseason_dropped():
    games = process_games(nba_rows())
    assert set(games.GAME_ID) == {"002", "003"}
    bos = games[games.TEAM == "BOS"].sort_values("DAY")
    assert list(bos.PLUS_MINUS) == [6, 6]
    assert list(bos.LOCATION) == [1, 1]
    assert list(bos.TEAM_OPP) == ["NYK", "NYK"]
    assert list(bos.DAY) == [0, 3] and bos.REST.iloc[1] == 3
    assert games[games.TEAM == "NYK"].LOCATION.eq(-1).all()
    assert set(NBA_SCHEMA.key_columns + list(NBA_SCHEMA.stats)) <= set(games.columns)


def test_nba_odds_names_are_unique_abbreviations():
    assert len(set(nba_odds_map.values())) == 30
    assert nba_odds_map["Milwaukee Bucks"] == "MIL"


def test_odds_api_payload_to_consensus_lines():
    odds = [
        {
            "id": "x",
            "commence_time": "2026-11-01T13:00:00-05:00",
            "home_team": "Buffalo Bills",
            "away_team": "Baltimore Ravens",
            "bookmakers": [
                {
                    "key": book,
                    "title": book,
                    "last_update": "2026-10-30T12:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-10-30T12:00:00Z",
                            "outcomes": [
                                {"name": "Buffalo Bills", "price": -150 + shift},
                                {"name": "Baltimore Ravens", "price": 130},
                            ],
                        },
                        {
                            "key": "spreads",
                            "last_update": "2026-10-30T12:00:00Z",
                            "outcomes": [
                                {"name": "Buffalo Bills", "price": -110, "point": -3.0},
                                {
                                    "name": "Baltimore Ravens",
                                    "price": -110,
                                    "point": 3.0,
                                },
                            ],
                        },
                        {
                            "key": "totals",
                            "last_update": "2026-10-30T12:00:00Z",
                            "outcomes": [
                                {"name": "Over", "price": -110, "point": 47.5},
                                {"name": "Under", "price": -110, "point": 47.5},
                            ],
                        },
                    ],
                }
                for book, shift in [("dk", 0), ("fd", 10)]
            ],
        }
    ]
    from sportsml.nfl.data.names import odds_map

    lines = process_odds(odds, odds_map).iloc[0]
    assert (lines.team, lines.opp_team) == ("BUF", "BAL")
    assert lines.moneyline == -145 and lines.spread_line == -3.0
    assert lines.total_line == 47.5
