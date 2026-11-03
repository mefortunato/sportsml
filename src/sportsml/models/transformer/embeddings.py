"""Per-game team vectors from an external play-by-play model (e.g. runitback).

The file is a parquet (or csv) with one row per team per game: ``game_id``,
``team``, ``emb_0 .. emb_{n-1}`` and optionally ``checkpoint`` (an id of the
model that wrote it), ``season`` and ``in_sample`` (whether that model was
trained on the game). runitback writes it with ``runitback nfl embed``.

A vector describes how a finished game went, like the box score in a history
token, so it is only ever used for games before the one being predicted. The
leak to guard against is the play model itself: in a backtest, a model
trained on season Y's plays must not produce the vectors of season Y's games.
``check_out_of_sample`` enforces that from ``in_sample``.

The table is read again on every state refresh, so a saved model picks up
vectors for new games; it is not pickled with the model. A relative ``path``
resolves against the working directory, like the games table.
"""

from __future__ import annotations

import pathlib
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...core.schema import GameSchema

PREFIX = "emb_"


def read_embeddings(path: str) -> pd.DataFrame:
    path = pathlib.Path(path)
    if path.suffix == ".csv":
        return pd.read_csv(path, dtype={"game_id": str})
    return pd.read_parquet(path)


def embedding_columns(frame: pd.DataFrame) -> list[str]:
    cols = [c for c in frame.columns if c.startswith(PREFIX)]
    return sorted(cols, key=lambda c: int(c[len(PREFIX) :]))


def embedding_dim(path: str) -> int:
    """Number of ``emb_*`` columns in the file at ``path``."""
    import pyarrow.parquet as pq

    if pathlib.Path(path).suffix == ".csv":
        names = pd.read_csv(path, nrows=0).columns
    else:
        names = pq.read_schema(path).names
    return sum(str(c).startswith(PREFIX) for c in names)


@dataclass
class GameEmbeddings:
    """Where a model's game vectors come from; saved with the model.

    Attributes:
        path: The embeddings file.
        dim: Number of ``emb_*`` columns.
        checkpoint: The ``checkpoint`` id the model was trained with (None
            if the file has none). A refresh from a file written by another
            checkpoint fails: its vectors live in a different space.
        strict: Fail (instead of warn) when a game after ``fit_season`` was
            in the play model's training set. Backtests set it.
        fit_season: The last season the game model was trained on.
    """

    path: str
    dim: int
    checkpoint: str | None = None
    strict: bool = False
    fit_season: int | None = None

    @classmethod
    def from_file(cls, path: str, strict: bool = False) -> GameEmbeddings:
        frame = read_embeddings(path)
        dim = len(embedding_columns(frame))
        if dim == 0:
            raise ValueError(f"{path} has no {PREFIX}* columns")
        missing = {"game_id", "team"} - set(frame.columns)
        if missing:
            raise ValueError(f"{path} is missing columns {sorted(missing)}")
        ids = frame["checkpoint"].unique() if "checkpoint" in frame else []
        if len(ids) > 1:
            raise ValueError(f"{path} mixes vectors from {len(ids)} checkpoints")
        return cls(str(path), dim, str(ids[0]) if len(ids) else None, strict)

    def load(self) -> pd.DataFrame:
        frame = read_embeddings(self.path)
        if len(embedding_columns(frame)) != self.dim:
            raise ValueError(
                f"{self.path} has {len(embedding_columns(frame))} embedding "
                f"columns; the model was trained with {self.dim}"
            )
        if self.checkpoint is not None:
            ids = (
                set(frame["checkpoint"].astype(str)) if "checkpoint" in frame else set()
            )
            if ids != {self.checkpoint}:
                raise ValueError(
                    f"{self.path} was written by checkpoint(s) {sorted(ids)}, "
                    f"but the model was trained on vectors from {self.checkpoint}; "
                    "retrain the model when the play model changes"
                )
        self.check_out_of_sample(frame)
        return frame

    def check_out_of_sample(self, frame: pd.DataFrame) -> None:
        """Flag vectors of games after ``fit_season`` that the play model
        was trained on: in a backtest they leak the test season."""
        if self.fit_season is None or not {"in_sample", "season"} <= set(frame):
            return
        leaked = frame["in_sample"].astype(bool) & (frame["season"] > self.fit_season)
        if not leaked.any():
            return
        seasons = sorted(frame.loc[leaked, "season"].unique().tolist())
        message = (
            f"{leaked.sum() // 2} games of seasons {seasons} in {self.path} were "
            f"in the play model's training set, but the game model was fit "
            f"through {self.fit_season}"
        )
        if self.strict:
            raise ValueError(message + "; use a play model trained before them")
        warnings.warn(message, stacklevel=3)

    def table(
        self, games: pd.DataFrame, schema: GameSchema
    ) -> tuple[np.ndarray, np.ndarray]:
        """``(vectors [N, dim] float32, known [N] bool)`` for the rows of
        ``games``, matched on game id and team; zeros where unknown."""
        frame = self.load()
        cols = embedding_columns(frame)
        frame = frame.assign(game_id=frame["game_id"].astype(str))
        frame = frame.drop_duplicates(["game_id", "team"]).set_index(
            ["game_id", "team"]
        )
        keys = pd.MultiIndex.from_arrays(
            [
                games[schema.game_id].astype(str).to_numpy(),
                games[schema.team].to_numpy(),
            ]
        )
        values = frame[cols].reindex(keys).to_numpy(dtype=np.float32)
        known = ~np.isnan(values).any(axis=1)
        return np.nan_to_num(values), known
