import numpy as np
import pandas as pd
import pytest
import torch

from sportsml.backtest import backtest
from sportsml.core.metrics import antisymmetrize
from sportsml.core.predictor import load_predictor
from sportsml.core.schema import played
from sportsml.models.transformer import default_model, fit_transformer
from sportsml.models.transformer.data import SequenceData
from sportsml.models.transformer.embeddings import GameEmbeddings, embedding_dim

from .conftest import TOY_SCHEMA, make_games
from .test_transformer import quick_trainer

DIM = 6


def write_embeddings(games, path, checkpoint="ckpt-a", trained_through=2022, drop=()):
    """Toy play-model vectors: each game's stats plus noise, as runitback
    writes them (one row per team per game)."""
    rng = np.random.default_rng(1)
    games = played(games, TOY_SCHEMA)
    games = games[~games.game_id.isin(drop)]
    stats = games[["points", "opp_points", "yards", "opp_yards"]].to_numpy(float)
    stats = (stats - stats.mean(0)) / stats.std(0)
    values = np.hstack([stats, rng.normal(size=(len(games), DIM - 4))])
    frame = pd.DataFrame(values, columns=[f"emb_{i}" for i in range(DIM)])
    frame.insert(0, "game_id", games.game_id.to_numpy())
    frame.insert(1, "team", games.team.to_numpy())
    frame.insert(2, "season", games.season.to_numpy())
    frame["checkpoint"] = checkpoint
    frame["in_sample"] = frame.season <= trained_through
    frame.to_parquet(path, index=False)
    return str(path)


@pytest.fixture(scope="module")
def toy_games():
    return make_games(persistence=0.7)


@pytest.fixture(scope="module")
def emb_path(toy_games, tmp_path_factory):
    return write_embeddings(toy_games, tmp_path_factory.mktemp("emb") / "games.parquet")


@pytest.fixture(scope="module")
def fitted(toy_games, emb_path, tmp_path_factory):
    save_dir = tmp_path_factory.mktemp("models") / "transformer"
    res = fit_transformer(
        toy_games,
        "toy",
        trainer=quick_trainer(10),
        batch_size=32,
        game_embeddings=emb_path,
        save_dir=str(save_dir),
        print_metrics=False,
    )
    return res, save_dir


def test_table_matches_rows_on_game_and_team(toy_games, tmp_path):
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    dropped = games.game_id.iloc[0]
    path = write_embeddings(games, tmp_path / "e.parquet", drop=[dropped])
    source = GameEmbeddings.from_file(path)
    assert (source.dim, source.checkpoint) == (DIM, "ckpt-a")
    assert embedding_dim(path) == DIM
    values, known = source.table(games, TOY_SCHEMA)
    assert values.shape == (len(games), DIM)
    assert (~known).sum() == 2 and not known[games.game_id == dropped].any()
    assert (values[~known] == 0).all()
    frame = pd.read_parquet(path).set_index(["game_id", "team"])
    row = games.iloc[5]
    np.testing.assert_allclose(
        values[5],
        frame.loc[(row.game_id, row.team)].filter(like="emb_").to_numpy(float),
        rtol=1e-6,
    )


def test_fit_with_embeddings_learns_and_round_trips(fitted, toy_games):
    res, save_dir = fitted
    assert res["model"].encoder.embedding_dim == DIM
    assert res["metrics"]["test"]["accuracy"] > 0.6
    loaded = load_predictor(str(save_dir))
    loaded.update_state(toy_games)
    matchups = pd.DataFrame(
        {"team": ["T00", "T01"], "opp": ["T01", "T00"], "location": [1, -1]}
    )
    out = loaded.predict(matchups)
    assert out.pred_margin[0] == pytest.approx(-out.pred_margin[1])


def test_served_predictions_use_the_same_vectors_as_training(fitted, toy_games):
    res, _ = fitted
    predictor, module = res["predictor"], res["model"]
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    target = games[(games.season == 2024) & (games.week == 6)]
    predictor.update_state(games[(games.season < 2024) | (games.week < 6)])
    served = predictor.predict(target)

    data = SequenceData(games, TOY_SCHEMA, predictor.model.features)
    batch = data.with_rows(target.index)[list(range(len(target)))]
    assert batch["team"]["emb_known"][~batch["team"]["pad"]].all()
    with torch.no_grad():
        raw = module.predict_margin(batch).numpy()
    expected = antisymmetrize(target, raw, TOY_SCHEMA.game_id)
    np.testing.assert_allclose(served.pred_margin, expected, atol=1e-4)


def test_vectors_change_predictions_and_missing_ones_fall_back(fitted, toy_games):
    res, _ = fitted
    module = res["model"].eval()
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    data = SequenceData(games, TOY_SCHEMA, res["predictor"].model.features)
    batch = data.with_rows(np.arange(500, 532))[list(range(32))]
    missing = {
        side: {**seq, "emb_known": torch.zeros_like(seq["emb_known"])}
        for side, seq in batch.items()
        if side in ("team", "opp")
    }
    with torch.no_grad():
        full = module.predict_margin(batch)
        fallback = module.predict_margin({**batch, **missing})
    assert torch.isfinite(fallback).all()
    assert not torch.allclose(full, fallback)


def test_refresh_from_another_checkpoints_vectors_fails(fitted, toy_games, tmp_path):
    res, _ = fitted
    model = res["predictor"].model
    source = model.features.game_embeddings
    other = write_embeddings(toy_games, tmp_path / "other.parquet", checkpoint="b")
    original = source.path
    try:
        source.path = other
        with pytest.raises(ValueError, match="retrain"):
            model.update_state(toy_games)
    finally:
        source.path = original


def test_vectors_from_a_play_model_trained_on_scored_games_are_flagged(
    toy_games, tmp_path
):
    # the play model saw 2024, the toy test season (train 2021-22, val 2023)
    path = write_embeddings(toy_games, tmp_path / "e.parquet", trained_through=2024)
    kwargs = dict(trainer=quick_trainer(1), print_metrics=False, game_embeddings=path)
    with pytest.raises(ValueError, match="training set"):
        fit_transformer(toy_games, "toy", strict_embeddings=True, **kwargs)
    with pytest.warns(UserWarning, match="training set"):
        fit_transformer(toy_games, "toy", **kwargs)


def test_model_without_embedding_input_is_reported(toy_games, emb_path):
    with pytest.raises(ValueError, match="embedding_dim"):
        fit_transformer(
            toy_games,
            "toy",
            model=default_model("toy"),
            trainer=quick_trainer(1),
            game_embeddings=emb_path,
        )


def test_backtest_reads_each_folds_own_file(toy_games, tmp_path):
    # the 2024 fold trains through 2023: its play model must not have seen 2024
    write_embeddings(toy_games, tmp_path / "cutoff_2024.parquet", trained_through=2023)
    out = backtest(
        toy_games,
        "toy",
        family="transformer",
        seasons=[2024],
        max_epochs=1,
        print_summary=False,
        game_embeddings=str(tmp_path / "cutoff_{season}.parquet"),
    )
    assert len(out["results"]) > 0

    write_embeddings(toy_games, tmp_path / "leaky_2024.parquet", trained_through=2024)
    with pytest.raises(ValueError, match="training set"):
        backtest(
            toy_games,
            "toy",
            family="transformer",
            seasons=[2024],
            max_epochs=1,
            print_summary=False,
            game_embeddings=str(tmp_path / "leaky_{season}.parquet"),
        )
