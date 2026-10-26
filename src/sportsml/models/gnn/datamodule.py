from __future__ import annotations

import lightning.pytorch as pl
import numpy as np
import pandas as pd
import torch
from torch_geometric.loader import DataLoader

from ...core.schema import GameSchema, played
from ...core.splits import SeasonSplit
from .dataset import SnapshotDataset
from .graph import GraphFeatures, build_graph


class GraphDataModule(pl.LightningDataModule):
    """Season snapshots for train / val / test seasons of one games table."""

    def __init__(
        self,
        games: pd.DataFrame,
        schema: GameSchema,
        split: SeasonSplit,
        batch_size: int = 8,
        num_workers: int = 0,
        min_games: int = 1,
    ):
        super().__init__()
        self.schema = schema
        self.split = split
        self.batch_size = batch_size
        self.num_workers = num_workers

        games = played(games, schema)
        games = games[games[schema.season].isin(split.all)]
        train_games = games[games[schema.season].isin(split.train)]
        self.features = GraphFeatures.fit(games, train_games, schema)
        self.graph = build_graph(games, schema, self.features, min_games)

        self.target_mean = float(train_games[schema.target].mean())
        self.target_std = float(train_games[schema.target].std())

        self.datasets = {
            name: SnapshotDataset(self.graph, seasons)
            for name in ("train", "val", "test")
            if (seasons := getattr(split, name))
        }

    def _loader(self, name: str, shuffle: bool = False) -> DataLoader:
        return DataLoader(
            self.datasets[name],
            batch_size=self.batch_size,
            shuffle=shuffle,
            num_workers=self.num_workers,
            persistent_workers=self.num_workers > 0,
        )

    def train_dataloader(self):
        return self._loader("train", shuffle=True)

    def val_dataloader(self):
        return self._loader("val")

    def test_dataloader(self):
        return self._loader("test")

    @torch.no_grad()
    def predict_targets(self, model) -> tuple[pd.DataFrame, np.ndarray]:
        """Each split's target edges with ``model``'s unscaled predictions.

        Returns played-game rows (season, game_id, target) and predictions.
        """
        model.eval()
        rows, preds = [], []
        for name in self.datasets:
            for batch in self._loader(name):
                batch = batch.to(model.device)
                preds.append(model.predict_margin(batch).cpu().numpy())
                t = batch.target
                rows.append(
                    pd.DataFrame(
                        {
                            self.schema.season: batch.season[t].cpu().numpy(),
                            self.schema.game_id: self.graph.game_ids[
                                batch.game[t].cpu().numpy()
                            ],
                            self.schema.target: batch.y[t].cpu().numpy(),
                        }
                    )
                )
        return pd.concat(rows, ignore_index=True), np.concatenate(preds)
