"""Training plumbing shared by the neural model families (GNN, transformer)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import lightning.pytorch as pl
import numpy as np
import torch
import torchmetrics


def output_targets(
    schema, total_weight: float = 0.0, stats_weight: float = 0.0
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Targets a neural model regresses besides the margin, and their loss
    weights: the total (``schema.total``) with ``total_weight`` and every
    box-score stat with ``stats_weight`` shared between them (each stat's
    loss is averaged, so the weight does not grow with the number of stats).
    """
    names, weights = [], []
    if total_weight:
        if not schema.total:
            raise ValueError("the sport's schema has no total column")
        names.append(schema.total)
        weights.append(float(total_weight))
    if stats_weight:
        stats = [c for c in schema.stats if c not in names]
        names += stats
        weights += [float(stats_weight) / len(stats)] * len(stats)
    return tuple(names), tuple(weights)


class MarginModule(pl.LightningModule):
    """A LightningModule that regresses the point margin, optionally with
    more targets (``extra_targets``: e.g. the total and box-score stats).

    Handles per-target standardization, the (NaN-masked) MSE loss, metric
    logging, the optimizer and checkpoint loading. The loss is the margin's
    MSE plus each extra target's MSE times its ``extra_weights`` entry.
    Subclasses implement ``forward(batch)`` (scaled predictions: ``[B]`` for
    the margin alone, else ``[B, 1 + len(extra_targets)]`` with the margin
    first) and ``targets(batch)`` (the same shape, unscaled), list their
    ``nn.Module`` constructor arguments in ``SUBMODULES`` (each with
    ``hparams`` including its ``cls``), and call
    ``self.save_hyperparameters(ignore=list(self.SUBMODULES))`` followed by
    ``self.save_submodules()`` at the end of ``__init__``.
    """

    SUBMODULES: tuple[str, ...] = ()

    def __init__(
        self,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        target_mean: float | list[float] = 0.0,
        target_std: float | list[float] = 1.0,
        extra_targets: tuple[str, ...] = (),
        extra_weights: tuple[float, ...] = (),
    ):
        super().__init__()
        if len(extra_weights) != len(extra_targets):
            raise ValueError("extra_weights needs one weight per extra target")
        self.lr = lr
        self.weight_decay = weight_decay
        self.extra_targets = tuple(extra_targets)
        n = 1 + len(self.extra_targets)
        mean = torch.as_tensor(target_mean, dtype=torch.float32)
        std = torch.as_tensor(target_std, dtype=torch.float32)
        if n > 1:
            mean, std = mean.expand(n).clone(), std.expand(n).clone()
        self.register_buffer("target_mean", mean)
        self.register_buffer("target_std", std)
        self.register_buffer(
            "loss_weights", torch.tensor([1.0, *extra_weights], dtype=torch.float32)
        )
        self.metrics = torch.nn.ModuleDict(
            {
                stage: torch.nn.ModuleDict(
                    {
                        "rmse": torchmetrics.MeanSquaredError(squared=False),
                        "mae": torchmetrics.MeanAbsoluteError(),
                        "accuracy": torchmetrics.Accuracy(task="binary"),
                    }
                )
                for stage in ("train_metrics", "val_metrics")
            }
        )

    def save_submodules(self) -> None:
        self.hparams.update(
            {key: getattr(self, key).hparams for key in self.SUBMODULES}
        )

    @property
    def n_outputs(self) -> int:
        return 1 + len(getattr(self, "extra_targets", ()))

    def set_target_scaling(self, mean, std) -> None:
        """Standardize the regression targets (set from the training data):
        scalars for the margin alone, else one value per output."""
        mean = torch.as_tensor(np.asarray(mean, dtype=np.float32))
        std = torch.as_tensor(np.asarray(std, dtype=np.float32))
        self.target_mean.copy_(mean.reshape(self.target_mean.shape))
        self.target_std.copy_(std.reshape(self.target_std.shape))
        self.hparams.update({"target_mean": mean.tolist(), "target_std": std.tolist()})

    def configure_optimizers(self):
        return torch.optim.Adam(
            self.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )

    def targets(self, batch) -> torch.Tensor:
        raise NotImplementedError

    def predict_outputs(self, batch) -> torch.Tensor:
        """Unscaled predictions, ``[B, n_outputs]`` (margin first)."""
        pred = self(batch)
        if pred.dim() == 1:
            pred = pred[:, None]
        return pred * self.target_std + self.target_mean

    def predict_margin(self, batch) -> torch.Tensor:
        return self.predict_outputs(batch)[:, 0]

    def _step(self, batch, stage: str):
        y = self.targets(batch)
        pred = self(batch)
        if y.dim() == 1:
            y, pred = y[:, None], pred[:, None]
        z = (y - self.target_mean) / self.target_std
        known = ~torch.isnan(z)
        error = (pred - torch.nan_to_num(z)) ** 2 * known
        per_target = error.sum(0) / known.sum(0).clamp(min=1)
        weights = getattr(self, "loss_weights", None)
        loss = per_target[0] if weights is None else (per_target * weights).sum()
        n = len(y)
        self.log(f"{stage}_loss", loss, prog_bar=True, on_epoch=True, batch_size=n)
        if y.shape[1] > 1:
            self.log(f"{stage}_margin_loss", per_target[0], on_epoch=True, batch_size=n)
        y = y[:, 0]
        if f"{stage}_metrics" in self.metrics:
            margin = (pred * self.target_std + self.target_mean)[:, 0]
            metrics = self.metrics[f"{stage}_metrics"]
            metrics["rmse"].update(margin, y)
            metrics["mae"].update(margin, y)
            metrics["accuracy"].update((margin > 0).int(), (y > 0).int())
            for name, metric in metrics.items():
                self.log(f"{stage}_{name}", metric, on_epoch=True, batch_size=n)
        return loss

    def training_step(self, batch, idx=None):
        return self._step(batch, "train")

    def validation_step(self, batch, idx=None):
        self._step(batch, "val")

    def test_step(self, batch, idx=None):
        self._step(batch, "test")

    @classmethod
    def load_from_checkpoint(cls, checkpoint_path: str, **kwargs):
        hparams = torch.load(checkpoint_path, weights_only=False)["hyper_parameters"]
        kwargs |= {
            key: hparams[key]["cls"](
                **{k: v for k, v in hparams[key].items() if k != "cls"}
            )
            for key in cls.SUBMODULES
        }
        return super().load_from_checkpoint(
            checkpoint_path, weights_only=False, map_location="cpu", **kwargs
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


def best_model(trainer: pl.Trainer, model: MarginModule) -> MarginModule:
    """Fresh copy of the best (or last) weights, detached from the trainer."""
    callback = trainer.checkpoint_callback
    if callback is not None and callback.best_model_path:
        return type(model).load_from_checkpoint(callback.best_model_path)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "last.ckpt")
        trainer.save_checkpoint(path)
        return type(model).load_from_checkpoint(path)


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


def seed_and_reset(model: torch.nn.Module, seed: int | None) -> None:
    if seed is not None:
        pl.seed_everything(seed, verbose=False)
        reset_parameters(model)
