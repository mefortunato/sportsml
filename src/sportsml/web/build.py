"""``sportsml web build`` / ``sportsml web serve``."""

from __future__ import annotations

import datetime
import json
import pathlib

from ..core.io import Table, read_table
from ..core.process import process
from ..core.sport import get_sport
from .views import get_view


def build(
    sports: list[str] | None = None,
    output_dir: str = "webdata",
    games: Table | None = None,
    backtest_seasons: int = 5,
    max_epochs: int = 100,
) -> None:
    """Prepare everything the web app serves, one directory per sport.

    Downloads and processes the sport's games, trains the transformer, runs
    a walk-forward backtest of it over the last ``backtest_seasons``
    complete seasons (its out-of-sample predictions are the challenge game
    pool) and saves team metadata.

    Args:
        sports: Sports to build (default ``["nfl"]``).
        output_dir: Writes ``<output_dir>/<sport>/``.
        games: Use this processed games table instead of downloading (one
            sport only).
        max_epochs: Transformer training epochs (per fit).
    """
    from ..backtest import backtest
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
        tested = backtest(
            table,
            sport,
            family="transformer",
            n_seasons=backtest_seasons,
            max_epochs=max_epochs,
        )
        tested["results"].to_csv(path / "pool.csv", index=False)

        summary = tested["summary"]
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
            },
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2, default=float))
        print(f"built {sport} -> {path}")


def serve(
    data_dir: str = "webdata",
    static_dir: str | None = "web/build",
    host: str = "127.0.0.1",
    port: int = 8000,
    refresh: bool = True,
    refresh_hours: float = 6.0,
) -> None:
    """Serve the API and the frontend build with uvicorn."""
    import uvicorn

    from .app import create_app

    app = create_app(data_dir, static_dir, refresh=refresh, refresh_hours=refresh_hours)
    uvicorn.run(app, host=host, port=port)


__all__ = ["build", "serve"]
