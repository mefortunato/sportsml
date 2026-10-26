from __future__ import annotations

import logging

import lightning.pytorch as pl
import numpy as np
import pandas as pd
import torch
import torchmetrics

from ...core.predictor import MatchupModel
from ...core.schema import GameSchema, played
from .graph import GraphFeatures, build_graph
from .nn.encoder.base import GraphEncoder
from .nn.predictor.ffn import EdgeFFN

logger = logging.getLogger(__name__)


class GraphModel(pl.LightningModule):
    """Encoder (past games -> team embeddings) + head (matchup -> margin).

    Trained on season snapshots: messages flow over a snapshot's games before
    its date and the head predicts the games on its date.
    """

    def __init__(
        self,
        encoder: GraphEncoder,
        predictor: EdgeFFN,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        target_mean: float = 0.0,
        target_std: float = 1.0,
    ):
        super().__init__()
        self.encoder = encoder
        self.predictor = predictor

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

        self.save_hyperparameters(ignore=["encoder", "predictor"])
        self.hparams.update(
            {"encoder": encoder.hparams, "predictor": predictor.hparams}
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

    def forward(self, graph) -> torch.Tensor:
        """Scaled predictions for ``graph``'s target edges."""
        history = ~graph.on_date
        x = self.encoder(
            edge_index=graph.edge_index[:, history],
            edge_attr=graph.edge_attr[history],
            num_nodes=graph.num_nodes,
        )
        target = graph.target
        return self.predictor(
            x, graph.edge_index[:, target], context=graph.context[target]
        ).squeeze(-1)

    def predict_margin(self, graph) -> torch.Tensor:
        return self(graph) * self.target_std + self.target_mean

    def _step(self, graph, stage: str):
        y = graph.y[graph.target]
        pred = self(graph)
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

    def training_step(self, graph, idx=None):
        return self._step(graph, "train")

    def validation_step(self, graph, idx=None):
        self._step(graph, "val")

    def test_step(self, graph, idx=None):
        self._step(graph, "test")

    @classmethod
    def load_from_checkpoint(cls, checkpoint_path: str, **kwargs):
        hparams = torch.load(checkpoint_path, weights_only=False)["hyper_parameters"]
        kwargs |= {
            key: dict(hparams[key]).pop("cls")(
                **{k: v for k, v in hparams[key].items() if k != "cls"}
            )
            for key in ("encoder", "predictor")
        }
        return super().load_from_checkpoint(
            checkpoint_path, weights_only=False, map_location="cpu", **kwargs
        )


class GraphMatchupModel(MatchupModel):
    """Serves a trained :class:`GraphModel` from current-season embeddings."""

    def __init__(self, schema: GameSchema, module: GraphModel, features: GraphFeatures):
        self.schema = schema
        self.module = module.cpu().eval()
        self.features = features
        self.embeddings: torch.Tensor | None = None
        self.active: np.ndarray = np.zeros(len(features.teams), dtype=bool)

    @torch.no_grad()
    def update_state(self, games: pd.DataFrame) -> None:
        games = played(games, self.schema)
        current = games[games[self.schema.season] == games[self.schema.season].max()]
        known = (self.features.index(current[self.schema.team]) >= 0) & (
            self.features.index(current[self.schema.opp]) >= 0
        )
        if not known.all():
            new = set(current[self.schema.team][~known]) - set(self.features.teams)
            logger.warning("skipping games of teams unseen in training: %s", new)
            current = current[known]
        graph = build_graph(current, self.schema, self.features)
        self.embeddings = self.module.encoder(
            edge_index=graph.edge_index,
            edge_attr=graph.edge_attr,
            num_nodes=graph.num_nodes,
        )
        self.active = np.zeros(len(self.features.teams), dtype=bool)
        self.active[graph.edge_index[1].numpy()] = True

    @property
    def teams(self) -> list:
        return [t for t, active in zip(self.features.teams, self.active) if active]

    @torch.no_grad()
    def predict_margin(self, matchups: pd.DataFrame) -> np.ndarray:
        if self.embeddings is None:
            raise RuntimeError("call update_state before predicting")
        team = self.features.index(matchups[self.schema.team])
        opp = self.features.index(matchups[self.schema.opp])
        edge_index = torch.from_numpy(np.stack([opp, team]))
        pred = self.module.predictor(
            self.embeddings, edge_index, context=self.features.context_tensor(matchups)
        ).squeeze(-1)
        module = self.module
        return (pred * module.target_std + module.target_mean).numpy()
