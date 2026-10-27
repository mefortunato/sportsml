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

The neural families can also regress the total (combined points) and every
box-score stat next to the margin, as extra outputs with their own loss
weights (`--total_weight`, `--stats_weight` on `fit transformer`;
`total_weight` / `stats_weight` in `Sport.transformer` or `Sport.gnn`). A
model with the total serves `pred_total` and, where the matchup carries the
market's line, `over_prob`.

The transformer can also predict a full score distribution instead of
point values (`distribution: true` in `Sport.transformer` or the model
config): a bell curve per game plus a learned weight per whole-number
margin and total, so values football scoring produces often (a 3- or
7-point margin) get their real share, and cover / moneyline / over
probabilities come from it with pushes left out. On NFL 2006-2025 it did not
beat the normal model (cover Brier +0.0002 +/- 0.0016, moneyline Brier
+0.0012 +/- 0.0014), so it is off by default.

NFL games also carry pre-game injury features: for each unit (`qb`, `ol`,
`skill`, `front`, `secondary`), `inj_<unit>` / `opp_inj_<unit>` is the snap
share the week's injury report is expected to take away (each listed
player's share of the team's last 4 games times the chance a player with his
status sits; 1.0 is one full-time player). They are default context
features; on NFL 2021-2025 they improved the transformer's backtest Brier by
0.0028 +/- 0.0025 (about a fifth of its gap to the market), most of it in a
team's first game with a new quarterback.

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

## College football

```sh
export CFBD_API_KEY=...             # free key: collegefootballdata.com
uv run sportsml cfb download        # CFBD games, box scores, lines -> data/cfb/raw.csv
uv run sportsml cfb process         #                                -> data/cfb/games.csv
uv run sportsml cfb fit transformer #                                -> models/cfb/transformer
uv run sportsml cfb predict --model_dir models/cfb/transformer
```

`download` builds the games table from CollegeFootballData's v2 API: the
schedule (`/games`, so upcoming games are kept and cancelled ones dropped),
team box scores (`/games/teams`) and betting lines (`/lines`). Each market
comes from the most preferred book that has it (consensus, DraftKings, ESPN
Bet, Bovada, ...): `spread_line` (the team's expected margin), `total_line`
and both moneylines from the same book. CFBD has no spread or over/under
prices, so those bets are scored at -110. Box scores start in 2004, spreads
in 2013, totals in 2013 (~88% of games until 2017, all of them since 2019)
and moneylines in 2021.

- **FBS vs FCS.** Only games with an FBS team are kept. FCS and
  lower-division opponents are pooled into one team, `FCS`: a school that
  plays one FBS game a year would otherwise have a team state years out of
  date, while the pooled team's recent games describe a typical FCS
  opponent (it wins ~7% of these games, by -29 on average). The school's own
  name stays in `team_name` / `opp_name`.
- **Neutral sites, bowls and playoffs.** Neutral-site games have
  `location` 0 for both teams. CFBD files the whole bowl season under
  postseason week 1; `week` instead numbers postseason games by the 7-day
  block they fall in after the last regular week, so each playoff round is
  predicted from state that includes the previous round. `game_type` is
  `regular`, `bowl`, `playoff` or `final`, and `postseason`,
  `conference_game` and rest days (`rest`, `opp_rest`) are context
  features.
- **API budget.** CFBD's free tier allows 1,000 calls a month and a full
  download from 2004 takes ~450. Responses of finished seasons and weeks
  are cached in `data/cfb/cfbd_cache`, so later downloads only fetch the
  current season's schedule, lines and newest box scores (~6 calls).

The transformer's CFB defaults differ from the NFL's: a 28-game history
(about two seasons) and each history game's pre-game Elo of both teams
(`opponent_strength`), because schedule strength varies far more across 130+
FBS teams than across 32 NFL teams.

Walk-forward backtest, 2021-2025 (4,441 games every family predicted with a
spread; `brier vs market` is the paired per-game difference, 95% CI):

| Source | RMSE | Accuracy | Brier | Brier vs market | ATS |
|---|---|---|---|---|---|
| market | 15.32 | 75.6% | 0.1612 | | |
| transformer | 16.40 | 73.7% | 0.1699 | +0.0087 ± 0.0031 | 50.9% |
| gnn | 17.06 | 73.1% | 0.1769 | +0.0157 ± 0.0037 | 50.4% |
| sklearn | 17.63 | 72.2% | 0.1820 | +0.0208 ± 0.0039 | 50.6% |
| point_diff | 18.41 | 71.7% | 0.1869 | +0.0257 ± 0.0042 | 50.7% |
| elo | 18.53 | 72.9% | 0.1874 | +0.0262 ± 0.0035 | 51.1% |
| home | 22.00 | 62.7% | 0.2326 | +0.0714 ± 0.0057 | 50.4% |

As in the NFL, no model beats the spread (the transformer's picks win
50.8%, -3.0% ROI at -110). Its total is the one market with a persistent
edge: over/under picks won 53.2% of 4,516 games (+1.5% ROI at an assumed
-110; 54.3% and +3.6% on the 2,782 with an edge over 2 points), and over
2016-2025 the same picks won 52.8% of 8,357. CFBD records no over/under
prices, so the true juice (and so the real ROI) is unknown. Moneyline
picks (lines from 2021) lose at a small edge and are noisy above one.
`staking` on the 2016-2025 backtest finds no stake sizing that rescues the
spread; on the totals, betting edges over 2 points returned +3.7% (95% CI
+0.8% to +6.7%) against flat betting's +1.4% over 2019-2025.

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
- moneyline results from betting the side the model rates more likely to
  win than the market's no-vig odds imply (by more than 0-10 percentage
  points), with profit at the posted moneylines;
