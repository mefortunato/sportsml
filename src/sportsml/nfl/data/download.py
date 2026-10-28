from pathlib import Path

import pandas as pd

from .features import STATS_COLUMNS
from .injuries import INJURY_COLUMNS, injury_features
from .names import move_map
from .pbp import PBP_COLUMNS, load_pbp_features
from .weather import weather_features

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


def merge_both_sides(
    games: pd.DataFrame, features: pd.DataFrame, columns: list[str]
) -> pd.DataFrame:
    """Add per ``season, week, team`` ``columns`` for the team and, as
    ``opp_<column>``, for its opponent."""
    keys = ["season", "week"]
    features = features[[*keys, "team", *columns]]
    games = games.merge(features, on=[*keys, "team"], how="left")
    opp = features.rename(
        columns={"team": "opp_team", **{col: f"opp_{col}" for col in columns}}
    )
    return games.merge(opp, on=[*keys, "opp_team"], how="left")


def build_games(
    schedule: pd.DataFrame,
    team_stats: pd.DataFrame,
    injuries: pd.DataFrame | None = None,
    pbp: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Join weekly team stats onto both perspectives of every scheduled game.

    The schedule is the source of truth for which games exist, so games whose
    stats nflverse lacks keep their result with missing stats, and each row's
    opponent stats always come from the opponent's own stats row.
    ``injuries`` (:func:`~.injuries.injury_features` of these games) adds
    ``inj_*`` and ``opp_inj_*`` the same way, and ``pbp``
    (:func:`~.pbp.pbp_features`) the play-by-play stats.
    """
    schedule = schedule.copy()
    for col in ("home_team", "away_team"):
        schedule[col] = schedule[col].replace(move_map)
    games = invert_schedule(schedule)

    stats = team_stats.dropna(subset=["team"]).copy()
    stats["team"] = stats["team"].replace(move_map)
    stats = stats.drop_duplicates(["season", "week", "team"])
    games = merge_both_sides(games, stats, STATS_COLUMNS)
    if pbp is not None:
        games = merge_both_sides(games, pbp, PBP_COLUMNS)
    if injuries is not None:
        games = merge_both_sides(games, injuries, INJURY_COLUMNS)
    return games.sort_values(["season", "week", "game_id", "location"]).reset_index(
        drop=True
    )


def download(output_file: str = None, seasons: list[int] = None) -> pd.DataFrame:
    """Download nflverse schedules, weekly team stats, play-by-play
    efficiency, kickoff weather and injury features (all seasons by
    default)."""
    import nflreadpy

    schedule = nflreadpy.load_schedules(seasons or True).to_pandas()
    schedule = weather_features(schedule)
    team_stats = nflreadpy.load_team_stats(seasons=seasons or True).to_pandas()
    games = build_games(schedule, team_stats)
    played = games.loc[games["result"].notna(), "season"].unique()
    # play-by-play starts in 1999
    pbp = load_pbp_features(sorted(int(s) for s in played if s >= 1999))
    # injury reports start in 2009, snap counts in 2012
    have = sorted(int(s) for s in games["season"].unique() if s >= 2012)
    injuries = injury_features(
        games,
        nflreadpy.load_injuries(have).to_pandas(),
        nflreadpy.load_snap_counts(have).to_pandas(),
        nflreadpy.load_players().to_pandas(),
    )
    games = build_games(schedule, team_stats, injuries, pbp)

    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)

    return games
