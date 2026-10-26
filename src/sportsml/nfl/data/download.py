from pathlib import Path

import pandas as pd

from .features import STATS_COLUMNS
from .names import move_map

LOCATIONS = {"Home": 1, "Away": -1, "Neutral": 0}


def invert_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game from nflverse's one-row-per-game schedule."""
    home = schedule.copy()
    away = schedule.copy()

    away["result"] *= -1
    away["spread_line"] *= -1
    away["location"] = away["location"].replace("Home", "Away")

    home_col_renamer = {
        col: col.removeprefix("home_") for col in home if col.startswith("home_")
    }
    home_col_renamer.update(
        {col: col.replace("away_", "opp_") for col in home if col.startswith("away_")}
    )
    home = home.rename(columns=home_col_renamer)

    away_col_renamer = {
        col: col.removeprefix("away_") for col in away if col.startswith("away_")
    }
    away_col_renamer.update(
        {col: col.replace("home_", "opp_") for col in away if col.startswith("home_")}
    )
    away = away.rename(columns=away_col_renamer)

    games = pd.concat([home, away], ignore_index=True)
    games["location"] = games["location"].map(LOCATIONS)
    return games


def build_games(schedule: pd.DataFrame, team_stats: pd.DataFrame) -> pd.DataFrame:
    """Join weekly team stats onto both perspectives of every scheduled game.

    The schedule is the source of truth for which games exist, so games whose
    stats nflverse lacks keep their result with missing stats, and each row's
    opponent stats always come from the opponent's own stats row.
    """
    schedule = schedule.copy()
    for col in ("home_team", "away_team"):
        schedule[col] = schedule[col].replace(move_map)
    games = invert_schedule(schedule)

    stats = team_stats.dropna(subset=["team"]).copy()
    stats["team"] = stats["team"].replace(move_map)
    stats = stats.drop_duplicates(["season", "week", "team"])
    stats = stats[["season", "week", "team"] + STATS_COLUMNS]

    games = games.merge(stats, on=["season", "week", "team"], how="left")
    opp_stats = stats.rename(
        columns={"team": "opp_team", **{col: f"opp_{col}" for col in STATS_COLUMNS}}
    )
    games = games.merge(opp_stats, on=["season", "week", "opp_team"], how="left")
    return games.sort_values(["season", "week", "game_id", "location"]).reset_index(
        drop=True
    )


def download(output_file: str = None, seasons: list[int] = None) -> pd.DataFrame:
    """Download nflverse schedules and weekly team stats (all seasons by default)."""
    import nflreadpy

    seasons = seasons or True
    schedule = nflreadpy.load_schedules(seasons).to_pandas()
    team_stats = nflreadpy.load_team_stats(seasons=seasons).to_pandas()
    games = build_games(schedule, team_stats)

    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)

    return games
