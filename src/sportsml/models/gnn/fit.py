from __future__ import annotations

import tempfile
from pathlib import Path

import lightning.pytorch as pl
import torch

from ...core.evaluation import calibrate_and_evaluate
from ...core.io import Table, read_table
from ...core.metrics import format_metrics
from ...core.predictor import Predictor, prepare_save_dir, save_predictor
from ...core.schema import played
from ...core.splits import split_seasons
from ...core.sport import get_sport
from .datamodule import GraphDataModule
from .model import GraphMatchupModel, GraphModel
from .nn.encoder.edge_conv_encoder import EdgeConvEncoder
from .nn.predictor.ffn import EdgeFFN


def graph_dims(schema) -> dict[str, int]:
    """Edge / context feature counts a GraphModel needs for ``schema``."""
    location = 1 if schema.location else 0
    return {
        "edge_dim": len(schema.stats) + location,
        "context_dim": len(schema.context) + location,
    }


ENCODER_KEYS = ("hidden_dim", "out_dim", "num_layers", "dropout", "aggr")


def gnn_config(sport: str, context: list[str] | None = None) -> dict:
    """GraphModel init args for ``sport``: EdgeConvEncoder + EdgeFFN.

    Sizes and optimizer settings come from ``Sport.gnn``; feature counts from
    the sport's schema. Used by :func:`default_model` and the CLI defaults.
    """
    spec = get_sport(sport)
    dims = graph_dims(spec.schema.with_features(context))
    settings = {"hidden_dim": 128, "out_dim": 64, "num_layers": 3, **spec.gnn}
    encoder = {k: v for k, v in settings.items() if k in ENCODER_KEYS}
    return {
        "encoder": {"edge_dim": dims["edge_dim"], **encoder},
        "predictor": {
            "in_dim": encoder["out_dim"],
            "hidden_dim": encoder["out_dim"],
            "context_dim": dims["context_dim"],
        },
        **{k: v for k, v in settings.items() if k not in ENCODER_KEYS},
    }


def default_model(sport: str, context: list[str] | None = None) -> GraphModel:
    """EdgeConvEncoder + EdgeFFN configured for ``sport`` (see ``Sport.gnn``)."""
    config = gnn_config(sport, context)
    return GraphModel(
        encoder=EdgeConvEncoder(**config.pop("encoder")),
        predictor=EdgeFFN(**config.pop("predictor")),
        **config,
    )


def default_trainer(
    max_epochs: int = 100,
    patience: int = 10,
    root_dir: str | None = None,
    **kwargs,
) -> pl.Trainer:
    """CPU or GPU (whichever is available), early stopping on val_loss.

    Checkpoints go to ``root_dir`` (default: a temporary directory; the saved
    predictor already holds the best weights). ``kwargs`` go to the Trainer.
    """
    return pl.Trainer(
        max_epochs=max_epochs,
        accelerator="auto",
        devices=1,
        logger=False,
        default_root_dir=root_dir or tempfile.mkdtemp(prefix="sportsml-"),
        callbacks=[
            pl.callbacks.EarlyStopping(monitor="val_loss", patience=patience),
            pl.callbacks.ModelCheckpoint(monitor="val_loss", mode="min"),
        ],
        **kwargs,
    )


def _best_model(trainer: pl.Trainer, model: GraphModel) -> GraphModel:
    """Fresh copy of the best (or last) weights, detached from the trainer."""
    callback = trainer.checkpoint_callback
    if callback is not None and callback.best_model_path:
        return GraphModel.load_from_checkpoint(callback.best_model_path)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "last.ckpt")
        trainer.save_checkpoint(path)
        return GraphModel.load_from_checkpoint(path)


def fit_gnn(
    games: Table,
    sport: str,
    model: GraphModel,
    trainer: pl.Trainer | None = None,
    save_dir: str | None = None,
    context: list[str] | None = None,
    batch_size: int = 8,
    num_workers: int = 0,
    train_seasons: list[int] | None = None,
    val_seasons: list[int] | None = None,
    test_seasons: list[int] | None = None,
    min_games: int = 1,
    seed: int | None = 0,
    overwrite: bool = False,
    print_metrics: bool = True,
) -> dict:
    """Train a graph model on season snapshots and save it.

    Args:
        games: Processed games table.
        sport: Sport name, e.g. ``"nfl"``.
        model: Untrained :class:`GraphModel`. Its encoder's ``edge_dim`` must
            equal the number of stats + 1 (location) and its predictor's
            ``context_dim`` the number of context columns + 1 (location).
        trainer: Lightning trainer; defaults to :func:`default_trainer`.
        context: Override the sport's numeric context columns.
        train_seasons / val_seasons / test_seasons: Season split; val seasons
            drive early stopping and win-probability calibration.
        min_games: Only predict games where both teams have played this many
            games that season.
        seed: Seed for weight initialization and batch order (None: random).

    Returns:
        ``{"predictor", "metrics", "split", "model"}``
    """
    prepare_save_dir(save_dir, overwrite)
    schema = get_sport(sport).schema.with_features(context, categorical=[])
    games = played(read_table(games), schema)
    split = split_seasons(
        games[schema.season].unique(), train_seasons, val_seasons, test_seasons
    )
    if not split.val:
        raise ValueError("GNN training needs validation seasons (early stopping)")

    data = GraphDataModule(games, schema, split, batch_size, num_workers, min_games)
    _check_dims(model, data)
    if seed is not None:
        pl.seed_everything(seed, verbose=False)
        reset_parameters(model)
    model.set_target_scaling(data.target_mean, data.target_std)

    trainer = trainer or default_trainer()
    trainer.fit(model, datamodule=data)

    best = _best_model(trainer, model)
    rows, raw = data.predict_targets(best)
    sigma, metrics, _ = calibrate_and_evaluate(rows, raw, schema, split)
    if print_metrics:
        print(format_metrics(metrics))
    if trainer.logger is not None:
        trainer.logger.log_metrics(
            {f"final_{s}_{k}": v for s, m in metrics.items() for k, v in m.items()}
        )

    matchup_model = GraphMatchupModel(schema, best, data.features)
    matchup_model.update_state(games)
    predictor = Predictor(matchup_model, sigma=sigma, sport=sport, metrics=metrics)
    if save_dir is not None:
        save_predictor(predictor, save_dir)
    return {"predictor": predictor, "metrics": metrics, "split": split, "model": best}


def reset_parameters(model: torch.nn.Module) -> None:
    """Re-initialize every layer (after seeding, makes training reproducible).

    Layers' own ``reset_parameters`` run first, then any module-level custom
    initialization (``_reset_parameters``, e.g. EdgeConvEncoderLayer's).
    """
    for module in model.modules():
        if hasattr(module, "reset_parameters"):
            module.reset_parameters()
    for module in model.modules():
        if hasattr(module, "_reset_parameters"):
            module._reset_parameters()


def _check_dims(model: GraphModel, data: GraphDataModule) -> None:
    expected = {
        "encoder edge_dim": (model.encoder.edge_dim, data.features.edge_dim),
        "predictor context_dim": (
            model.predictor.context_dim,
            data.features.context_dim,
        ),
        "predictor in_dim": (model.predictor.in_dim, model.encoder.out_dim),
    }
    wrong = {k: v for k, v in expected.items() if v[0] != v[1]}
    if wrong:
        detail = ", ".join(
            f"{k}={got} (expected {want})" for k, (got, want) in wrong.items()
        )
        raise ValueError(f"model does not match the data: {detail}")
