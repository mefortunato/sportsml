import json

import numpy as np
import pandas as pd
import pytest
import sklearn.linear_model

from sportsml.backtest import (
    BREAKEVEN,
    ats_record,
    backtest,
    no_vig_probability,
    sklearn_fitter,
    walk_forward,
)
from sportsml.cli import run

from .conftest import TOY_SCHEMA


def test_walk_forward_only_sees_the_past(toy_games):
    fits, states = [], []
    base = sklearn_fitter("toy", model=sklearn.linear_model.Ridge())

    def fitter(games, split):
        fits.append((games.season.max(), split))
        predictor = base(games, split)
        update = predictor.update_state

        def spy(known):
            states.append(known)
            update(known)

        predictor.update_state = spy
        return predictor

    results = walk_forward(toy_games, "toy", fitter, seasons=[2023, 2024])

    assert [(season, split.val) for season, split in fits] == [
        (2022, [2022]),
        (2023, [2023]),
    ]
    predicted = results[["season", "week"]].drop_duplicates().itertuples(index=False)
    for (season, week), known in zip(predicted, states, strict=True):
        assert known.season.max() <= season
        assert (known[known.season == season].week < week).all()


def test_results_have_one_row_per_game_with_market(toy_games):
    results = walk_forward(
        toy_games,
        "toy",
        sklearn_fitter("toy", model=sklearn.linear_model.Ridge()),
        seasons=[2024],
    )
    played = toy_games[(toy_games.season == 2024) & toy_games.margin.notna()]
    assert len(results) == played.game_id.nunique() == results.game_id.nunique()
    assert (results.location >= 0).all()
    home = played.set_index(["game_id", "team"]).spread
    assert np.allclose(
        results.market_margin, home.loc[list(zip(results.game_id, results.team))]
    )
    assert results.market_prob.between(0, 1).all()


def test_ats_record_counts_wins_losses_and_pushes():
    results = pd.DataFrame(
        {
            # model     spread   result
            "pred_margin": [5.0, -1.0, 3.0, 4.0],
            "market_margin": [2.0, 2.0, 3.0, 3.0],
            "margin": [4.0, 10.0, 0.0, 3.0],
        }
    )
    # edge +3 covers (win); edge -3 but team covered (loss); edge 0 (no bet);
    # edge +1 lands on the number (push)
    ats = ats_record(results, TOY_SCHEMA, thresholds=(0, 1)).set_index("min_edge")
    assert ats.loc[0, ["bets", "wins", "losses", "pushes"]].tolist() == [3, 1, 1, 1]
    assert ats.loc[0, "win_pct"] == 0.5
    assert ats.loc[0, "roi"] == pytest.approx((100 / 110 - 1) / 3)
    assert ats.loc[1, ["bets", "wins", "losses"]].tolist() == [2, 1, 1]
    assert BREAKEVEN == pytest.approx(0.5238, abs=1e-4)


def test_no_vig_probability():
    assert no_vig_probability(-110, -110) == pytest.approx(0.5)
    fav, dog = no_vig_probability(-200, 170), no_vig_probability(170, -200)
    assert fav + dog == pytest.approx(1.0)
    assert fav == pytest.approx((2 / 3) / (2 / 3 + 100 / 270))
    assert np.isnan(no_vig_probability(np.nan, -110))


def test_backtest_writes_outputs_and_scores_the_market(toy_games, tmp_path):
    out = backtest(
        toy_games,
        "toy",
        model=sklearn.linear_model.Ridge(),
        output_dir=str(tmp_path),
        print_summary=False,
    )
    summary = out["summary"]
    assert summary["seasons"] == [2023]  # 2024 is unfinished
    # the toy market knows each game's true expected margin
    overall = summary["overall"]
    assert overall["market"]["rmse"] < overall["model"]["rmse"]
    assert {"first 4 dates", "rest"} == set(summary["by_phase"])
    assert len(summary["ats"]) == 6

    saved = json.loads((tmp_path / "sklearn_summary.json").read_text())
    assert saved["overall"]["model"]["n"] == overall["model"]["n"]
    games = pd.read_csv(tmp_path / "sklearn_games.csv")
    assert {"pred_margin", "win_prob", "market_margin", "market_prob"} <= set(games)


def test_backtest_from_cli(toy_games, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    toy_games.to_csv("games.csv", index=False)
    out = run(
        [
            "toy", "backtest",
            "--games", "games.csv",
            "--model", "sklearn.linear_model.Ridge",
            "--seasons", "[2023, 2024]",
            "--print_summary", "false",
        ]
    )  # fmt: skip
    assert out["summary"]["seasons"] == [2023, 2024]
    assert (tmp_path / "backtests/toy/sklearn_summary.json").exists()
