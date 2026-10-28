from __future__ import annotations

import dataclasses

import lightning.pytorch as pl
import numpy as np
import pandas as pd
import torch

from ...core.evaluation import finish_fit
from ...core.io import Table, read_table
from ...core.predictor import prepare_save_dir
from ...core.schema import GameSchema, played
from ...core.splits import split_seasons
from ...core.sport import get_sport
from ..lightning import best_model, default_trainer, output_targets, seed_and_reset
from ..transformer.data import SequenceFeatures, extra_columns
from ..transformer.model import PairHead, SequenceEncoder
from .data import DateBatches, PbpData, PlayTable
from .model import PbpMatchupModel, PbpModel, PlayEncoder

TEAM_KEYS = (
    "history", "d_model", "nhead", "num_layers", "dropout",
    "season_embedding", "season_decay", "max_seasons_ago", "decay_init",
)  # fmt: skip
DEFAULTS = {
    "max_plays": 208,
    "game_d_model": 32,
    "game_nhead": 4,
    "game_layers": 2,
    "game_dropout": 0.0,
    "history": 20,
    "d_model": 64,
    "nhead": 4,
    "num_layers": 2,
    "dropout": 0.1,
    "form_games": 4,
    "aux_weight": 0.5,
    "total_weight": 0.0,
}


def default_plays(sport: str) -> str:
    return f"data/{sport}/plays.parquet"


def token_schema(schema: GameSchema) -> GameSchema:
    """The schema whose :class:`SequenceFeatures` tokens are a history
    game's extras: its margin, total (if any) and location."""
    return dataclasses.replace(schema, stats=(schema.total,) if schema.total else ())


def pbp_dims(schema: GameSchema, opponent_strength: bool = True) -> dict[str, int]:
    """Extra token / context feature counts a PbpModel needs for ``schema``."""
    location = [schema.location] if schema.location else []
    extras = list(dict.fromkeys([*token_schema(schema).stats, schema.target]))
    extras += location + extra_columns(opponent_strength, False)
    return {
        "extra_dim": len(extras),
        "context_dim": len(schema.context) + len(location),
    }


def pbp_settings(sport: str, **overrides) -> dict:
    return {**DEFAULTS, **get_sport(sport).pbp, **overrides}


def pbp_config(
    sport: str,
    play_dim: int,
    context: list[str] | None = None,
    opponent_strength: bool = True,
    **overrides,
) -> dict:
    """PbpModel init args for ``sport`` with ``play_dim`` features per play:
    :data:`DEFAULTS`, then ``Sport.pbp``, then ``overrides``."""
    spec = get_sport(sport)
    schema = spec.schema.with_features(context)
    settings = pbp_settings(sport, **overrides)
    dims = pbp_dims(schema, opponent_strength)
    extra, weights = output_targets(
        schema, settings["total_weight"], settings.get("stats_weight", 0.0)
    )
    d_game = settings["game_d_model"]
    return {
        "game_encoder": {
            "play_dim": play_dim,
            "max_plays": settings["max_plays"],
            "d_model": d_game,
            "nhead": settings["game_nhead"],
            "num_layers": settings["game_layers"],
            "dropout": settings["game_dropout"],
        },
        "team_encoder": {
            "token_dim": 2 * d_game + dims["extra_dim"],
            **{k: v for k, v in settings.items() if k in TEAM_KEYS},
        },
        "head": {
            "in_dim": settings["d_model"],
            "context_dim": dims["context_dim"],
            "hidden_dim": settings["d_model"],
            "dropout": settings["dropout"],
            "out_dim": 1 + len(extra),
        },
        "extra_targets": extra,
        "extra_weights": weights,
        "aux_weight": settings["aux_weight"],
        "aux_dim": 2 if schema.total else 1,
        **{k: settings[k] for k in ("lr", "weight_decay") if k in settings},
    }


def default_model(
    sport: str,
    play_dim: int,
    context: list[str] | None = None,
    opponent_strength: bool = True,
    **overrides,
) -> PbpModel:
    config = pbp_config(sport, play_dim, context, opponent_strength, **overrides)
    return PbpModel(
        game_encoder=PlayEncoder(**config.pop("game_encoder")),
        team_encoder=SequenceEncoder(**config.pop("team_encoder")),
        head=PairHead(**config.pop("head")),
        **config,
    )


def _loader(data, games, schema, rows, batch_dates, shuffle, seed):
    sampler = DateBatches(games, schema, rows, batch_dates, shuffle, seed)
    return torch.utils.data.DataLoader(
        data.with_rows(rows), sampler=sampler, batch_size=None
    )


