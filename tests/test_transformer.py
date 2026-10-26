import tempfile

import lightning.pytorch as pl
import numpy as np
import pandas as pd
import pytest
import torch

from sportsml.core.metrics import antisymmetrize
from sportsml.core.predictor import load_predictor
from sportsml.core.schema import played
from sportsml.models.transformer import default_model, fit_transformer
from sportsml.models.transformer.data import (
    SequenceData,
    SequenceFeatures,
    histories,
    opponent_rows,
)

from .conftest import TOY_SCHEMA


def quick_trainer(max_epochs=8):
    return pl.Trainer(
        max_epochs=max_epochs,
        default_root_dir=tempfile.mkdtemp(),
        accelerator="cpu",
        logger=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        callbacks=[pl.callbacks.ModelCheckpoint(monitor="val_loss", mode="min")],
    )


@pytest.fixture(scope="module")
def played_games(toy_games):
    return played(toy_games, TOY_SCHEMA).reset_index(drop=True)


@pytest.fixture(scope="module")
def fitted(toy_games, tmp_path_factory):
    save_dir = tmp_path_factory.mktemp("models") / "transformer"
    res = fit_transformer(
        toy_games,
        "toy",
        trainer=quick_trainer(),
        save_dir=str(save_dir),
        print_metrics=False,
    )
    return res, save_dir


def test_histories_are_earlier_games_of_the_same_team(played_games):
    games = played_games
    hist = histories(games, TOY_SCHEMA, history=8)
    for row in [0, 100, 500, len(games) - 1]:
        idx = hist[row][hist[row] >= 0]
        earlier = games.iloc[idx]
        now = (games.season[row], games.week[row])
        assert (earlier.team == games.team[row]).all()
        when = list(zip(earlier.season, earlier.week))
        assert all(w < now for w in when)
        assert when == sorted(when, reverse=True)  # most recent first
        team = games[games.team == games.team[row]]
        n_before = sum(w < now for w in zip(team.season, team.week))
        assert len(idx) == min(8, n_before)


def test_histories_cross_seasons_and_opponent_rows_pair_up(played_games):
    hist = histories(played_games, TOY_SCHEMA, history=8)
    opener = played_games[(played_games.season == 2022) & (played_games.week == 1)]
    row = opener.index[0]
    assert (played_games.season.iloc[hist[row]] == 2021).all()  # all last season

    opp = opponent_rows(played_games, TOY_SCHEMA)
    assert (played_games.team.iloc[opp].to_numpy() == played_games.opp.to_numpy()).all()
    assert (
        played_games.game_id.iloc[opp].to_numpy() == played_games.game_id.to_numpy()
    ).all()


@pytest.mark.parametrize("week", [1, 6])
def test_served_predictions_match_training_path(fitted, toy_games, week):
    """Serving rebuilds the same sequences training saw, including openers."""
    res, _ = fitted
    predictor, module = res["predictor"], res["model"]
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    target = games[(games.season == 2024) & (games.week == week)]

    predictor.update_state(games[(games.season < 2024) | (games.week < week)])
    served = predictor.predict(target)

    features = predictor.model.features
    data = SequenceData(games, TOY_SCHEMA, features).with_rows(target.index)
    with torch.no_grad():
        raw = module.predict_margin(data[list(range(len(target)))]).numpy()
    expected = antisymmetrize(target, raw, TOY_SCHEMA.game_id)
    np.testing.assert_allclose(served.pred_margin, expected, atol=1e-4)


def test_learns_and_round_trips(fitted, toy_games):
    res, save_dir = fitted
    assert res["metrics"]["test"]["accuracy"] > 0.6

    loaded = load_predictor(str(save_dir))
    loaded.update_state(toy_games)
    matchups = pd.DataFrame(
        {"team": ["T00", "T01"], "opp": ["T01", "T00"], "location": [1, -1]}
    )
    out = loaded.predict(matchups)
    assert out.pred_margin[0] == pytest.approx(-out.pred_margin[1])
    assert np.isfinite(out.win_prob).all()


def test_seeded_fits_are_reproducible(toy_games):
    def fit():
        res = fit_transformer(
            toy_games, "toy", trainer=quick_trainer(2), print_metrics=False
        )
        return res["metrics"]["val"]

    assert fit() == fit()


def test_mismatched_model_dims_are_reported(toy_games):
    with pytest.raises(ValueError, match="context_dim"):
        fit_transformer(
            toy_games,
            "toy",
            model=default_model("toy", context=[]),
            trainer=quick_trainer(1),
        )


def test_features_standardize_on_training_games(played_games):
    features = SequenceFeatures.fit(played_games, TOY_SCHEMA, history=8)
    tokens = features.tokens(played_games)
    assert tokens.shape == (len(played_games), features.token_dim)
    np.testing.assert_allclose(tokens.mean(axis=0), 0, atol=1e-4)
