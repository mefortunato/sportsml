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
* ``<sport>/challenge/<n>.json``: ``[{"game": ..., "answers": {market: ...}}]``
  per pool game playable on some market, each answer without the
  pick-dependent ``pick`` / ``correct`` / ``units``, in shards listed by
  ``<sport>/challenge/index.json`` (see :func:`write_challenge`);
* ``<sport>/performance.json`` and ``<sport>/rankings.json``;
* ``<sport>/odds.json`` (with ``odds``): current sportsbook lines for the
  upcoming games (:mod:`sportsml.web.odds`).

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
from ..odds.providers import provider_for
from .odds import load_previous, refresh_odds
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


def write_challenge(
    path: pathlib.Path, challenge: list[dict], teams: dict, shard_size: int = 100
) -> None:
    """The challenge pool as ``challenge/index.json`` and shards of
    ``shard_size`` games, ``challenge/<n>.json``.

    The page picks a game from the index (``[game_id, shard, markets]`` per
    game) and fetches only that game's shard, instead of a pool file that
    reaches tens of MB for college football. Each shard carries just the
    teams its games reference.
    """
    directory = path / "challenge"
    if directory.exists():
        for old in directory.glob("*.json"):
            old.unlink()
    (path / "challenge.json").unlink(missing_ok=True)  # single-file exports
    index = []
    for shard, start in enumerate(range(0, len(challenge), shard_size)):
        entries = challenge[start : start + shard_size]
        used = {e["game"][side]["team"] for e in entries for side in ("home", "away")}
        _write(
            directory / f"{shard}.json",
            entries,
            {key: team for key, team in teams.items() if key in used},
        )
        index += [[e["game"]["game_id"], shard, list(e["answers"])] for e in entries]
    _write(directory / "index.json", {"shard_size": shard_size, "games": index}, {})


def export(
    data_dir: str = "webdata",
    output_dir: str = "web/static",
    refresh: bool = False,
    odds: dict[str, str] | None = None,
    odds_history: str | None = None,
) -> None:
    """Write every sport's page data as static JSON.

    Args:
        data_dir: Built web data (``sportsml web build``).
        output_dir: Writes ``<output_dir>/data/``.
        refresh: Re-download each sport's results first (team state is
            refreshed with the saved model; nothing is retrained). A failed
            download fails the export, so the last published site stays.
        odds: Fetch current lines per sport from a provider, e.g.
            ``{nfl: oddsapi, cfb: cfbd}`` (keys ``ODDS_API_KEY`` /
            ``CFBD_API_KEY``). Skipped when no game kicks off within 8
            days; a failed fetch keeps the previous lines and does not fail
            the export.
        odds_history: The previous ``data/`` (a directory or the deployed
            site's URL) whose ``<sport>/odds.json`` line history to extend.
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

        if odds and sport in odds:
            cards = [g for week in by_date.values() for g in week["games"]]
            payload = refresh_odds(
                provider_for(sport, odds[sport]),
                cards,
                load_previous(odds_history, sport),
            )
            if payload:
                (out / sport).mkdir(parents=True, exist_ok=True)
                (out / sport / "odds.json").write_text(
                    json.dumps(payload, separators=(",", ":"), default=float)
                )
                print(
                    f"odds {sport}: {len(payload['games'])} games from "
                    f"{payload['provider']} (requests left: {payload['remaining']})"
                )

        game_ids = {g["game_id"] for week in by_date.values() for g in week["games"]}
        games = {game_id: snap.game(game_id) for game_id in sorted(game_ids)}
        _write(out / sport / "games.json", games, teams)

        challenge = [
            {"game": snap.challenge_game(game_id), "answers": answers}
            for game_id in snap.pool.index
            if (answers := snap.challenge_answers(game_id))
        ]
        write_challenge(out / sport, challenge, teams)
        _write(out / sport / "performance.json", snap.performance(), teams)
        _write(out / sport / "rankings.json", snap.rankings(), teams)
        print(
            f"exported {sport}: {len(by_date)} dates, {len(games)} games, "
            f"{len(challenge)} challenge games -> {out / sport}"
        )