def fit_pbp(
    games: Table,
    sport: str,
    plays: str | PlayTable | None = None,
    model: PbpModel | None = None,
    trainer: pl.Trainer | None = None,
    save_dir: str | None = None,
    context: list[str] | None = None,
    batch_dates: int = 9,
    train_seasons: list[int] | None = None,
    val_seasons: list[int] | None = None,
    test_seasons: list[int] | None = None,
    min_history: int = 1,
    opponent_strength: bool = True,
    seed: int | None = 0,
    overwrite: bool = False,
    print_metrics: bool = True,
) -> dict:
    """Train the play-by-play model (plays -> game embeddings -> team
    embeddings -> margin and total) and save it.

    Args:
        games: Processed games table.
        sport: Sport name, e.g. ``"nfl"``.
        plays: Play features (``sportsml <sport> plays``): a parquet path or
            a loaded :class:`PlayTable`. Default ``data/<sport>/plays.parquet``.
            A saved model reloads it from the path to refresh its state.
        model: Untrained :class:`PbpModel`; defaults to :func:`default_model`
            (sizes from ``Sport.pbp``).
        trainer: Lightning trainer; defaults to ``default_trainer()``.
        context: Override the sport's numeric context columns.
        batch_dates: Each training batch is every row of this many
            consecutive dates of one season.
        train_seasons / val_seasons / test_seasons: Season split; val seasons
            drive early stopping and win-probability calibration.
        min_history: Only use games where both teams have this many earlier
            games (any season).
        opponent_strength: Add each history game's pre-game Elo of both teams
            and the opponent's season-to-date margin to its token (the
            opponent's form embedding is always there).
        seed: Seed for weight initialization and batch order (None: random).

    Returns:
        ``{"predictor", "metrics", "split", "model"}``
    """
    prepare_save_dir(save_dir, overwrite)
    schema = get_sport(sport).schema.with_features(context, categorical=[])
    plays_path = plays if isinstance(plays, str) else None
    if plays is None:
        plays_path = default_plays(sport)
    settings = pbp_settings(sport)
    if not isinstance(plays, PlayTable):
        plays = PlayTable.load(plays_path, settings["max_plays"])
    games = played(read_table(games), schema)
    games = games.sort_values([schema.season, schema.date], kind="stable")
    games = games.reset_index(drop=True)
    split = split_seasons(
        games[schema.season].unique(), train_seasons, val_seasons, test_seasons
    )
    if not split.val:
        raise ValueError("pbp training needs validation seasons")

    model = model or default_model(sport, plays.play_dim, context, opponent_strength)
    form_games = settings["form_games"]
    train_games = games[games[schema.season].isin(split.train)]
    features = SequenceFeatures.fit(
        train_games,
        token_schema(schema),
        model.team_encoder.history,
        opponent_strength,
    )
    _check_dims(model, features, plays)
    extra = tuple(model.extra_targets)
    data = PbpData(games, schema, features, plays, form_games, extra)

    enough = np.ones(len(games), dtype=bool)
    if min_history > 0:
        enough &= data.history[:, min_history - 1] >= 0
        enough &= data.opp_history[:, min_history - 1] >= 0
    season = games[schema.season].to_numpy()
    rows = {
        name: np.flatnonzero(np.isin(season, seasons) & enough)
        for name in ("train", "val", "test")
        if (seasons := getattr(split, name))
    }

    seed_and_reset(model, seed)
    y = games[[schema.target, *extra]].apply(pd.to_numeric, errors="coerce")
    y = y.iloc[rows["train"]]
    if extra:
        std = y.std().replace(0, 1).fillna(1.0)
        model.set_target_scaling(y.mean().fillna(0.0).to_numpy(), std.to_numpy())
    else:
        y = y[schema.target].to_numpy(dtype=float)
        model.set_target_scaling(float(y.mean()), float(y.std()))
    aux = pd.DataFrame(data.aux_y[rows["train"]])
    model.set_aux_scaling(
        aux.mean().fillna(0.0).to_numpy(), aux.std().replace(0, 1).fillna(1.0)
    )

    trainer = trainer or default_trainer()
    trainer.fit(
        model,
        train_dataloaders=_loader(
            data, games, schema, rows["train"], batch_dates, True, seed
        ),
        val_dataloaders=_loader(
            data, games, schema, rows["val"], batch_dates, False, seed
        ),
    )
    best = best_model(trainer, model).eval()

    predicted = np.concatenate(list(rows.values()))
    with torch.no_grad():
        loader = _loader(data, games, schema, predicted, batch_dates, False, None)
        positions = np.concatenate(list(loader.sampler))
        raw = np.concatenate([best.predict_outputs(b).numpy() for b in loader])
    rows_predicted = predicted[positions]
    raw_total = None
    if schema.total and schema.total in extra:
        raw_total = raw[:, 1 + extra.index(schema.total)]
    result = finish_fit(
        PbpMatchupModel(schema, best, features, form_games, plays, plays_path),
        games,
        games.iloc[rows_predicted],
        raw[:, 0],
        split,
        sport,
        save_dir,
        print_metrics,
        raw_total=raw_total,
    )
    if trainer.logger is not None:
        trainer.logger.log_metrics(
            {
                f"final_{s}_{k}": v
                for s, m in result["metrics"].items()
                for k, v in m.items()
            }
        )
    return {**result, "model": best}


def _check_dims(model: PbpModel, features: SequenceFeatures, plays: PlayTable):
    d_game = model.game_encoder.out_dim
    expected = {
        "game_encoder play_dim": (model.game_encoder.play_dim, plays.play_dim),
        "team_encoder token_dim": (
            model.team_encoder.token_dim,
            2 * d_game + features.token_dim,
        ),
        "head context_dim": (model.head.context_dim, features.context_dim),
        "head in_dim": (model.head.in_dim, model.team_encoder.out_dim),
    }
    wrong = {k: v for k, v in expected.items() if v[0] != v[1]}
    if wrong:
        detail = ", ".join(
            f"{k}={got} (expected {want})" for k, (got, want) in wrong.items()
        )
        raise ValueError(f"model does not match the data: {detail}")
