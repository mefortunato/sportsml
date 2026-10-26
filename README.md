# SportsML

Game predictions for the NFL, college football, NBA and men's / women's college
basketball. For any matchup it predicts the point margin and a calibrated win
probability, with three interchangeable model families:

- **sklearn**: any regressor (random forest by default) on each team's
  season-to-date box-score averages.
- **gnn**: a graph neural network (PyTorch Geometric) over the season's games,
  teams as nodes and games as edges.
- **transformer**: a transformer over each team's most recent games (across
  seasons), so season openers still have a full history. `--opponent_strength
  true` (with `--model.encoder.init_args.token_dim` raised by 3) also gives
  each game the pre-game Elo of both teams and the opponent's season-to-date
  margin; on NFL 2021-2025 that did not change the backtest Brier.

Naive baselines (`home` field only, season-to-date `point_diff`, and
FiveThirtyEight-style `elo`) and the betting market are the yardsticks in
backtests.

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
uv run sportsml nfl fit transformer #                                      -> models/nfl/transformer
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

GNN and transformer runs log to MLflow (`sqlite:///mlflow.db`); view them with
`uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`.

## Backtesting against the market

```sh
uv run sportsml nfl backtest                 # sklearn, last 5 complete seasons
uv run sportsml nfl backtest --family transformer --seasons '[2023, 2024, 2025]'
uv run sportsml nfl benchmark                # every family + baselines + market
```

`--family` takes any model family or baseline: `home`, `point_diff`, `elo`,
`sklearn`, `gnn`, `transformer`.

For each test season the model is fit on earlier seasons only, then the season
is replayed week by week: team state is refreshed from the games played so far
and that week's games are predicted. This is the same loop as production
(retrain occasionally, refresh weekly), so there is no lookahead.

The baseline is the Vegas line from the nflverse schedule. Its margin is the
spread and its win probability comes from the no-vig moneylines. The summary
prints:

- RMSE, accuracy, Brier score and log loss for the model and the market on
  the same games, overall, by season, and for the first four weeks vs the
  rest;
- against-the-spread results from betting the model's side whenever it
  disagrees with the spread by more than 0-5 points, with win rate, 95% CI
  and ROI at -110 (break-even is 52.38%);
- the correlation between the model's edge (model margin minus spread) and
  the cover margin (result minus spread). It is above zero only if the model
  knows something the spread does not.

`backtests/nfl/<family>_games.csv` holds every game's model and market
prediction, and `<family>_summary.json` the summary.

`benchmark` runs several families (default: all) through the same backtest
and compares them on the games all of them predicted. Its table is sorted by
Brier score, includes early-season Brier, and gives each family's paired
per-game Brier difference to the market with a 95% CI. A family is only
meaningfully better than another when those intervals separate. It writes
`benchmark.csv`, `benchmark.json` and `benchmark_games.csv` (every source's
prediction per game) to `backtests/<sport>/`.

Any model can be backtested from Python with
`sportsml.backtest.walk_forward(games, sport, fitter, seasons)`, where
`fitter(games, split)` returns a fitted `Predictor`.

## Web app

A static site (SvelteKit) with no server, rebuilt daily on GitHub Pages:

- **Upcoming games**: each game's Vegas line and the model's predicted
  margin on one chart, the win probability, and the model's pick against
  the spread.
- **Game view**: both teams' per-game stats, W-L and ATS records, and recent
  results, all as of before kickoff.
- **Power rankings**: each team's average predicted margin against every
  other team, week by week, with conference, division and final-four
  filters.
