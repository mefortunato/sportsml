from __future__ import annotations

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
from .data import SequenceData, SequenceFeatures, extra_columns
from .model import PairHead, SequenceEncoder, TransformerMatchupModel, TransformerModel

ENCODER_KEYS = (
    "history", "d_model", "nhead", "num_layers", "dropout",
    "season_embedding", "season_decay", "max_seasons_ago", "decay_init",
)  # fmt: skip


def transformer_dims(
    schema: GameSchema, opponent_strength: bool = False, elo_margin: bool = False
) -> dict[str, int]:
    """Token / context feature counts a TransformerModel needs for ``schema``."""
    location = [schema.location] if schema.location else []
    tokens = list(dict.fromkeys([*schema.stats, schema.target, *location]))
    tokens += extra_columns(opponent_strength, elo_margin)
    return {
        "token_dim": len(tokens),
        "context_dim": len(schema.context) + len(location),
    }


def transformer_config(
    sport: str,
    context: list[str] | None = None,
    opponent_strength: bool = False,
    elo_margin: bool = False,
    total_weight: float | None = None,
    stats_weight: float | None = None,
    **overrides,
) -> dict:
    """TransformerModel init args for ``sport``: sizes from
    ``Sport.transformer``, then ``overrides`` (any encoder arg, e.g.
    ``history=34, season_decay=True``, or ``lr``).

    ``total_weight`` / ``stats_weight`` add the total and every box-score
    stat as extra outputs with those loss weights (see
    :func:`~sportsml.models.lightning.output_targets`); None takes the
    sport's ``Sport.transformer`` setting (default 0, off). With
    ``distribution=True`` (an override or ``Sport.transformer`` key) the
    model predicts a :class:`~sportsml.models.lightning.ScoreDistribution`
    of the margin (and the total) instead of point values."""
    spec = get_sport(sport)
    dims = transformer_dims(
        spec.schema.with_features(context), opponent_strength, elo_margin
    )
    settings = {
        "history": 20,
        "d_model": 64,
        "nhead": 4,
        "num_layers": 2,
        "dropout": 0.1,
        **spec.transformer,
        **overrides,
    }
    if total_weight is None:
        total_weight = settings.get("total_weight", 0.0)
    if stats_weight is None:
        stats_weight = settings.get("stats_weight", 0.0)
    distribution = bool(settings.get("distribution", False))
    output_keys = ("total_weight", "stats_weight", "distribution")
    settings = {k: v for k, v in settings.items() if k not in output_keys}
    extra, weights = output_targets(spec.schema, total_weight, stats_weight)
    outputs = 1 + len(extra)
    encoder = {k: v for k, v in settings.items() if k in ENCODER_KEYS}
    return {
        "encoder": {"token_dim": dims["token_dim"], **encoder},
        "head": {
            "in_dim": encoder["d_model"],
            "context_dim": dims["context_dim"],
            "hidden_dim": encoder["d_model"],
            "dropout": encoder["dropout"],
            "out_dim": 2 * outputs if distribution else outputs,
        },
        "extra_targets": extra,
        "extra_weights": weights,
        "distribution": distribution,
        **{k: v for k, v in settings.items() if k not in ENCODER_KEYS},
    }


def default_model(
    sport: str,
    context: list[str] | None = None,
    opponent_strength: bool = False,
    elo_margin: bool = False,
    total_weight: float | None = None,
    stats_weight: float | None = None,
    **overrides,
) -> TransformerModel:
    config = transformer_config(
        sport,
        context,
        opponent_strength,
        elo_margin,
        total_weight,
        stats_weight,
        **overrides,
    )
    return TransformerModel(
        encoder=SequenceEncoder(**config.pop("encoder")),
        head=PairHead(**config.pop("head")),
        **config,
    )


def _loader(data: SequenceData, batch_size: int, shuffle: bool, num_workers: int):
    sampler = torch.utils.data.BatchSampler(
        torch.utils.data.RandomSampler(data)
        if shuffle
        else torch.utils.data.SequentialSampler(data),
        batch_size=batch_size,
        drop_last=False,
    )
    return torch.utils.data.DataLoader(
        data,
        sampler=sampler,
        batch_size=None,
        num_workers=num_workers,
        persistent_workers=num_workers > 0,
    )


