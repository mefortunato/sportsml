# SportsML

Game predictions for the NFL, college football, NBA and men's / women's college
basketball. For any matchup it predicts the point margin and a calibrated win
probability, with two interchangeable model families:

- **sklearn**: any regressor (random forest by default) on each team's
  season-to-date box-score averages.
- **gnn**: a graph neural network (PyTorch Geometric) over the season's games,
  teams as nodes and games as edges.

## Installation

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

This installs the package, the dev tools and the notebook tooling. The PyTorch
build from PyPI includes CUDA on Linux, so the same install trains on CPU or,
when one is available, on a GPU (Lightning picks it automatically).

## Quickstart (NFL)

```sh
uv run sportsml nfl download      # nflverse schedules + weekly team stats -> data/nfl/raw.csv
uv run sportsml nfl process       # validate / clean                       -> data/nfl/games.csv
uv run sportsml nfl fit sklearn   # train, print metrics, save             -> models/nfl/sklearn
uv run sportsml nfl fit gnn       #                                        -> models/nfl/gnn
uv run sportsml nfl predict       # next unplayed games                    -> predictions/nfl.csv
```

Each week, re-run `download` and `process`, then `predict`: it refreshes the
saved model's team state from the new results without retraining. Useful
`predict` options are `--model_dir models/nfl/gnn`, `--date 9` (week 9),
`--matchups my_games.csv` and `--output_file predictions/nfl.json`.

Every command takes `--help`, and `--print_config` dumps a full YAML config
that can be edited and passed back with `--config`. Some examples:

```sh
# a different estimator, rolling windows, Vegas lines as features
uv run sportsml nfl fit sklearn --model sklearn.ensemble.HistGradientBoostingRegressor \
    --windows+ 3 --context '[rest, opp_rest, div_game, spread_line]' --overwrite true

# GNN size / training
uv run sportsml nfl fit gnn --model.encoder.init_args.num_layers 2 --trainer.max_epochs 50
```

GNN runs log to MLflow (`sqlite:///mlflow.db`); view them with
`uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`.

## Sports and data sources

| Sport | Command | Source | Credentials |
|---|---|---|---|
| NFL | `nfl` | [nflverse](https://github.com/nflverse/nflverse-data) via `nflreadpy` | none |
| College football | `cfb` | [CollegeFootballData](https://collegefootballdata.com) | `CFBD_API_KEY` |
| NBA | `nba` | stats.nba.com via `nba_api` | none |
| Men's college basketball | `cbb` | Kaggle March Machine Learning Mania | `~/.kaggle/kaggle.json` |
| Women's college basketball | `wcbb` | Kaggle March Machine Learning Mania | `~/.kaggle/kaggle.json` |

`sportsml.odds` fetches betting lines from [The Odds API](https://the-odds-api.com)
(`ODDS_API_KEY`); `odds_map` in each sport's `data/names.py` maps sportsbook
team names to the sport's team keys.

## Predictions

A saved model is an MLflow pyfunc model:

```python
import pandas as pd
from sportsml.core.predictor import load_predictor

predictor = load_predictor("models/nfl/sklearn")
predictor.update_state(pd.read_csv("data/nfl/games.csv"))  # optional refresh
predictor.predict(pd.DataFrame({"team": ["KC"], "opp_team": ["BUF"], "location": [1]}))
```

Input columns are the sport's team / opponent keys plus optional pre-game
columns (`location`: 1 home, 0 neutral, -1 away; e.g. `rest` for the NFL).
The output adds:

- `pred_margin`: expected team points minus opponent points. Predictions are
  exactly antisymmetric: A vs B is the negative of B vs A.
- `win_prob`: `P(team wins)`, from a normal distribution around `pred_margin`
  whose spread is fit on the validation season.

`predictor.metrics` holds the train / val / test metrics (RMSE, MAE, accuracy,
Brier score, log loss) from fitting. `sportsml.inference` has helpers for all
pairwise matchups, matchup matrices and upcoming games.

## Architecture

```
sportsml/
  core/           sport- and model-agnostic layer
    schema.py       GameSchema: which columns are season, team, target, stats, ...
    sport.py        Sport registry (schema + download + defaults); register_sport()
    predictor.py    MatchupModel interface + Predictor (MLflow) wrapper
    evaluation.py   shared calibration / metrics for every model family
  models/
    sklearn/        season-to-date features -> any sklearn regressor
    gnn/            season graph snapshots -> GraphModel (Lightning + PyG)
  nfl/ cfb/ nba/ cbb/ wcbb/   per-sport download + schema (data/features.py)
  inference/      predict command, matchup helpers
  cli.py          `sportsml <sport> ...`, generated from the registry
```

A games table has one row per team per game, so every game appears twice:
once from each team's perspective. Upcoming games have a missing target.

### Adding a model family (e.g. a transformer)

1. Create `sportsml/models/<family>/` with a class implementing
   `sportsml.core.predictor.MatchupModel`:
   - `update_state(games)`: rebuild per-team state from played games (for a
     transformer, e.g. encode each team's recent game sequence);
   - `predict_margin(matchups)`: raw margin for each `team` vs `opp` row;
   - `teams`: teams that currently have state.
2. Write `fit_<family>(games, sport, ...)` that trains on
   `split_seasons(...).train`, predicts the played rows of every split and calls
   `core.evaluation.calibrate_and_evaluate`, then wraps the model in
   `Predictor(model, sigma, sport, metrics)` and saves it with
   `save_predictor`. `models/sklearn/fit.py` is the shortest example.
3. Add it to `fit` in `cli.py` (and its defaults to `sport_defaults`).

`Predictor` adds antisymmetric margins, win probabilities, input validation
and MLflow persistence, and `predict` / the matchup helpers work unchanged.

### Adding a sport

Create `sportsml/<sport>/` with a `download()` that returns a games table and a
`GameSchema` describing its columns, then expose
`SPORT = Sport(name=..., schema=..., download=...)` in its `__init__.py` and
add the name to `BUILTIN_SPORTS` (or call `register_sport(SPORT)`). The CLI
and both model families pick it up from there.

## Development

```sh
make test     # uv run pytest
make lint     # ruff check + format check (pre-commit runs the same hooks)
make format
```

CI (GitHub Actions) runs lint and tests on every push to `main` and every pull
request. `make build` / `make run ARGS="nfl predict"` build and run the Docker
image (`DOCKER_ARGS="--gpus all"` for GPU).