- **Model performance**: the walk-forward backtest against Vegas
  (accuracy, Brier score, calibration, betting the model's edge).
- **Beat the model**: a past game with its line and both teams' pre-game
  stats. Pick the side that covers, then see the final score and what the
  model picked. The model's picks are its walk-forward backtest predictions,
  made without seeing those games. Your record is kept in your browser.

Every page reads JSON files built next to the site; nothing is computed on
request. Two GitHub Actions workflows keep them current:

- **Train** (`.github/workflows/train.yml`, monthly in season and on
  demand) runs `sportsml web build`: download, train the transformer,
  backtest it and record weekly power rankings (~30 minutes). It publishes
  the result as the `webdata` release asset.
- **Site** (`.github/workflows/site.yml`, daily and after Monday night's
  game) downloads that asset, runs `sportsml web export --refresh true`
  (re-download results and refresh team state, no retraining), builds the
  frontend and deploys it. A failed run leaves the last deployed site up.

To set it up: in the repository settings, set **Pages → Source** to
**GitHub Actions**, then run **Train** once from the Actions tab. It starts
**Site** when it finishes.

Locally:

```sh
make webdata                    # train + backtest (slow) -> webdata/
make site                       # fresh results -> web/static/data, site -> web/build
make web-dev                    # hot reload on :5173 with that data
make artifact                   # one-page build (hash routing) -> web/build-artifact/
```

Limits of a static site:

- Only precomputed views exist: upcoming weeks, their game views, past
  seasons' rankings, the challenge pool.
- The challenge answers ship with the site, so it runs on the honor
  system.
- The data is as fresh as the last Site run; line moves during the day are
  not reflected.

To add a sport, give it a `SportView` (`src/sportsml/web/sports/<sport>.py`)
with its stats, team metadata and score columns, add it to `BUILTIN_VIEWS`,
and build it with `sportsml web build --sports '[nfl, <sport>]'`. The
frontend needs no changes.

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
    evaluation.py   shared calibration / metrics; finish_fit() for every family
  models/
    baselines.py    home field, point differential, Elo
    sklearn/        season-to-date features -> any sklearn regressor
    gnn/            season graph snapshots -> GraphModel (Lightning + PyG)
    transformer/    per-team game sequences -> TransformerModel (Lightning)
    lightning.py    shared base (MarginModule), trainer, seeding for neural families
  nfl/ cfb/ nba/ cbb/ wcbb/   per-sport download + schema (data/features.py)
  inference/      predict command, matchup helpers
  backtest.py     walk-forward backtests, family registry, benchmark
  web/            per-sport views, snapshots, static-site export
  cli.py          `sportsml <sport> ...` and `sportsml web ...`, generated from the registry
web/              SvelteKit frontend (static site; data from `sportsml web export`)
```

A games table has one row per team per game, so every game appears twice:
once from each team's perspective. Upcoming games have a missing target.

### Adding a model family

`models/transformer/` is the worked example.

1. Create `sportsml/models/<family>/` with a class implementing
   `sportsml.core.predictor.MatchupModel`:
   - `update_state(games)`: rebuild per-team state from played games (the
     transformer keeps each team's last N games);
   - `predict_margin(matchups)`: raw margin for each `team` vs `opp` row;
   - `teams`: teams that currently have state.
   A neural family can subclass `models.lightning.MarginModule` for target
   scaling, loss, metric logging and checkpoint loading.
2. Write `fit_<family>(games, sport, ...)` that trains on
   `split_seasons(...).train`, predicts the played rows of every split
   (pre-game state only) and returns `core.evaluation.finish_fit(...)`, which
   calibrates, scores, wraps the model in a `Predictor` and saves it.
3. Add it to `fit` in `cli.py` (defaults in `sport_defaults`) and to
   `family_fitter` / `Family` in `backtest.py`, so it can be backtested and
   benchmarked.

`Predictor` adds antisymmetric margins, win probabilities, input validation
and MLflow persistence, and `predict` / the matchup helpers work unchanged.

### Adding a sport

Create `sportsml/<sport>/` with a `download()` that returns a games table and a
`GameSchema` describing its columns, then expose
`SPORT = Sport(name=..., schema=..., download=...)` in its `__init__.py` and
add the name to `BUILTIN_SPORTS` (or call `register_sport(SPORT)`). The CLI
and every model family pick it up from there.

## Development

```sh
make test     # uv run pytest
make lint     # ruff check + format check (pre-commit runs the same hooks)
make format
```

`make test` and `make lint` also run the frontend's unit tests and
`svelte-check`. CI (GitHub Actions) runs both on every push to `main` and every
pull request. `make cli ARGS="nfl predict"` runs any CLI command inside the
Docker image (`DOCKER_ARGS="--gpus all"` for GPU).