- for models that predict the total: its RMSE next to the over/under
  line's, the over/under Brier score against the no-vig over/under odds,
  and over/under bets when the model's total beats the line by 0-5 points,
  at the posted odds;
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

### Confidence-weighted staking

Flat betting stakes one unit on every pick, however close the model is to
the line. `staking` sizes each bet from the model's edge instead and scores
the weighted profit:

```sh
uv run sportsml nfl backtest --family transformer --n_seasons 10
uv run sportsml nfl staking --results backtests/nfl/transformer_games.csv
```

For each market (spread, moneyline and, with a model total, over/under) it
compares flat staking, edge thresholds, a stake proportional to the edge,
and a learned policy: a logistic fit of P(pick wins | edge) on the earlier
seasons' out-of-sample picks, staking the half-Kelly bet at each pick's odds
(nothing where the edge has not beaten the odds). Each test season's
policies only learn from earlier seasons, so the first `--min_train_seasons`
(default 3) seasons of results are only learned from. Stakes are relative
units (average stake 1), so ROI is profit per unit staked and comparable
with flat betting. The summary gives profit, ROI with a bootstrap 95% CI,
the paired ROI difference vs flat, the stake-weighted win rate, the largest
drawdown and profit by season; `staking_summary.json` and
`staking_bets.csv` (every pick's stake under every policy) go to
`backtests/<sport>/`.

Any model can be backtested from Python with
`sportsml.backtest.walk_forward(games, sport, fitter, seasons)`, where
`fitter(games, split)` returns a fitted `Predictor`.

## Web app

A static site (SvelteKit) with no server, rebuilt daily on GitHub Pages, with
the NFL and college football:

- **Upcoming games**: each game's Vegas line and the model's predicted
  margin on one chart, the win probability, and the model's pick in each
  market: against the spread, on the moneyline and on the over/under.
- **Game view**: both teams' per-game stats, W-L and ATS records, and recent
  results, all as of before kickoff.
- **Price your line** (upcoming games): enter the spread, moneyline or
  total and odds your sportsbook offers; the page reprices every pick in the
  browser (the model's predictions do not depend on the odds) with its win
  chance, break-even, expected value and a quarter-Kelly stake. Win chances
  are the model's moved toward the market by how much of its disagreement
  has been right in the walk-forward backtest (`pricing.trust` in
  `sports.json`, fit per market).
- **Power rankings**: each team's average predicted margin against every
  other team, week by week, with conference, division and final-four
  filters.
- **Model performance**: the walk-forward backtest against Vegas
  (accuracy, Brier score, calibration, and betting the model's edge on the
  spread, the moneyline and the over/under).
- **Beat the model**: a past game with its lines and both teams' pre-game
  stats. Choose a market (spread, moneyline or over/under), make your pick,
  then see the final score and what the model picked. Picks are scored in
  units at the game's odds. The model's picks are its walk-forward backtest
  predictions, made without seeing those games. Your record on each market
  is kept in your browser.

- **Current lines**: with `--odds`, upcoming games show every sportsbook's
  spread, moneyline and total, the best price on each side, the opening
  line and how the consensus moved; the cards, picks and the line
  calculator use the current consensus, and any book can be loaded into
  the calculator.

Every page reads JSON files built next to the site; nothing is computed on
request. Two GitHub Actions workflows keep them current:

- **Train** (`.github/workflows/train.yml`, monthly in season and on
  demand) runs `sportsml web build --sports '[nfl, cfb]'`: for each sport,
  download, train the transformer, backtest it and record weekly power
  rankings. It publishes the result as the `webdata` release asset.
- **Site** (`.github/workflows/site.yml`, daily and after Monday night's
  game) downloads that asset, runs `sportsml web export --refresh true`
  (re-download results and refresh team state, no retraining), builds the
  frontend and deploys it. A failed run leaves the last deployed site up.

Sportsbook lines come from `sportsml web export --odds '{nfl: oddsapi,
cfb: cfbd}'`: [The Odds API](https://the-odds-api.com) (`ODDS_API_KEY`;
every US book, one request per sport and refresh) and CollegeFootballData's
`/lines` (`CFBD_API_KEY`; several books with opening lines). The Site
workflow refreshes them about 23 times a week in season, more often on game
days, which fits The Odds API's free tier (150 requests a month) for the
NFL; no request is made when no game is within 8 days, and a failed fetch
keeps the last lines. Add `ODDS_API_KEY` (and `CFBD_API_KEY`) under the
repository's **Settings → Secrets and variables → Actions**; without them
the site builds as before, without current lines. `odds.json` reports the
provider's remaining requests.

To set it up: in the repository settings, set **Pages → Source** to
**GitHub Actions**, add a `CFBD_API_KEY` repository secret (both workflows
download college football), then run **Train** once from the Actions tab.
Both workflows keep CFBD's responses of finished seasons in the Actions
cache, so a daily Site run makes only a handful of CFBD calls. It starts
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
