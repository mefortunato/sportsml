from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch

from ...core.predictor import MatchupModel
from ...core.schema import GameSchema, played
from ..lightning import MarginModule
from .graph import GraphFeatures, build_graph
from .nn.encoder.base import GraphEncoder
from .nn.predictor.ffn import EdgeFFN

logger = logging.getLogger(__name__)


class GraphModel(MarginModule):
    """Encoder (past games -> team embeddings) + head (matchup -> margin).

    Trained on season snapshots: messages flow over a snapshot's games before
    its date and the head predicts the games on its date.
    """

    SUBMODULES = ("encoder", "predictor")

    def __init__(
        self,
        encoder: GraphEncoder,
        predictor: EdgeFFN,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        target_mean: float = 0.0,
        target_std: float = 1.0,
    ):
        super().__init__(lr, weight_decay, target_mean, target_std)
        self.encoder = encoder
        self.predictor = predictor
        self.save_hyperparameters(ignore=list(self.SUBMODULES))
        self.save_submodules()

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

    def targets(self, graph) -> torch.Tensor:
        return graph.y[graph.target]


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
