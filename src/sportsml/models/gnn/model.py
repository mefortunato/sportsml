from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch

from ...core.predictor import MatchupModel
from ...core.schema import GameSchema, played
from ..lightning import MarginModule
from .graph import GraphFeatures, build_graph, edge_time
from .nn.encoder.base import GraphEncoder
from .nn.predictor.ffn import EdgeFFN

logger = logging.getLogger(__name__)


class GraphModel(MarginModule):
    """Encoder (past games -> team embeddings) + head (matchup -> margin).

    Trained on season snapshots: messages flow over a snapshot's games before
    its date and the head predicts the games on its date.

    Args:
        carry_seasons: Snapshots also hold this many earlier seasons' games,
            each edge with its age (in seasons) and how many seasons back it
            is as two extra edge features, so the encoder learns how fast to
            discount old games and season openers have a full season to go
            on. 0: the snapshot's season only.
        off_def: Each team is an offense node (``i``) and a defense node
            (``num_teams + i``): a game's stats flow from the opponent's
            defense to the team's offense and back, with a role feature
            telling the two directions apart. Needs a head that reads node
            pairs (:class:`~.nn.predictor.mirrored.MirroredHead`).
    """

    SUBMODULES = ("encoder", "predictor")

    def __init__(
        self,
        encoder: GraphEncoder,
        predictor: EdgeFFN,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        target_mean: float | list[float] = 0.0,
        target_std: float | list[float] = 1.0,
        extra_targets: tuple[str, ...] = (),
        extra_weights: tuple[float, ...] = (),
        carry_seasons: int = 0,
        off_def: bool = False,
    ):
        super().__init__(
            lr, weight_decay, target_mean, target_std, extra_targets, extra_weights
        )
        self.encoder = encoder
        self.predictor = predictor
        self.carry_seasons = carry_seasons
        self.off_def = off_def
        self.save_hyperparameters(ignore=list(self.SUBMODULES))
        self.save_submodules()

    def encode(
        self,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        num_teams: int,
        time: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Node embeddings from played-game edges (opponent -> team)."""
        if self.carry_seasons:
            edge_attr = torch.cat([edge_attr, time], dim=-1)
        num_nodes = num_teams
        if self.off_def:
            opp, team = edge_index
            # the opponent's defense -> the team's offense, and back
            edge_index = torch.cat(
                [
                    torch.stack([num_teams + opp, team]),
                    torch.stack([team, num_teams + opp]),
                ],
                dim=1,
            )
            role = torch.zeros(2 * len(edge_attr), 1, device=edge_attr.device)
            role[len(edge_attr) :] = 1
            edge_attr = torch.cat([edge_attr.repeat(2, 1), role], dim=-1)
            num_nodes = 2 * num_teams
        return self.encoder(
            edge_index=edge_index, edge_attr=edge_attr, num_nodes=num_nodes
        )

    def forward(self, graph) -> torch.Tensor:
        """Scaled predictions for ``graph``'s target edges."""
        history = ~graph.on_date
        x = self.encode(
            graph.edge_index[:, history],
            graph.edge_attr[history],
            graph.num_nodes,
            graph.edge_time[history] if self.carry_seasons else None,
        )
        target = graph.target
        out = self.predictor(
            x, graph.edge_index[:, target], context=graph.context[target]
        )
        return out.squeeze(-1) if self.n_outputs == 1 else out

    def targets(self, graph) -> torch.Tensor:
        return graph.y[graph.target]


class GraphMatchupModel(MatchupModel):
    """Serves a trained :class:`GraphModel` from current-season embeddings.

    With ``carry_seasons`` the embeddings are computed per request, at the
    matchup's season and date (a season opener sees last season's games as
    old as in training).
    """

    def __init__(self, schema: GameSchema, module: GraphModel, features: GraphFeatures):
        self.schema = schema
        self.module = module.cpu().eval()
        self.features = features
        self.embeddings: torch.Tensor | None = None
        self.active: np.ndarray = np.zeros(len(features.teams), dtype=bool)
        self.games: pd.DataFrame | None = None
        self._cache: dict = {}

    @property
    def carry(self) -> int:
        return getattr(self.module, "carry_seasons", 0)

    @torch.no_grad()
    def update_state(self, games: pd.DataFrame) -> None:
        s = self.schema
        games = played(games, s)
        latest = games[s.season].max()
        current = games[games[s.season] >= latest - self.carry]
        known = (self.features.index(current[s.team]) >= 0) & (
            self.features.index(current[s.opp]) >= 0
        )
        if not known.all():
            new = set(current[s.team][~known]) - set(self.features.teams)
            logger.warning("skipping games of teams unseen in training: %s", new)
            current = current[known]
        self.games = current
        self._cache = {}
        graph = build_graph(current, s, self.features)
        self.active = np.zeros(len(self.features.teams), dtype=bool)
        self.active[graph.edge_index.flatten().numpy()] = True
        if not self.carry:
            self.embeddings = self._encode(graph)
        else:
            self.embeddings = self._embeddings(latest, None)

    def _encode(self, graph, time=None) -> torch.Tensor:
        return self.module.encode(
            graph.edge_index, graph.edge_attr, graph.num_nodes, time
        )

    def _embeddings(self, season, date) -> torch.Tensor:
        """Embeddings for games of ``season`` on ``date`` (None: after the
        last played game), from the games before it."""
        s = self.schema
        games = self.games
        if date is None or pd.isna(date):
            same = games.loc[games[s.season] == season, s.date]
            date = same.max() + 1 if len(same) else games[s.date].min()
        key = (season, date)
        if key not in self._cache:
            before = games[
                (games[s.season] >= season - self.carry)
                & ((games[s.season] < season) | (games[s.date] < date))
            ]
            graph = build_graph(before, s, self.features)
            time = edge_time(graph, season, date, self.features.season_length)
            self._cache[key] = self._encode(graph, time)
        return self._cache[key]

    @property
    def teams(self) -> list:
        return [t for t, active in zip(self.features.teams, self.active) if active]

    def predict_margin(self, matchups: pd.DataFrame) -> np.ndarray:
        return self.predict_outputs(matchups)["margin"]

    @torch.no_grad()
    def predict_outputs(self, matchups: pd.DataFrame) -> dict[str, np.ndarray]:
        if self.embeddings is None:
            raise RuntimeError("call update_state before predicting")
        s = self.schema
        team = self.features.index(matchups[s.team])
        opp = self.features.index(matchups[s.opp])
        context = self.features.context_tensor(matchups)
        module = self.module
        pred = torch.zeros(len(matchups), module.n_outputs)
        if not self.carry:
            groups = [(self.embeddings, np.arange(len(matchups)))]
        else:
            latest = self.games[s.season].max()
            season = matchups[s.season] if s.season in matchups else latest
            date = matchups[s.date] if s.date in matchups else None
            keys = pd.DataFrame(
                {"season": season, "date": date}, index=matchups.index
            ).reset_index(drop=True)
            groups = [
                (self._embeddings(*key), rows)
                for key, rows in keys.groupby(
                    ["season", "date"], dropna=False
                ).indices.items()
            ]
        for x, rows in groups:
            edge_index = torch.from_numpy(np.stack([opp[rows], team[rows]]))
            out = module.predictor(x, edge_index, context=context[rows])
            pred[rows] = out.reshape(len(rows), -1)
        out = (pred * module.target_std + module.target_mean).numpy()
        extra = getattr(module, "extra_targets", ())
        result = {"margin": out[:, 0]}
        total = s.total
        if total and total in extra:
            result["total"] = out[:, 1 + extra.index(total)]
        return result
