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
    strength,
)

from .conftest import TOY_SCHEMA, make_games


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
def toy_games():
    """A league whose team strength carries over between seasons, as real
    ones do (the opponent-strength features rely on that)."""
    return make_games(persistence=0.7)


@pytest.fixture(scope="module")
def played_games(toy_games):
    return played(toy_games, TOY_SCHEMA).reset_index(drop=True)


@pytest.fixture(scope="module")
def fitted(toy_games, tmp_path_factory):
    save_dir = tmp_path_factory.mktemp("models") / "transformer"
    res = fit_transformer(
        toy_games,
        "toy",
        trainer=quick_trainer(20),
        batch_size=32,  # enough optimizer steps on a small toy league
        opponent_strength=True,
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


def test_strength_features_use_only_earlier_games(played_games):
    games = played_games
    full = strength(games, TOY_SCHEMA)
    # drop every game after 2024 week 5: features of the rest must not move
    early = games[(games.season < 2024) | (games.week < 6)]
    truncated = strength(early, TOY_SCHEMA)
    pd.testing.assert_frame_equal(full.loc[early.index], truncated)
    # Elo going into a game reflects earlier results: better teams rate higher
    gap = full["_team_elo"] - full["_opp_elo"]
    assert np.corrcoef(gap, games.margin)[0, 1] > 0.2


def test_season_decay_down_weights_earlier_seasons():
    from sportsml.models.transformer.model import SequenceEncoder

    torch.manual_seed(0)
    tokens = torch.randn(4, 6, 5)
    ago = torch.tensor([[0.0, 0, 0, 1, 1, 2]] * 4)
    pad = torch.zeros(4, 6, dtype=torch.bool)
    changed = tokens.clone()
    changed[:, 3:] += 5.0  # only last season's and older games differ

    def shift(**options):
        enc = SequenceEncoder(token_dim=5, history=6, d_model=16, nhead=2,
                              num_layers=2, dropout=0.0, **options).eval()  # fmt: skip
        with torch.no_grad():
            return (enc(tokens, ago, pad) - enc(changed, ago, pad)).abs().max()

    assert shift() > 0.1
    # a steep penalty per season leaves earlier seasons almost unseen
    assert shift(season_decay=True, season_embedding=True, decay_init=30.0) < 1e-3


def test_season_options_train_and_round_trip(toy_games, tmp_path):
    model = default_model("toy", history=10, season_embedding=True, season_decay=True)
    res = fit_transformer(
        toy_games,
        "toy",
        model=model,
        trainer=quick_trainer(2),
        save_dir=str(tmp_path / "model"),
        print_metrics=False,
    )
    encoder = res["model"].encoder
    assert encoder.history == 10 and encoder.decay is not None

    loaded = load_predictor(str(tmp_path / "model"))
    for predictor in (res["predictor"], loaded):
        predictor.update_state(toy_games)
    matchups = pd.DataFrame({"team": ["T00"], "opp": ["T03"], "location": [1]})
    np.testing.assert_allclose(
        loaded.predict(matchups).pred_margin,
        res["predictor"].predict(matchups).pred_margin,
        atol=1e-5,
    )


def test_opponent_games_are_each_tokens_opponents_earlier_games(played_games):
    features = SequenceFeatures.fit(played_games, TOY_SCHEMA, history=8)
    data = SequenceData(played_games, TOY_SCHEMA, features, opponent_games=3)
    batch = data[[100, 200]]["team"]
    rows = data.history[[100, 200]]
    index = batch["opponent_index"][rows >= 0]
    opponents = batch["opponents"]
    for row, at in zip(rows[rows >= 0].tolist(), index.tolist(), strict=True):
        game = played_games.iloc[row]
        for k in range(3):
            prior = int(data.opp_history[row, k])
            if prior < 0:
                assert opponents["pad"][at, k]
                continue
            earlier = played_games.iloc[prior]
            assert earlier.team == game.opp
            assert (earlier.season, earlier.week) < (game.season, game.week)
            assert opponents["seasons_ago"][at, k] == game.season - earlier.season


def test_opponent_games_train_and_serve_like_training(toy_games, tmp_path):
    model = default_model("toy", history=8, opponent_games=4)
    res = fit_transformer(
        toy_games,
        "toy",
        model=model,
        trainer=quick_trainer(2),
        save_dir=str(tmp_path / "model"),
        print_metrics=False,
    )
    module = res["model"]
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    target = games[(games.season == 2024) & (games.week == 6)]
    loaded = load_predictor(str(tmp_path / "model"))
    loaded.update_state(games[(games.season < 2024) | (games.week < 6)])

    features = loaded.model.features
    data = SequenceData(games, TOY_SCHEMA, features, opponent_games=4)
    batch = data.with_rows(target.index)[list(range(len(target)))]
    with torch.no_grad():
        raw = module.predict_margin(batch).numpy()
    expected = antisymmetrize(target, raw, TOY_SCHEMA.game_id)
    np.testing.assert_allclose(loaded.predict(target).pred_margin, expected, atol=1e-4)

    # the opponents' own games reach the output
    team = batch["team"]
    changed = {**team, "opponents": {**team["opponents"]}}
    changed["opponents"]["tokens"] = team["opponents"]["tokens"] + 1.0
    with torch.no_grad():
        shift = module.encoder(**changed) - module.encoder(**team)
    assert shift.abs().max() > 1e-3


def test_elo_margin_is_the_margin_elo_did_not_expect(played_games, toy_games):
    from sportsml.models.baselines import EloModel

    extra = strength(played_games, TOY_SCHEMA, opponent_strength=False, elo_margin=True)
    assert list(extra) == ["_margin_vs_elo"]
    elo = EloModel(TOY_SCHEMA)
    expected = elo.replay(played_games) * elo.params.points_per_elo
    np.testing.assert_allclose(
        extra["_margin_vs_elo"], played_games["margin"] - expected
    )
    # a game's adjustment depends only on that game and the ones before it
    early = played_games[played_games.season < 2024]
    np.testing.assert_allclose(
        strength(early, TOY_SCHEMA, False, True)["_margin_vs_elo"],
        extra.loc[early.index, "_margin_vs_elo"],
    )

    res = fit_transformer(
        toy_games, "toy", elo_margin=True, trainer=quick_trainer(1),
        print_metrics=False,
    )  # fmt: skip
    assert res["predictor"].model.features.token_columns[-1] == "_margin_vs_elo"
