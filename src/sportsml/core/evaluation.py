from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .metrics import antisymmetrize, evaluate, fit_sigma, win_probability
from .schema import GameSchema
from .splits import SeasonSplit

logger = logging.getLogger(__name__)


def calibrate_and_evaluate(
    rows: pd.DataFrame, raw_pred, schema: GameSchema, split: SeasonSplit
) -> tuple[float, dict[str, dict[str, float]], np.ndarray]:
    """Shared post-fit step for every model family.

    Antisymmetrizes per-row predictions of played games, fits the win
    probability spread ``sigma`` on the validation seasons (falling back to
    test, then train) and scores every split.

    Args:
        rows: Played rows (both perspectives of each game) that were predicted.
        raw_pred: Raw margin predictions aligned with ``rows``.

    Returns:
        ``(sigma, metrics_by_split, antisymmetric_predictions)``
    """
    pred = antisymmetrize(rows, raw_pred, schema.game_id)
    y = rows[schema.target].to_numpy(dtype=float)
    seasons = rows[schema.season].to_numpy()
    masks = {
        name: np.isin(seasons, getattr(split, name)) & ~np.isnan(pred)
        for name in ("train", "val", "test")
    }

    source = next((n for n in ("val", "test", "train") if masks[n].any()), None)
    if source is None:
        raise ValueError("no predictions to calibrate on")
    if source == "train":
        logger.warning("no val/test seasons: win probabilities fit in-sample")
    sigma = fit_sigma(y[masks[source]], pred[masks[source]])

    metrics = {
        name: evaluate(y[mask], pred[mask], win_probability(pred[mask], sigma))
        for name, mask in masks.items()
        if mask.any()
    }
    return sigma, metrics, pred
