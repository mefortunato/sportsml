"""nflverse play-by-play -> one row of numeric play features per play.

Every feature is written from the home team's side: ``offense`` is +1 when
the home team has the ball, -1 when the away team does, and features that
describe what the offense did (yards, EPA, success, ...) are multiplied by
it, so a good play for the away team is negative. Neutral-site games use
nflverse's designated home team. The games table maps each of its rows to
the home or away side of its game through ``home_team`` / ``away_team``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .names import move_map

PLAY_TYPES = (
    "pass", "run", "punt", "field_goal", "kickoff", "extra_point",
    "qb_kneel", "qb_spike", "no_play",
)  # fmt: skip

# offense actions, each scaled and multiplied by the offense's side
OFFENSE_COLUMNS = {
    "yards_gained": 10.0,
    "epa": 1.0,
    "success": 1.0,
    "first_down": 1.0,
    "sack": 1.0,
    "air_yards": 10.0,
    "yards_after_catch": 10.0,
    "complete_pass": 1.0,
    "pass": 1.0,
    "rush": 1.0,
    "shotgun": 1.0,
    "no_huddle": 1.0,
    "qb_scramble": 1.0,
}

KEY_COLUMNS = ("game_id", "home_team", "away_team")


def play_features(pbp: pd.DataFrame) -> pd.DataFrame:
    """Numeric features of every play of ``pbp`` (nflverse play-by-play),
    in game order, with ``game_id``, ``home_team`` and ``away_team``."""
    pbp = pbp[pbp["play_type"].isin(PLAY_TYPES)]
    pbp = pbp.sort_values(["game_id", "play_id"], kind="stable")
    home = pbp["home_team"].replace(move_map)
    away = pbp["away_team"].replace(move_map)
    posteam = pbp["posteam"].replace(move_map)

    def num(col):
        return pd.to_numeric(pbp[col], errors="coerce").fillna(0.0).to_numpy(float)

    def side_of(teams):
        return np.where(teams == home, 1.0, np.where(teams == away, -1.0, 0.0))

    offense = side_of(posteam)
    out = {"offense": offense}
    for kind in PLAY_TYPES:
        out[f"is_{kind}"] = (pbp["play_type"] == kind).to_numpy(float)
    out["quarter"] = num("qtr") / 4
    out["game_seconds"] = num("game_seconds_remaining") / 3600
    out["half_seconds"] = num("half_seconds_remaining") / 1800
    down = num("down")
    for d in (1, 2, 3, 4):
        out[f"down_{d}"] = (down == d).astype(float)
    out["to_go"] = num("ydstogo") / 10
    out["yardline"] = num("yardline_100") / 100

    # the home team's lead before and change during the play
    after = pd.Series(
        num("total_home_score") - num("total_away_score"), index=pbp.index
    )
    before = after.groupby(pbp["game_id"].to_numpy()).shift(1).fillna(0.0)
    out["home_lead"] = before.to_numpy() / 14
    out["points"] = (after - before).to_numpy() / 7

    for col, scale in OFFENSE_COLUMNS.items():
        out[col] = offense * num(col) / scale
    out["turnover"] = offense * (num("interception") + num("fumble_lost"))
    penalized = side_of(pbp["penalty_team"].replace(move_map))
    out["penalty"] = penalized * num("penalty")
    out["penalty_yards"] = penalized * num("penalty_yards") / 10
    # returns (punts, kickoffs, turnovers) are made by the defense
    out["return_yards"] = -offense * num("return_yards") / 10
    out["touchdown"] = side_of(pbp["td_team"].replace(move_map))

    features = pd.DataFrame(out, index=pbp.index).astype(np.float32)
    keys = pd.DataFrame(
        {"game_id": pbp["game_id"], "home_team": home, "away_team": away}
    )
    return pd.concat([keys, features], axis=1).reset_index(drop=True)


def download_plays(
    output_file: str | None = None, seasons: list[int] | None = None
) -> pd.DataFrame:
    """Download nflverse play-by-play (all seasons by default, one at a time)
    and write its play features (:func:`play_features`) as parquet."""
    import nflreadpy

    if seasons is None:
        schedule = nflreadpy.load_schedules(True).to_pandas()
        played = schedule.dropna(subset=["result"])
        seasons = sorted(int(s) for s in played["season"].unique())
    frames = []
    for season in seasons:
        frames.append(play_features(nflreadpy.load_pbp(season).to_pandas()))
    plays = pd.concat(frames, ignore_index=True)

    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        plays.to_parquet(output_file, index=False)
    return plays
