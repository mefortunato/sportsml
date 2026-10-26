"""Walk-forward backtests of any model family, scored against the market.

For each test season a model is fit on earlier seasons only (the latest of
them validates / calibrates). The season is then replayed date by date: team
state is refreshed from the games played so far and that date's games are
predicted, the same retrain-occasionally, refresh-weekly loop as production.

Where the sport's schema names market columns, the market's spread and
moneylines are scored on the same games, and the model's disagreements with
the spread are scored as bets against it.
"""

from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Callable
from typing import Literal

import numpy as np
import pandas as pd
import sklearn.base

from .core.io import Table, read_table
from .core.metrics import evaluate, fit_sigma, win_probability
from .core.predictor import Predictor
from .core.schema import GameSchema, one_row_per_game, played, upcoming
from .core.splits import SeasonSplit, split_seasons
from .core.sport import get_sport

# Fits a model on the games it is given (all before the test season).
Fitter = Callable[[pd.DataFrame, SeasonSplit], Predictor]

# Win rate needed to break even on bets at -110.
BREAKEVEN = 110 / 210


def sklearn_fitter(
    sport: str, model: sklearn.base.BaseEstimator | None = None, **kwargs
) -> Fitter:
    from .models.sklearn import fit_sklearn

    def fit(games: pd.DataFrame, split: SeasonSplit) -> Predictor:
        return fit_sklearn(
            games,
            sport,
            model=model,
            train_seasons=split.train,
            val_seasons=split.val,
            test_seasons=split.test,
            print_metrics=False,
            **kwargs,
        )["predictor"]

    return fit


def gnn_fitter(sport: str, max_epochs: int = 100, **kwargs) -> Fitter:
    from .models.gnn import default_model, default_trainer, fit_gnn

    def fit(games: pd.DataFrame, split: SeasonSplit) -> Predictor:
        trainer = default_trainer(
            max_epochs=max_epochs,
            enable_progress_bar=False,
            enable_model_summary=False,
        )
        return fit_gnn(
            games,
            sport,
            model=default_model(sport),
            trainer=trainer,
            train_seasons=split.train,
            val_seasons=split.val,
            test_seasons=split.test,
            print_metrics=False,
            **kwargs,
        )["predictor"]

    return fit


