"""Per-game offensive efficiency from nflverse play-by-play.

Box scores sum EPA and yards over every snap, garbage time included. These
rate each offense per play, and in neutral game states (win probability
0.1-0.9, outside the last two minutes of a half) where play calling is not
driven by the score. A team's defense is its opponent's offense
(``opp_<column>``), the same way the box-score stats pair up.

Like the box score, these describe a finished game: they are ``stats`` that
the models average over a team's earlier games, never inputs about the game
being predicted. Play-by-play starts in 1999.
"""

from __future__ import annotations

import pandas as pd

from .names import move_map

PBP_COLUMNS = [
    "plays",
    "epa_per_play",
    "success_rate",
    "dropback_epa",
    "rush_epa_per_play",
    "early_down_epa",
    "neutral_epa",
    "neutral_pass_oe",
    "neutral_sec_per_play",
    "explosive_rate",
    "drives",
    "start_yardline",
]
OPP_PBP_COLUMNS = [f"opp_{col}" for col in PBP_COLUMNS]

# play-by-play columns the features read (load_pbp has ~370)
SOURCE_COLUMNS = [
    "game_id",
    "season",
    "week",
    "play_id",
    "posteam",
    "play_type",
    "pass",
    "rush",
    "qb_kneel",
    "qb_spike",
    "down",
    "epa",
    "success",
    "wp",
    "pass_oe",
    "yards_gained",
    "half_seconds_remaining",
    "game_seconds_remaining",
    "fixed_drive",
    "yardline_100",
]
NEUTRAL_WP = (0.1, 0.9)
EXPLOSIVE_PASS = 20
EXPLOSIVE_RUSH = 10


def pbp_features(pbp: pd.DataFrame) -> pd.DataFrame:
    """``season, week, team`` + one row of :data:`PBP_COLUMNS` per offense
    per game.

    Args:
        pbp: nflverse play-by-play (``load_pbp``), at least
            :data:`SOURCE_COLUMNS`.
    """
    pbp = pbp[pbp["posteam"].notna()].sort_values(["game_id", "play_id"])
    pbp = pbp.assign(team=pbp["posteam"].replace(move_map))
    keys = ["season", "week", "team"]

    # seconds from one snap to the next within a drive, penalties included
    snaps = pbp[pbp["play_type"].isin(["pass", "run", "no_play"])]
    nxt = snaps.groupby(["game_id", "fixed_drive"])["game_seconds_remaining"].shift(-1)
    snaps = snaps.assign(sec_per_play=snaps["game_seconds_remaining"] - nxt)

    plays = snaps[
        ((snaps["pass"] == 1) | (snaps["rush"] == 1))
        & (snaps["qb_kneel"] != 1)
        & (snaps["qb_spike"] != 1)
        & snaps["epa"].notna()
    ]
    neutral = plays["wp"].between(*NEUTRAL_WP) & (plays["half_seconds_remaining"] > 120)
    dropback = plays["pass"] == 1
    explosive = plays["yards_gained"] >= dropback.map(
        {True: EXPLOSIVE_PASS, False: EXPLOSIVE_RUSH}
    )

    def per_play(value, mask=None) -> pd.Series:
        frame = plays[keys].assign(value=value)
        if mask is not None:
            frame = frame[mask]
        return frame.groupby(keys)["value"].mean()

    drive_starts = (
        pbp[pbp["fixed_drive"].notna() & pbp["yardline_100"].notna()]
        .drop_duplicates(["game_id", "fixed_drive"])
        .groupby(keys)["yardline_100"]
    )
    early = plays["down"].isin([1, 2])
    out = pd.concat(
        {
            "plays": plays.groupby(keys).size(),
            "epa_per_play": per_play(plays["epa"]),
            "success_rate": per_play(plays["success"]),
            "dropback_epa": per_play(plays["epa"], dropback),
            "rush_epa_per_play": per_play(plays["epa"], ~dropback),
            "early_down_epa": per_play(plays["epa"], early),
            "neutral_epa": per_play(plays["epa"], neutral),
            "neutral_pass_oe": per_play(plays["pass_oe"], neutral),
            "neutral_sec_per_play": per_play(plays["sec_per_play"], neutral),
            "explosive_rate": per_play(explosive.astype(float)),
            "drives": drive_starts.size(),
            # own 25 is 75 yards to go
            "start_yardline": drive_starts.mean(),
        },
        axis=1,
    )
    out["plays"] = out["plays"].fillna(0)
    return out.reset_index()[[*keys, *PBP_COLUMNS]]


def load_pbp_features(seasons: list[int]) -> pd.DataFrame:
    """:func:`pbp_features` of each season, loaded one season at a time."""
    import nflreadpy

    frames = []
    for season in seasons:
        pbp = nflreadpy.load_pbp([season]).select(SOURCE_COLUMNS).to_pandas()
        frames.append(pbp_features(pbp))
    return pd.concat(frames, ignore_index=True)
