"""Neural families with extra outputs: the total and every box-score stat."""

import numpy as np
import pandas as pd
import pytest
import torch

from sportsml.core.predictor import load_predictor
from sportsml.core.schema import mirror, played
from sportsml.models.lightning import output_targets

from .conftest import TOY_SCHEMA
from .test_gnn import quick_trainer as gnn_trainer
from .test_transformer import quick_trainer as transformer_trainer


def test_output_targets_weight_the_total_and_share_the_stats_weight():
    assert output_targets(TOY_SCHEMA) == ((), ())
    names, weights = output_targets(TOY_SCHEMA, total_weight=0.5, stats_weight=1.0)
    assert names == ("total", *TOY_SCHEMA.stats)
    assert weights[0] == 0.5
    assert sum(weights[1:]) == pytest.approx(1.0)


def fit(family, games, tmp_path, **weights):
    if family == "transformer":
        from sportsml.models.transformer import fit_transformer

        return fit_transformer(
            games, "toy", trainer=transformer_trainer(3),
            save_dir=str(tmp_path / family), print_metrics=False, **weights,
        )  # fmt: skip
    from sportsml.models.gnn import default_model, fit_gnn

    return fit_gnn(
        games, "toy", model=default_model("toy", **weights), trainer=gnn_trainer(3),
        save_dir=str(tmp_path / family), print_metrics=False,
    )  # fmt: skip


@pytest.mark.parametrize("family", ["transformer", "gnn"])
def test_total_and_stats_outputs_train_and_serve(family, toy_games, tmp_path):
    res = fit(family, toy_games, tmp_path, total_weight=1.0, stats_weight=1.0)
    predictor = res["predictor"]
    assert res["model"].n_outputs == 2 + len(TOY_SCHEMA.stats)
    assert predictor.total_sigma > 0
    assert {"total_rmse", "total_mae"} <= set(res["metrics"]["val"])

    games = played(toy_games, TOY_SCHEMA)
    last = games[games.season == 2024]
    matchups = last.drop_duplicates("game_id").head(6)
    out = predictor.predict(matchups)
    # a symmetric total, an antisymmetric margin
    flipped = predictor.predict(mirror(matchups, TOY_SCHEMA))
    np.testing.assert_allclose(out.pred_total, flipped.pred_total, atol=1e-4)
    np.testing.assert_allclose(out.pred_margin, -flipped.pred_margin, atol=1e-4)
    # toy totals are ~42: a few epochs land in the right range
    assert out.pred_total.between(20, 70).all()
    over = 1 - torch.distributions.Normal(
        torch.tensor(out.pred_total.to_numpy()), predictor.total_sigma
    ).cdf(torch.tensor(matchups["total_line"].to_numpy()))
    np.testing.assert_allclose(out.over_prob, over.numpy(), atol=1e-5)

    loaded = load_predictor(str(tmp_path / family))
    loaded.update_state(toy_games)
    predictor.update_state(toy_games)
    np.testing.assert_allclose(
        loaded.predict(matchups).pred_total, predictor.predict(matchups).pred_total,
        atol=1e-4,
    )  # fmt: skip


@pytest.mark.parametrize("family", ["transformer", "gnn"])
def test_margin_only_models_serve_no_total(family, toy_games, tmp_path):
    res = fit(family, toy_games, tmp_path)
    out = res["predictor"].predict(
        played(toy_games, TOY_SCHEMA).drop_duplicates("game_id").head(3)
    )
    assert "pred_total" not in out and "over_prob" not in out
    assert res["predictor"].total_sigma is None


def test_missing_stats_are_left_out_of_the_loss(toy_games, tmp_path):
    games = toy_games.copy()
    early = games.season == 2021
    games.loc[early, "yards"] = np.nan
    res = fit("transformer", games, tmp_path, total_weight=1.0, stats_weight=1.0)
    assert np.isfinite(res["metrics"]["train"]["rmse"])
    assert np.isfinite(res["model"].target_mean.numpy()).all()


def test_predictors_saved_before_totals_still_serve(toy_games, tmp_path):
    """A pickled margin-only module lacks the new attributes."""
    res = fit("transformer", toy_games, tmp_path)
    predictor = res["predictor"]
    module = predictor.model.module
    del module.extra_targets
    del module._buffers["loss_weights"]
    del predictor.total_sigma
    del module.head.out_dim
    matchups = pd.DataFrame({"team": ["T00"], "opp": ["T01"], "location": [1]})
    assert np.isfinite(predictor.predict(matchups).pred_margin).all()
