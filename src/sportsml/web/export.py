"""``sportsml web export``: every page's data as static JSON files.

The web app is a static site with no server: each page's data is
precomputed here from the snapshots ``sportsml web build`` writes, and the
challenge's random pick and scoring run in the browser. ``refresh=True``
re-downloads results first, so a daily run updates team state, upcoming
predictions and rankings without retraining.

Writes, under ``<output_dir>/data/``:

* ``sports.json``: each sport's info (label, model, backtest summary);
* ``<sport>/upcoming.json``: ``{"default": ..., "by_date": {"<season>-<date>": ...}}``;
* ``<sport>/games.json``: ``{game_id: game view}`` for every upcoming game;
* ``<sport>/challenge.json``: ``[{"game": ..., "answer": ...}]`` per pool game,
  the answer without the pick-dependent ``pick`` / ``correct``;
* ``<sport>/performance.json`` and ``<sport>/rankings.json``.

Team objects are written once per file (``"teams"``) and referenced as
``{"$team": key}``; floats are rounded to 6 decimals.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pandas as pd

from ..core.process import process
from ..core.sport import get_sport
from .snapshot import Snapshot

logger = logging.getLogger(__name__)


def download_games(sport: str) -> pd.DataFrame:
    """The sport's games, freshly downloaded and processed."""
    return process(sport, get_sport(sport).download())


def load_snapshots(data_dir: str | pathlib.Path) -> dict[str, Snapshot]:
    """One snapshot per sport subdirectory of ``data_dir``."""
    snapshots = {}
    for path in sorted(pathlib.Path(data_dir).iterdir()):
        if (path / "meta.json").exists():
            snapshot = Snapshot.load(path)
            snapshots[snapshot.view.sport] = snapshot
            logger.info("loaded %s from %s", snapshot.view.sport, path)
    return snapshots


def _compact(value, teams: dict):
    if isinstance(value, dict):
        key = value.get("team")
        if isinstance(key, str) and key in teams and value == teams[key]:
            return {"$team": key}
        return {k: _compact(v, teams) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact(v, teams) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _write(path: pathlib.Path, data, teams: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"teams": teams, "data": _compact(data, teams)}
    path.write_text(json.dumps(payload, separators=(",", ":")))


def export(
    data_dir: str = "webdata",
    output_dir: str = "web/static",
    refresh: bool = False,
) -> None:
    """Write every sport's page data as static JSON.

    Args:
        data_dir: Built web data (``sportsml web build``).
        output_dir: Writes ``<output_dir>/data/``.
        refresh: Re-download each sport's results first (team state is
            refreshed with the saved model; nothing is retrained). A failed
            download fails the export, so the last published site stays.
    """
    snapshots = load_snapshots(data_dir)
    if refresh:
        snapshots = {
            sport: snap.refreshed(download_games(sport))
            for sport, snap in snapshots.items()
        }
    out = pathlib.Path(output_dir) / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sports.json").write_text(
        json.dumps([snap.info() for snap in snapshots.values()])
    )
    for sport, snap in snapshots.items():
        # the static page's CSP blocks external images: badges fall back to
        # the team-colored chip instead of making requests that fail
        teams = {key: {**team, "logo": None} for key, team in snap.teams.items()}
        snap.teams = teams

        default = snap.upcoming()
        by_date = {
            f"{default['season']}-{date}": snap.upcoming(default["season"], date)
            for date in default["dates"]
        }
        _write(
            out / sport / "upcoming.json",
            {"default": default, "by_date": by_date},
            teams,
        )

        game_ids = {g["game_id"] for week in by_date.values() for g in week["games"]}
        games = {game_id: snap.game(game_id) for game_id in sorted(game_ids)}
        _write(out / sport / "games.json", games, teams)

        challenge = []
        for game_id in snap.pool.index:
            answer = snap.challenge_answer(game_id, "home")
            del answer["pick"], answer["correct"]
            challenge.append({"game": snap.challenge_game(game_id), "answer": answer})
        _write(out / sport / "challenge.json", challenge, teams)
        _write(out / sport / "performance.json", snap.performance(), teams)
        _write(out / sport / "rankings.json", snap.rankings(), teams)
        print(
            f"exported {sport}: {len(by_date)} dates, {len(games)} games, "
            f"{len(challenge)} challenge games -> {out / sport}"
        )
