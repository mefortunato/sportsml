"""Model-family-agnostic prediction layer.

Every model family (sklearn, GNN, and future ones such as a transformer)
implements :class:`MatchupModel`. :class:`Predictor` wraps any of them with the
behavior every served model needs: antisymmetric margins, calibrated win
probabilities, a stable output format and MLflow persistence.
"""

from __future__ import annotations

import abc
import pathlib
import shutil
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

from .metrics import win_probability
from .schema import GameSchema, mirror


class MatchupModel(abc.ABC):
    """A fitted model that predicts the point margin of ``team`` vs ``opp``.

    Implementations keep whatever per-team state they need (season averages,
    graph embeddings, sequence encodings, ...) and rebuild it from a games
    table in :meth:`update_state`, so a saved model can be refreshed with new
    results without retraining.
    """

    schema: GameSchema

    @abc.abstractmethod
    def update_state(self, games: pd.DataFrame) -> None:
        """Rebuild per-team state from the played games in ``games``."""

    @abc.abstractmethod
    def predict_margin(self, matchups: pd.DataFrame) -> np.ndarray:
        """Raw margin for each row's ``team`` vs ``opp``.

        Rows whose teams have no state should get NaN. Callers should use
        :class:`Predictor`, which also averages in the mirrored perspective.
        """

    @property
    @abc.abstractmethod
    def teams(self) -> list:
        """Teams that currently have state, i.e. can be predicted."""


class Predictor(mlflow.pyfunc.PythonModel):
    """MLflow pyfunc model that serves any :class:`MatchupModel`.

    ``predict`` takes a DataFrame with the schema's ``team`` and ``opp``
    columns plus any pre-game columns (location, context, categorical) and
    returns it with ``pred_margin`` and ``win_prob`` appended.
    """

    def __init__(
        self,
        model: MatchupModel,
        sigma: float,
        sport: str,
        metrics: dict[str, dict[str, float]] | None = None,
    ):
        self.model = model
        self.sigma = float(sigma)
        self.sport = sport
        self.metrics = metrics or {}

    @property
    def schema(self) -> GameSchema:
        return self.model.schema

    def update_state(self, games: pd.DataFrame) -> None:
        self.model.update_state(games)

    def predict(self, model_input, params: dict[str, Any] | None = None):
        schema = self.schema
        matchups = pd.DataFrame(model_input).reset_index(drop=True)
        missing = [c for c in (schema.team, schema.opp) if c not in matchups]
        if missing:
            raise ValueError(f"matchups need columns {missing}")
        unknown = set(matchups[schema.team]) | set(matchups[schema.opp])
        unknown -= set(self.model.teams)
        if unknown:
            raise ValueError(f"no state for teams: {sorted(unknown, key=str)}")
        if schema.location and schema.location not in matchups:
            matchups[schema.location] = 0

        forward = self.model.predict_margin(matchups)
        backward = self.model.predict_margin(mirror(matchups, schema))
        margin = (np.asarray(forward) - np.asarray(backward)) / 2
        return matchups.assign(
            pred_margin=margin, win_prob=win_probability(margin, self.sigma)
        )


def prepare_save_dir(path: str | None, overwrite: bool = False) -> None:
    """Fail before training, not after, if ``path`` already holds a model."""
    if path is None:
        return
    target = pathlib.Path(path)
    if target.exists() and any(target.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"{path} already exists; pass overwrite=True to replace it"
            )
        shutil.rmtree(target)


def save_predictor(predictor: Predictor, path: str) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    mlflow.pyfunc.save_model(path, python_model=predictor)


def load_predictor(path: str) -> Predictor:
    """Load a saved model as a :class:`Predictor` (with update_state etc.)."""
    return mlflow.pyfunc.load_model(path).unwrap_python_model()
