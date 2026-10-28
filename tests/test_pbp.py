import numpy as np
import pandas as pd
import pytest
import torch

from sportsml.core.metrics import antisymmetrize
from sportsml.core.predictor import load_predictor
from sportsml.core.schema import one_row_per_game, played
from sportsml.models.pbp import PlayTable, fit_pbp
from sportsml.models.pbp.data import PbpData, date_batches

from .conftest import TOY_SCHEMA, make_games
from .test_transformer import quick_trainer


def make_plays(games: pd.DataFrame, plays_per_game: int = 24, seed: int = 0):
    """Plays of every played toy game, written from the home side: the
    teams alternate possessions; yards and points add up to the box score."""
    rng = np.random.default_rng(seed)
    rows = []
    for game in one_row_per_game(played(games, TOY_SCHEMA), TOY_SCHEMA).itertuples():
        n = plays_per_game + int(rng.integers(-4, 5))
        offense = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
        mine = offense > 0
        yards = np.where(mine, game.yards / mine.sum(), -game.opp_yards / (~mine).sum())
        points = np.zeros(n)
        points[mine] = game.points / mine.sum()
        points[~mine] = -game.opp_points / (~mine).sum()
        for i in range(n):
            rows.append(
                {
                    "game_id": game.game_id,
                    "home_team": game.team,
                    "away_team": game.opp,
                    "offense": offense[i],
                    "yards": (yards[i] + rng.normal(0, 2)) / 10,
                    "points": points[i] / 7,
                    "quarter": 1 + 4 * i // n,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def toy_games():
    return make_games(persistence=0.7)


@pytest.fixture(scope="module")
def plays_file(toy_games, tmp_path_factory):
    path = tmp_path_factory.mktemp("plays") / "plays.parquet"
    make_plays(toy_games).to_parquet(path, index=False)
    return str(path)


@pytest.fixture(scope="module")
def fitted(toy_games, plays_file, tmp_path_factory):
    save_dir = tmp_path_factory.mktemp("models") / "pbp"
    res = fit_pbp(
        toy_games,
        "toy",
        plays=plays_file,
        trainer=quick_trainer(15),
        batch_dates=2,
        save_dir=str(save_dir),
        print_metrics=False,
    )
    return res, save_dir


def test_play_table_pads_truncates_and_finds_sides(toy_games, plays_file):
    table = PlayTable.load(plays_file, max_plays=22)
    plays = pd.read_parquet(plays_file)
    count = plays.groupby("game_id").size()
    assert ((~table.pad).sum(1).numpy() == count[table.game_ids].clip(upper=22)).all()
    first = plays[plays.game_id == plays.game_id.iloc[-1]]
    i = table.index[first.game_id.iloc[0]]
    np.testing.assert_allclose(
        table.plays[i, : len(first)].numpy(),
        first[table.columns].head(22).to_numpy(),
        atol=1e-6,
    )

    games = played(toy_games, TOY_SCHEMA)
    slot = table.sides(games, TOY_SCHEMA)
    assert (slot >= 0).all()
    home = games.location.to_numpy() == 1
    assert (slot[home] % 2 == 0).all()  # the home row reads the home side
    assert (table.game_ids[slot // 2] == games.game_id.to_numpy()).all()
    unknown = games.assign(game_id="nope").head(3)
    assert (table.sides(unknown, TOY_SCHEMA) == -1).all()


def test_batches_only_encode_earlier_games(fitted, toy_games):
    res, _ = fitted
    model = res["predictor"].model
    games = played(toy_games, TOY_SCHEMA)
    games = games.sort_values(["season", "week"], kind="stable").reset_index(drop=True)
    when = games.drop_duplicates("game_id").set_index("game_id")[["season", "week"]]
    data = PbpData(games, TOY_SCHEMA, model.features, model._plays, form_games=4)
    for row in [100, 500, len(games) - 1]:
        batch = data[[row]]
        encoded = when.loc[model._plays.game_ids[batch["games"].numpy()]]
        assert len(encoded) > 8  # both teams' histories and the opponents' form
        now = (games.season[row], games.week[row])
        assert all(w < now for w in encoded.itertuples(index=False, name=None))


def test_date_batches_group_consecutive_dates(toy_games):
    games = played(toy_games, TOY_SCHEMA).reset_index(drop=True)
    rows = np.flatnonzero(games.season >= 2023)
    batches = date_batches(games, TOY_SCHEMA, rows, batch_dates=4)
    assert sorted(np.concatenate(batches)) == list(range(len(rows)))
    for batch in batches:
        frame = games.iloc[rows[batch]]
        assert frame.season.nunique() == 1 and frame.week.nunique() <= 4
    shuffled = date_batches(games, TOY_SCHEMA, rows, 4, shuffle=True, seed=1)
    assert sorted(map(tuple, shuffled)) == sorted(map(tuple, batches))


@pytest.mark.parametrize("week", [1, 6])
def test_served_predictions_match_training_path(fitted, toy_games, week):
    """Serving rebuilds the same game embeddings and tokens training saw."""
    res, _ = fitted
    predictor, module = res["predictor"], res["model"]
    model = predictor.model
    games = played(toy_games, TOY_SCHEMA)
    games = games.sort_values(["season", "week"], kind="stable").reset_index(drop=True)
    target = games[(games.season == 2024) & (games.week == week)]

    predictor.update_state(games[(games.season < 2024) | (games.week < week)])
    served = predictor.predict(target)

    data = PbpData(games, TOY_SCHEMA, model.features, model._plays, 4).with_rows(
        target.index
    )
    with torch.no_grad():
        raw = module.predict_margin(data[list(range(len(target)))]).numpy()
    expected = antisymmetrize(target, raw, TOY_SCHEMA.game_id)
    np.testing.assert_allclose(served.pred_margin, expected, atol=1e-4)


def test_learns_and_round_trips(fitted, toy_games):
    res, save_dir = fitted
    assert res["metrics"]["test"]["accuracy"] > 0.6
    assert "total_rmse" in res["metrics"]["test"]

    loaded = load_predictor(str(save_dir))
    assert loaded.model._plays is None  # the play table is not saved
    loaded.update_state(toy_games)  # reloads it from the path
    matchups = pd.DataFrame(
        {"team": ["T00", "T01"], "opp": ["T01", "T00"], "location": [1, -1]}
    )
    out = loaded.predict(matchups)
    assert out.pred_margin[0] == pytest.approx(-out.pred_margin[1])
    assert np.isfinite(out[["win_prob", "pred_total"]].to_numpy()).all()
    res["predictor"].update_state(toy_games)
    np.testing.assert_allclose(
        out.pred_margin, res["predictor"].predict(matchups).pred_margin, atol=1e-5
    )


def test_games_without_plays_still_predict(toy_games, plays_file, tmp_path):
    plays = pd.read_parquet(plays_file)
    dropped = plays.game_id.drop_duplicates().sample(40, random_state=0)
    path = tmp_path / "plays.parquet"
    plays[~plays.game_id.isin(dropped)].to_parquet(path, index=False)
    res = fit_pbp(
        toy_games, "toy", plays=str(path), trainer=quick_trainer(1),
        print_metrics=False,
    )  # fmt: skip
    model = res["predictor"].model
    assert set(dropped) <= model._absent
    out = res["predictor"].predict(
        pd.DataFrame({"team": ["T00"], "opp": ["T05"], "location": [0]})
    )
    assert np.isfinite(out.pred_margin).all()


def test_backtest_runs_the_pbp_family(toy_games, plays_file):
    from sportsml.backtest import backtest

    out = backtest(
        toy_games, "toy", family="pbp", seasons=[2024], max_epochs=1,
        plays=plays_file, print_summary=False,
    )  # fmt: skip
    results = out["results"]
    assert len(results) and {"pred_margin", "pred_total"} <= set(results)
    assert "totals" in out["summary"]