def fit_transformer(
    games: Table,
    sport: str,
    model: TransformerModel | None = None,
    trainer: pl.Trainer | None = None,
    save_dir: str | None = None,
    context: list[str] | None = None,
    batch_size: int = 256,
    num_workers: int = 0,
    train_seasons: list[int] | None = None,
    val_seasons: list[int] | None = None,
    test_seasons: list[int] | None = None,
    min_history: int = 1,
    opponent_strength: bool = False,
    elo_margin: bool = False,
    total_weight: float | None = None,
    stats_weight: float | None = None,
    seed: int | None = 0,
    overwrite: bool = False,
    print_metrics: bool = True,
) -> dict:
    """Train a transformer over each team's recent games and save it.

    Args:
        games: Processed games table.
        sport: Sport name, e.g. ``"nfl"``.
        model: Untrained :class:`TransformerModel`; defaults to
            :func:`default_model`. Its sequence length is the encoder's
            ``history``.
        trainer: Lightning trainer; defaults to ``default_trainer()``.
        context: Override the sport's numeric context columns.
        train_seasons / val_seasons / test_seasons: Season split; val seasons
            drive early stopping and win-probability calibration.
        min_history: Only use games where both teams have this many earlier
            games (any season).
        opponent_strength: Add each history game's pre-game Elo of both teams
            and the opponent's season-to-date margin to its token. Off by
            default: on NFL 2021-2025 it did not change the backtest Brier
            (+0.0002 +/- 0.0027) and makes state refreshes slower.
        elo_margin: Add each history game's margin minus the margin pre-game
            Elo expected, so a result is read against the opponent's rating.
        total_weight / stats_weight: Also regress the total (served as
            ``pred_total``) and every box-score stat, with these loss
            weights (None: the sport's ``Sport.transformer`` setting). Used
            to build the default model; ignored with ``model``.
        seed: Seed for weight initialization and batch order (None: random).

    Returns:
        ``{"predictor", "metrics", "split", "model"}``
    """
    prepare_save_dir(save_dir, overwrite)
    schema = get_sport(sport).schema.with_features(context, categorical=[])
    games = played(read_table(games), schema).reset_index(drop=True)
    split = split_seasons(
        games[schema.season].unique(), train_seasons, val_seasons, test_seasons
    )
    if not split.val:
        raise ValueError("transformer training needs validation seasons")

    model = model or default_model(
        sport,
        context,
        opponent_strength,
        elo_margin,
        total_weight=total_weight,
        stats_weight=stats_weight,
    )
    train_games = games[games[schema.season].isin(split.train)]
    features = SequenceFeatures.fit(
        train_games, schema, model.encoder.history, opponent_strength, elo_margin
    )
    _check_dims(model, features)
    extra = tuple(model.extra_targets)
    data = SequenceData(games, schema, features, extra_targets=extra)

    enough = np.ones(len(games), dtype=bool)
    if min_history > 0:
        enough &= (data.history[:, min_history - 1] >= 0).numpy()
        enough &= (data.opp_history[:, min_history - 1] >= 0).numpy()
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

    trainer = trainer or default_trainer()
    trainer.fit(
        model,
        train_dataloaders=_loader(
            data.with_rows(rows["train"]), batch_size, True, num_workers
        ),
        val_dataloaders=_loader(
            data.with_rows(rows["val"]), batch_size, False, num_workers
        ),
    )
    best = best_model(trainer, model).eval()

    predicted = np.concatenate(list(rows.values()))
    with torch.no_grad():
        raw = np.concatenate(
            [
                best.predict_outputs(batch).numpy()
                for batch in _loader(data.with_rows(predicted), 4096, False, 0)
            ]
        )
    raw_total = None
    if schema.total and schema.total in extra:
        raw_total = raw[:, 1 + extra.index(schema.total)]
    result = finish_fit(
        TransformerMatchupModel(schema, best, features),
        games,
        games.iloc[predicted],
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


def _check_dims(model: TransformerModel, features: SequenceFeatures) -> None:
    expected = {
        "encoder token_dim": (model.encoder.token_dim, features.token_dim),
        "head context_dim": (model.head.context_dim, features.context_dim),
        "head in_dim": (model.head.in_dim, model.encoder.out_dim),
    }
    wrong = {k: v for k, v in expected.items() if v[0] != v[1]}
    if wrong:
        detail = ", ".join(
            f"{k}={got} (expected {want})" for k, (got, want) in wrong.items()
        )
        raise ValueError(f"model does not match the data: {detail}")
