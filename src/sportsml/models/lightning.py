"""Training plumbing shared by the neural model families (GNN, transformer)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import lightning.pytorch as pl
import torch
import torchmetrics


class MarginModule(pl.LightningModule):
    """A LightningModule that regresses the point margin.

    Handles target standardization, the MSE loss, metric logging, the
    optimizer and checkpoint loading. Subclasses implement ``forward(batch)``
    (scaled predictions for the batch's targets) and ``targets(batch)``,
    list their ``nn.Module`` constructor arguments in ``SUBMODULES`` (each
    with ``hparams`` including its ``cls``), and call
    ``self.save_hyperparameters(ignore=list(self.SUBMODULES))`` followed by
    ``self.save_submodules()`` at the end of ``__init__``.
    """

    SUBMODULES: tuple[str, ...] = ()

    def __init__(
        self,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        target_mean: float = 0.0,
        target_std: float = 1.0,
    ):
        super().__init__()
        self.lr = lr
        self.weight_decay = weight_decay
        self.register_buffer("target_mean", torch.tensor(target_mean))
        self.register_buffer("target_std", torch.tensor(target_std))
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

    def set_target_scaling(self, mean: float, std: float) -> None:
        """Standardize the regression target (set from the training data)."""
        self.target_mean.fill_(mean)
        self.target_std.fill_(std)
        self.hparams.update({"target_mean": mean, "target_std": std})

    def configure_optimizers(self):
        return torch.optim.Adam(
            self.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )

    def targets(self, batch) -> torch.Tensor:
        raise NotImplementedError

    def predict_margin(self, batch) -> torch.Tensor:
        return self(batch) * self.target_std + self.target_mean

    def _step(self, batch, stage: str):
        y = self.targets(batch)
        pred = self(batch)
        loss = torch.nn.functional.mse_loss(
            pred, (y - self.target_mean) / self.target_std
        )
        n = y.numel()
        self.log(f"{stage}_loss", loss, prog_bar=True, on_epoch=True, batch_size=n)
        if f"{stage}_metrics" in self.metrics:
            margin = pred * self.target_std + self.target_mean
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
