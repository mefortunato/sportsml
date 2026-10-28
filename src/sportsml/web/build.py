"""``sportsml web build``: data, model and backtest for the web app."""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib

import pandas as pd

from ..core.io import Table, read_table
from ..core.process import process
from ..core.sport import get_sport
from .views import get_view

# Bump to rebuild every cached backtest season once, e.g. after a change the
# code hash cannot see (a dependency upgrade that changes training).
BACKTEST_CACHE_VERSION = 1

# Source the backtest results depend on: everything but the presentation
# layer, the odds client and the CLI (web/build.py's rankings are included).
_UNHASHED = ("web/", "odds/", "cli.py")


def code_hash() -> str:
    """Hash of the package source that shapes backtest results."""
    root = pathlib.Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for file in sorted(root.rglob("*.py")):
        rel = file.relative_to(root).as_posix()
        if rel.startswith(_UNHASHED) and rel != "web/build.py":
            continue
        digest.update(rel.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def backtest_key(sport: str, season: int, max_epochs: int, code: str) -> str:
    """Identifies one season's walk-forward backtest: the same key means the
    same model, training and code, so the stored results can be reused.

    Game data is deliberately left out: finished seasons are treated as
    final (pass ``refresh_backtest`` after a source revises old data).
    """
    from ..models.transformer.fit import transformer_config

    spec = {
        "version": BACKTEST_CACHE_VERSION,
        "sport": sport,
        "season": int(season),
        "family": "transformer",
        "settings": get_sport(sport).transformer,
        "model": transformer_config(sport),
        "max_epochs": max_epochs,
        "code": code,
    }
    text = json.dumps(spec, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def cached_backtest(
    path: pathlib.Path, keys: dict[int, str], season: str = "season"
) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """A previous build's pool and rankings rows for the seasons whose
    backtest key is unchanged, and those seasons."""
    empty = pd.DataFrame(), pd.DataFrame(), []
    try:
        meta = json.loads((path / "meta.json").read_text())
        pool = read_table(str(path / "pool.csv"))
        rankings = read_table(str(path / "rankings.csv"))
    except (OSError, ValueError):
        return empty
    stored = meta.get("backtest_cache", {})
    reuse = [
        s
        for s, key in keys.items()
        if stored.get(str(s)) == key
        and (pool[season] == s).any()
        and (rankings["season"] == s).any()
    ]
    return (
        pool[pool[season].isin(reuse)],
        rankings[rankings["season"].isin(reuse)],
        reuse,
    )


def build(
    sports: list[str] | None = None,
    output_dir: str = "webdata",
    games: Table | None = None,
    backtest_seasons: int = 5,
    max_epochs: int = 100,
    refresh_backtest: bool = False,
) -> None:
    """Prepare everything the web app shows, one directory per sport.

    Downloads and processes the sport's games, trains the transformer, runs
    a walk-forward backtest of it over the last ``backtest_seasons``
    complete seasons (its out-of-sample predictions are the challenge game
    pool, and its team ratings before each date the power rankings) and
    saves team metadata.

    Backtest seasons are reused from the previous build in ``output_dir``
    when nothing that shapes them changed (:func:`backtest_key`: the model
    settings, ``max_epochs`` and the model code), so a routine build only
    trains the model for upcoming games and backtests newly completed
    seasons.

    Args:
        sports: Sports to build (default ``["nfl"]``).
        output_dir: Writes ``<output_dir>/<sport>/``.
        games: Use this processed games table instead of downloading (one
            sport only).
        max_epochs: Transformer training epochs (per fit).
        refresh_backtest: Backtest every season again, ignoring the previous
            build (e.g. after a data source revised old seasons).
    """
    from ..backtest import backtest, complete_seasons, summarize
    from ..inference.utils import power_ratings
    from ..models.lightning import default_trainer
    from ..models.transformer import fit_transformer

    sports = sports or ["nfl"]
    if games is not None and len(sports) != 1:
        raise ValueError("pass games only when building a single sport")
    for sport in sports:
        view = get_view(sport)
        path = pathlib.Path(output_dir) / sport
        path.mkdir(parents=True, exist_ok=True)

        table = (
            read_table(games)
            if games is not None
            else process(sport, get_sport(sport).download())
        )
        table.to_csv(path / "games.csv", index=False)
        teams = view.load_teams()
        (path / "teams.json").write_text(teams.to_json(orient="records", indent=1))

        trainer = default_trainer(
            max_epochs=max_epochs, enable_progress_bar=False, enable_model_summary=False
        )
        fitted = fit_transformer(
            table, sport, trainer=trainer, save_dir=str(path / "model"), overwrite=True
        )
        schema = get_sport(sport).schema
        seasons = complete_seasons(table, schema)[-backtest_seasons:]
        code = code_hash()
        keys = {s: backtest_key(sport, s, max_epochs, code) for s in seasons}
        if refresh_backtest:
            pool, rankings, reused = pd.DataFrame(), pd.DataFrame(), []
        else:
            pool, rankings, reused = cached_backtest(path, keys, schema.season)
        missing = [s for s in seasons if s not in reused]
        print(
            f"{sport} backtest: reusing {reused or 'none'}, "
            f"backtesting {missing or 'none'}",
            flush=True,
        )

        ranked = []

        def rank(predictor, season, date):
            playing = table.loc[table[schema.season] == season, schema.team]
            for team, rating in power_ratings(predictor, playing.unique()).items():
                ranked.append(
                    {"season": season, "date": date, "team": team, "rating": rating}
                )

        if missing:
            tested = backtest(
                table,
                sport,
                family="transformer",
                seasons=missing,
                max_epochs=max_epochs,
                on_date=rank,
            )
            pool = pd.concat([pool, tested["results"]], ignore_index=True)
            rankings = pd.concat([rankings, pd.DataFrame(ranked)], ignore_index=True)
        pool = pool.sort_values(schema.season, kind="stable")
        rankings = rankings.sort_values(["season", "date"], kind="stable")
        pool.to_csv(path / "pool.csv", index=False)
        rankings.to_csv(path / "rankings.csv", index=False)

        summary = {"seasons": [int(s) for s in seasons], **summarize(pool, schema)}
        meta = {
            "sport": sport,
            "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "model": {"family": "transformer", "metrics": fitted["metrics"]},
            "backtest": {
                "seasons": summary["seasons"],
                "overall": summary["overall"],
                "ats": summary.get("ats", [{}])[0],
                "moneyline": summary.get("moneyline", [{}])[0],
                "totals": {
                    k: v
                    for k, v in summary.get("totals", {}).items()
                    if k in ("n", "rmse", "brier")
                }
                | {"record": summary.get("totals", {}).get("record", [{}])[0]},
            },
            "backtest_cache": {str(s): key for s, key in keys.items()},
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2, default=float))
        print(f"built {sport} -> {path}")


__all__ = ["build"]