def no_vig_probability(moneyline, opp_moneyline) -> np.ndarray:
    """P(team wins) implied by American moneylines, bookmaker margin removed."""

    def implied(line):
        line = np.asarray(line, dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(line > 0, 100 / (line + 100), -line / (100 - line))

    team, opp = implied(moneyline), implied(opp_moneyline)
    return team / (team + opp)


def market_predictions(
    rows: pd.DataFrame, schema: GameSchema, sigma: float
) -> pd.DataFrame:
    """The market's margin (spread) and win probability for each row.

    Probabilities come from the moneylines where both exist, else from the
    spread with residual spread ``sigma``.
    """
    margin = rows[schema.market_spread].astype(float)
    prob = win_probability(margin, sigma)
    if schema.market_moneyline:
        team, opp = (rows[col] for col in schema.market_moneyline)
        no_vig = no_vig_probability(team, opp)
        prob = np.where(np.isfinite(no_vig), no_vig, prob)
    return pd.DataFrame(
        {"market_margin": margin, "market_prob": prob}, index=rows.index
    )


def walk_forward(
    games: pd.DataFrame,
    sport: str,
    fitter: Fitter,
    seasons: list[int],
    verbose: bool = False,
) -> pd.DataFrame:
    """Out-of-sample predictions for every played game of ``seasons``.

    Returns one row per game (home team's perspective) with the result, the
    model's ``pred_margin`` / ``win_prob`` and, if the schema has market
    columns, ``market_margin`` / ``market_prob``.
    """
    schema = get_sport(sport).schema
    games = played(games, schema)
    out = []
    for season in seasons:
        start = time.time()
        history = games[games[schema.season] < season]
        split = split_seasons(history[schema.season].unique(), test=[])
        predictor = fitter(history, split)

        current = games[games[schema.season] == season]
        season_preds = []
        for date in sorted(current[schema.date].unique()):
            known = pd.concat([history, current[current[schema.date] < date]])
            predictor.update_state(known)
            day = one_row_per_game(current[current[schema.date] == date], schema)
            teams = set(predictor.model.teams)
            has_state = day[schema.team].isin(teams) & day[schema.opp].isin(teams)
            if has_state.any():
                season_preds.append(predictor.predict(day[has_state]))
        season_preds = pd.concat(season_preds, ignore_index=True)

        if schema.market_spread:
            lined = history.dropna(subset=[schema.market_spread])
            sigma = fit_sigma(lined[schema.target], lined[schema.market_spread])
            market = market_predictions(season_preds, schema, sigma)
            season_preds = pd.concat([season_preds, market], axis=1)
        out.append(season_preds)
        if verbose:
            print(
                f"{season}: {len(season_preds)} games predicted "
                f"({time.time() - start:.0f}s)",
                flush=True,
            )

    results = pd.concat(out, ignore_index=True)
    keep = [*schema.key_columns, schema.location, schema.target]
    keep += [schema.team_name, schema.opp_name, *schema.display]
    keep += ["pred_margin", "win_prob", "market_margin", "market_prob"]
    return results[[c for c in dict.fromkeys(keep) if c and c in results]]


def ats_record(
    results: pd.DataFrame, schema: GameSchema, thresholds=(0, 1, 2, 3, 4, 5)
) -> pd.DataFrame:
    """Bet the side the model favors vs the spread when it disagrees by > t.

    A bet wins when that side covers; pushes return the stake. ROI assumes
    -110 on every bet.
    """
    edge = (results["pred_margin"] - results["market_margin"]).to_numpy()
    cover = (results[schema.target] - results["market_margin"]).to_numpy()
    rows = []
    for t in thresholds:
        bet = np.abs(edge) > t
        outcome = np.sign(edge[bet]) * np.sign(cover[bet])
        wins, losses = int((outcome > 0).sum()), int((outcome < 0).sum())
        pushes = int((outcome == 0).sum())
        decided = wins + losses
        pct = wins / decided if decided else np.nan
        half = 1.96 * np.sqrt(pct * (1 - pct) / decided) if decided else np.nan
        rows.append(
            {
                "min_edge": t,
                "bets": int(bet.sum()),
                "wins": wins,
                "losses": losses,
                "pushes": pushes,
                "win_pct": pct,
                "ci95_low": pct - half,
                "ci95_high": pct + half,
                "roi": (wins * 100 / 110 - losses) / max(int(bet.sum()), 1),
            }
        )
    return pd.DataFrame(rows)


def edge_correlation(results: pd.DataFrame, schema: GameSchema) -> dict:
    """Correlation of (model - spread) with (result - spread), with 95% CI.

    Above zero means the model knows something the spread does not.
    """
    edge = results["pred_margin"] - results["market_margin"]
    cover = results[schema.target] - results["market_margin"]
    r = float(np.corrcoef(edge, cover)[0, 1])
    half = 1.96 / np.sqrt(len(edge) - 3)
    low, high = np.tanh(np.arctanh(r) - half), np.tanh(np.arctanh(r) + half)
    return {"r": r, "ci95_low": float(low), "ci95_high": float(high)}


def summarize(results: pd.DataFrame, schema: GameSchema, early_dates: int = 4):
    """Model (and market) metrics overall, by season and by phase of season.

    With market columns, every metric is computed on the games that have a
    market line, so model and market are scored on the same games.
    """
    sources = {"model": ("pred_margin", "win_prob")}
    if "market_margin" in results:
        sources["market"] = ("market_margin", "market_prob")
        results = results.dropna(subset=["market_margin", "market_prob"])

    def score(frame):
        y = frame[schema.target]
        return {
            name: evaluate(y, frame[margin], frame[prob])
            for name, (margin, prob) in sources.items()
        }

    date_rank = results.groupby(schema.season)[schema.date].rank(method="dense")
    phase = np.where(date_rank <= early_dates, f"first {early_dates} dates", "rest")
    summary = {
        "overall": score(results),
        "by_season": {int(s): score(f) for s, f in results.groupby(schema.season)},
        "by_phase": {p: score(f) for p, f in results.groupby(phase)},
    }
    if "market" in sources:
        summary["ats"] = ats_record(results, schema).to_dict("records")
        summary["edge_correlation"] = edge_correlation(results, schema)
    return summary


def format_summary(summary: dict) -> str:
    cols = ["n", "rmse", "mae", "accuracy", "brier", "log_loss"]

    def table(scores: dict) -> pd.DataFrame:
        frame = pd.DataFrame(
            {(k, src): m for k, by_src in scores.items() for src, m in by_src.items()}
        ).T[cols]
        frame["n"] = frame["n"].astype(int)
        return frame

    fmt = {"float_format": lambda v: f"{v:.4f}"}
    parts = [
        "Overall\n" + table({"all": summary["overall"]}).droplevel(0).to_string(**fmt),
        "By season\n" + table(summary["by_season"]).to_string(**fmt),
        "By phase\n" + table(summary["by_phase"]).to_string(**fmt),
    ]
    if "ats" in summary:
        ats = pd.DataFrame(summary["ats"]).set_index("min_edge")
        parts.append(
            f"Against the spread (break-even {BREAKEVEN:.2%} at -110)\n"
            + ats.to_string(**fmt)
        )
        corr = summary["edge_correlation"]
        parts.append(
            "Edge vs cover correlation: "
            f"{corr['r']:+.4f} (95% CI {corr['ci95_low']:+.4f} to "
            f"{corr['ci95_high']:+.4f})"
        )
    return "\n\n".join(parts)


def complete_seasons(games: pd.DataFrame, schema: GameSchema) -> list[int]:
    """Fully played seasons with at least two earlier seasons (train + val)."""
    seasons = sorted(played(games, schema)[schema.season].unique())
    unfinished = set(upcoming(games, schema)[schema.season])
    return [int(s) for s in seasons[2:] if s not in unfinished]


def backtest(
    games: Table,
    sport: str,
    family: Literal["sklearn", "gnn"] = "sklearn",
    seasons: list[int] | None = None,
    n_seasons: int = 5,
    model: sklearn.base.BaseEstimator | None = None,
    max_epochs: int = 100,
    output_dir: str | None = None,
    print_summary: bool = True,
) -> dict:
    """Walk-forward backtest of a model family against the market.

    Args:
        games: Processed games table.
        sport: Sport name, e.g. ``"nfl"``.
        family: ``"sklearn"`` or ``"gnn"``.
        seasons: Test seasons; default the last ``n_seasons`` complete ones.
        model: sklearn regressor (``family="sklearn"``); default random forest.
        max_epochs: GNN training epochs per season (``family="gnn"``).
        output_dir: Write ``<family>_games.csv`` (one row per game) and
            ``<family>_summary.json`` here.

    Returns:
        ``{"results": per-game DataFrame, "summary": dict}``
    """
    games = read_table(games)
    schema = get_sport(sport).schema
    if seasons is None:
        seasons = complete_seasons(games, schema)[-n_seasons:]
    if family == "sklearn":
        fitter = sklearn_fitter(sport, model=model)
    elif family == "gnn":
        fitter = gnn_fitter(sport, max_epochs=max_epochs)
    else:
        raise ValueError(f"unknown model family {family!r}; use sklearn or gnn")

    results = walk_forward(games, sport, fitter, seasons, verbose=print_summary)
    summary = {
        "sport": sport,
        "family": family,
        "seasons": [int(s) for s in seasons],
        **summarize(results, schema),
    }
    if output_dir:
        path = pathlib.Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        results.to_csv(path / f"{family}_games.csv", index=False)
        (path / f"{family}_summary.json").write_text(
            json.dumps(summary, indent=2, default=float)
        )
    if print_summary:
        print(format_summary(summary))
    return {"results": results, "summary": summary}
