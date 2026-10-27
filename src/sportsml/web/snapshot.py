"""The data behind the web app's pages: one :class:`Snapshot` per sport.

A snapshot directory (written by :mod:`sportsml.web.build`) holds:

* ``games.csv``: the processed games table (played and upcoming);
* ``teams.json``: team display metadata;
* ``model/``: the saved predictor;
* ``pool.csv``: out-of-sample walk-forward predictions for historical games
  (the challenge pool, and the model performance page);
* ``rankings.csv``: the walk-forward models' power ratings before each date
  of the backtest seasons (the current season's are computed on load);
* ``meta.json``: sport, build time and backtest summary.
"""

from __future__ import annotations

import datetime
import json
import math
import pathlib
import random
from collections.abc import Iterable

import numpy as np
import pandas as pd

from ..core.io import read_table
from ..core.predictor import Predictor, load_predictor
from ..core.schema import one_row_per_game, played, upcoming
from ..core.sport import get_sport
from ..inference.utils import power_ratings
from .views import SportView, get_view


def py(value):
    """JSON-safe Python value (numpy scalars -> builtins, NaN -> None)."""
    if isinstance(value, dict):
        return {k: py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [py(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


ATS_RESULT = {"home": "W", "away": "L", "push": "P"}

# The markets a game can be played on in the challenge.
MARKETS = ("spread", "moneyline", "total")
# Odds assumed for spread bets.
SPREAD_ODDS = -110.0


def cover_side(margin: float, spread: float) -> str | None:
    """Which side covered: ``spread`` is the home team's expected margin."""
    if spread is None or pd.isna(spread) or pd.isna(margin):
        return None
    if margin > spread:
        return "home"
    if margin < spread:
        return "away"
    return "push"


def winner_side(margin: float) -> str | None:
    if margin is None or pd.isna(margin):
        return None
    return "home" if margin > 0 else "away" if margin < 0 else "push"


def total_side(total: float, line: float) -> str | None:
    """``over`` / ``under`` / ``push`` of combined points against the line."""
    if line is None or total is None or pd.isna(line) or pd.isna(total):
        return None
    return "over" if total > line else "under" if total < line else "push"


def profit(odds: float, won: bool) -> float:
    """Units won (or -1 lost) on 1 unit at American ``odds``."""
    if not won:
        return -1.0
    return odds / 100 if odds > 0 else 100 / -odds


def _value(row, column):
    """A row's numeric value, None if the column is unset, absent or NaN."""
    if column is None:
        return None
    value = row.get(column)
    return None if value is None or pd.isna(value) else float(value)


class Snapshot:
    """Everything the site shows for one sport (``web export`` writes it out).

    Upcoming-game predictions are computed once on construction; team
    summaries are computed per request from games strictly before the game
    being shown, so historical (challenge) games never reveal their result.
    """

    def __init__(
        self,
        view: SportView,
        games: pd.DataFrame,
        predictor: Predictor,
        pool: pd.DataFrame,
        teams: pd.DataFrame,
        meta: dict | None = None,
        model_dir: str | None = None,
        rankings: pd.DataFrame | None = None,
    ):
        self.view = view
        self.schema = schema = get_sport(view.sport).schema
        self.games = games.reset_index(drop=True)
        # ids arrive as strings in URLs; keep them strings everywhere
        self.games[schema.game_id] = self.games[schema.game_id].astype(str)
        self.played = played(self.games, schema)
        self.teams = {row["team"]: py(row.to_dict()) for _, row in teams.iterrows()}
        self.meta = meta or {}
        self.model_dir = model_dir
        self.sigma = predictor.sigma
        self._rows = self.games.groupby(schema.game_id).indices
        self.stat_values = pd.DataFrame(
            {stat.key: stat.value(self.played) for stat in view.stats},
            index=self.played.index,
        )
        self.playoffs = view.playoffs(self.played) if view.playoffs else {}
        self.baked_rankings = rankings if rankings is not None else pd.DataFrame()
        self.rankings_table = self._with_current_rankings(predictor)
        self.upcoming_games = self._predict_upcoming(predictor)

        if len(pool):
            pool = pool.assign(**{schema.game_id: pool[schema.game_id].astype(str)})
        self.results = pool  # every backtest game, pushes included
        self.performance_summary = self._performance() if len(pool) else None
        if len(pool) and schema.market_spread:
            # lined games; a push on one market can still be played on another
            pool = pool.dropna(subset=["market_margin"])
        self.pool = pool.set_index(schema.game_id) if len(pool) else pool
        self._markets: dict = {}

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, directory: str | pathlib.Path) -> Snapshot:
        path = pathlib.Path(directory)
        meta = json.loads((path / "meta.json").read_text())
        pool_path = path / "pool.csv"
        rankings_path = path / "rankings.csv"
        return cls(
            view=get_view(meta["sport"]),
            games=read_table(str(path / "games.csv")),
            predictor=load_predictor(str(path / "model")),
            pool=read_table(str(pool_path)) if pool_path.exists() else pd.DataFrame(),
            teams=pd.DataFrame(json.loads((path / "teams.json").read_text())),
            meta=meta,
            model_dir=str(path / "model"),
            rankings=read_table(str(rankings_path)) if rankings_path.exists() else None,
        )

    def refreshed(self, games: pd.DataFrame) -> Snapshot:
        """A new snapshot with newer games (same model, pool and teams)."""
        teams = pd.DataFrame(list(self.teams.values()))
        meta = {**self.meta, "refreshed_at": _now()}
        return Snapshot(
            self.view,
            games,
            load_predictor(self.model_dir),
            self.results,
            teams,
            meta,
            self.model_dir,
            self.baked_rankings,
        )

    # ----------------------------------------------------------------- pieces
    def team(self, key) -> dict:
        info = self.teams.get(key)
        return py(info) if info else {"team": key, "name": str(key)}

    def stat_definitions(self) -> list[dict]:
        return [
            {
                "key": s.key,
                "label": s.label,
                "decimals": s.decimals,
                "higher_is_better": s.higher_is_better,
            }
            for s in self.view.stats
        ]

    def _row(self, game_id, team=None) -> pd.Series | None:
        """One perspective of a game: ``team``'s if given, else the home team's."""
        index = self._rows.get(game_id)
        if index is None:
            return None
        rows = self.games.iloc[index]
        if team is not None:
            rows = rows[rows[self.schema.team] == team]
        return one_row_per_game(rows, self.schema).iloc[0] if len(rows) else None

    def _spread(self, row: pd.Series):
        s = self.schema
        return py(row.get(s.market_spread)) if s.market_spread else None

    def _lines(self, row: pd.Series) -> dict:
        """The market's moneylines, total line and over/under odds."""
        s = self.schema
        moneyline = None
        if s.market_moneyline:
            home, away = (_value(row, c) for c in s.market_moneyline)
            if home is not None and away is not None:
                moneyline = {"home": home, "away": away}
        total_odds = None
        if s.market_total_odds:
            over, under = (_value(row, c) for c in s.market_total_odds)
            if over is not None and under is not None:
                total_odds = {"over": over, "under": under}
        return {
            "moneyline": moneyline,
            "total_line": _value(row, s.market_total),
            "total_odds": total_odds,
        }

    def _header(self, row: pd.Series) -> dict:
        s = self.schema
        location = row[s.location] if s.location else 1
        return {
            "game_id": py(row[s.game_id]),
            "season": py(row[s.season]),
            "date": py(row[s.date]),
            "kickoff": self.view.kickoff(row),
            "home": self.team(row[s.team]),
            "away": self.team(row[s.opp]),
            "neutral": bool(location == 0),
            "spread": self._spread(row),
            **self._lines(row),
        }

    def _prediction(self, pred, header: dict) -> dict:
        """The model's numbers for a game and its pick in each market.

        ``pred`` has ``pred_margin`` / ``win_prob`` (and ``pred_total`` /
        ``over_prob`` from a model that predicts the total); ``header`` the
        game's lines (:meth:`_header`).
        """
        from ..backtest import no_vig_probability

        margin, win_prob = pred["pred_margin"], pred["win_prob"]
        spread = header["spread"]
        edge = None if spread is None else margin - spread
        pick = None
        if edge is not None and edge != 0:
            pick = "home" if edge > 0 else "away"
        out = {"margin": margin, "win_prob": win_prob, "edge": edge, "ats_pick": pick}

        # moneyline: the side whose model probability beats the market's
        market_prob = ml_edge = ml_pick = None
        if header["moneyline"]:
            ml = header["moneyline"]
            market_prob = float(no_vig_probability(ml["home"], ml["away"]))
            ml_edge = win_prob - market_prob
            ml_pick = "home" if ml_edge > 0 else "away" if ml_edge < 0 else None
        out |= {"market_prob": market_prob, "ml_edge": ml_edge, "ml_pick": ml_pick}

        total = _value(pred, "pred_total")
        line = header["total_line"]
        total_edge = ou_pick = None
        if total is not None and line is not None:
            total_edge = total - line
            ou_pick = "over" if total_edge > 0 else "under" if total_edge < 0 else None
        out |= {
            "total": total,
            "over_prob": _value(pred, "over_prob"),
            "total_edge": total_edge,
            "ou_pick": ou_pick,
        }
        return py(out)

    def _result(self, row: pd.Series) -> dict | None:
        s = self.schema
        if pd.isna(row[s.target]):
            return None
        score, opp_score = self.view.score
        home, away = _value(row, score), _value(row, opp_score)
        total = _value(row, s.total)
        if total is None and home is not None and away is not None:
            total = home + away
        return py(
            {
                "home_score": row.get(score),
                "away_score": row.get(opp_score),
                "margin": row[s.target],
                "covered": cover_side(row[s.target], self._spread(row)),
                "winner": winner_side(row[s.target]),
                "total": total,
                "went": total_side(total, _value(row, s.market_total)),
            }
        )

    def _with_current_rankings(self, predictor: Predictor) -> pd.DataFrame:
        """Baked rankings plus the current season's, from the saved model.

        One rating per team before each played date of the season and before
        its next date, from the games played until then (like the backtest).
        """
        s = self.schema
        baked = self.baked_rankings
        season = (
            upcoming(self.games, s)[s.season].max()
            if len(upcoming(self.games, s))
            else self.played[s.season].max()
        )
        if pd.isna(season) or (len(baked) and season in set(baked["season"])):
            return baked
        current = self.games[self.games[s.season] == season]
        dates = sorted(current.loc[current[s.target].notna(), s.date].unique())
        later = current.loc[current[s.target].isna(), s.date]
        dates += [later.min()] if len(later) else []
        playing = current[s.team].unique()
        rows = []
        for date in dates:
            known = self.played[
                (self.played[s.season] < season)
                | ((self.played[s.season] == season) & (self.played[s.date] < date))
            ]
            predictor.update_state(known)
            for team, rating in power_ratings(predictor, playing).items():
                rows.append(
                    {"season": season, "date": date, "team": team, "rating": rating}
                )
        return pd.concat([baked, pd.DataFrame(rows)], ignore_index=True)

    def _performance(self) -> dict:
        """Walk-forward backtest metrics: overall, by season, each market's
        bets, calibration (of win and over probabilities)."""
        from ..backtest import ats_record, moneyline_record, summarize, totals_record

        s = self.schema
        results = self.results
        summary = summarize(results, s)
        if s.market_spread:
            lined = results.dropna(subset=["market_margin", "market_prob"])
            by_season = lined.groupby(s.season)
            summary["ats_by_season"] = {
                int(season): ats_record(frame, s, thresholds=(0,)).iloc[0].to_dict()
                for season, frame in by_season
            }
            if "moneyline" in summary:
                summary["moneyline_by_season"] = {
                    int(season): moneyline_record(frame, s, thresholds=(0,))
                    .iloc[0]
                    .to_dict()
                    for season, frame in by_season
                }
            if "totals" in summary:
                summary["totals_by_season"] = {
                    int(season): totals_record(frame, s, thresholds=(0,))
                    .iloc[0]
                    .to_dict()
                    for season, frame in by_season
                }
        else:
            lined = results
        decided = lined[lined[s.target] != 0]
        won = decided[s.target] > 0
        sources = {"model": "win_prob"}
        if "market_prob" in decided:
            sources["market"] = "market_prob"
        summary["calibration"] = {
            name: _calibration(decided[column], won) for name, column in sources.items()
        }
        if "totals" in summary:
            totals = lined.dropna(subset=["over_prob", s.market_total, s.total])
            totals = totals[totals[s.total] != totals[s.market_total]]
            over = totals[s.total] > totals[s.market_total]
            sources = {"model": "over_prob"}
            if totals.get("market_over_prob", pd.Series(dtype=float)).notna().any():
                sources["market"] = "market_over_prob"
            summary["over_calibration"] = {
                name: _calibration(totals[column], over)
                for name, column in sources.items()
            }
        summary["seasons"] = sorted(int(x) for x in results[s.season].unique())
        return py(summary)

    def _predict_upcoming(self, predictor: Predictor) -> pd.DataFrame:
        predictor.update_state(self.games)
        rows = one_row_per_game(upcoming(self.games, self.schema), self.schema)
        known = set(predictor.model.teams)
        rows = rows[
            rows[self.schema.team].isin(known) & rows[self.schema.opp].isin(known)
        ]
        if rows.empty:
            return rows.assign(pred_margin=[], win_prob=[])
        preds = predictor.predict(rows)
        return preds.set_index(rows.index)

    # ------------------------------------------------------------- summaries
    def team_summary(self, team, season, date) -> dict:
        """``team`` as of just before ``(season, date)``: only earlier games."""
        s, view = self.schema, self.view
        mine = self.played[self.played[s.team] == team]
        before = (mine[s.season] < season) | (
            (mine[s.season] == season) & (mine[s.date] < date)
        )
        history = mine[before].sort_values([s.season, s.date])
        basis = season
        current = history[history[s.season] == season]
        if current.empty and not history.empty:
            basis = history[s.season].max()
            current = history[history[s.season] == basis]

        margin = current[s.target]
        record = {
            "wins": int((margin > 0).sum()),
            "losses": int((margin < 0).sum()),
            "ties": int((margin == 0).sum()),
        }
        ats = {"wins": 0, "losses": 0, "pushes": 0}
        if s.market_spread:
            lined = current.dropna(subset=[s.market_spread])
            cover = lined[s.target] - lined[s.market_spread]
            ats = {
                "wins": int((cover > 0).sum()),
                "losses": int((cover < 0).sum()),
                "pushes": int((cover == 0).sum()),
            }
        averages = self.stat_values.loc[current.index].mean().round(3)

        score, opp_score = view.score
        recent = []
        for _, row in history.tail(view.recent_games).iloc[::-1].iterrows():
            spread = self._spread(row)
            recent.append(
                {
                    "game_id": row[s.game_id],
                    "season": row[s.season],
                    "date": row[s.date],
                    "opp": self.team(row[s.opp]),
                    "location": row[s.location] if s.location else None,
                    "score": row.get(score),
                    "opp_score": row.get(opp_score),
                    "margin": row[s.target],
                    "spread": spread,
                    # this team against the spread: "W", "L" or "P"
                    "ats": ATS_RESULT.get(cover_side(row[s.target], spread)),
                }
            )
        return py(
            {
                "team": self.team(team),
                "season": basis,
                "current_season": bool(basis == season),
                "games": len(current),
                "record": record,
                "ats": ats,
                "averages": {k: averages.get(k) for k in self.stat_values},
                "recent": recent,
            }
        )

    def _summaries(self, row: pd.Series) -> dict:
        s = self.schema
        season, date = row[s.season], row[s.date]
        return {
            "home": self.team_summary(row[s.team], season, date),
            "away": self.team_summary(row[s.opp], season, date),
        }

    # ------------------------------------------------------------ endpoints
    def upcoming(self, season=None, date=None) -> dict:
        s = self.schema
        games = self.upcoming_games
        if games.empty:
            return {"season": None, "date": None, "dates": [], "games": []}
        season = games[s.season].max() if season is None else season
        games = games[games[s.season] == season]
        dates = sorted(games[s.date].unique())
        date = dates[0] if date is None else date
        week = games[games[s.date] == date]
        cards = []
        for _, row in week.iterrows():
            header = self._header(row)
            header["prediction"] = self._prediction(row, header)
            cards.append(header)
        cards.sort(key=lambda g: (g["kickoff"] or "", str(g["game_id"])))
        return py({"season": season, "date": date, "dates": dates, "games": cards})

    def game(self, game_id) -> dict | None:
        """Header, prediction, result (if played) and both teams' summaries."""
        s = self.schema
        in_pool = len(self.pool) and game_id in self.pool.index
        team = self.pool.loc[game_id, s.team] if in_pool else None
        row = self._row(game_id, team)
        if row is None:
            return None
        header = self._header(row)
        prediction = None
        if game_id in set(self.upcoming_games.get(s.game_id, [])):
            pred = self.upcoming_games[self.upcoming_games[s.game_id] == game_id].iloc[
                0
            ]
            prediction = self._prediction(pred, header)
        elif in_pool:
            prediction = self._prediction(self.pool.loc[game_id], header)
        return py(
            {
                **header,
                "prediction": prediction,
                "result": self._result(row),
                "summaries": self._summaries(row),
                "stats": self.stat_definitions(),
            }
        )

    def markets(self, game_id) -> list[str]:
        """Markets a pool game can be played on: it has the line (and, for the
        total, a model total) and did not land on it."""
        if game_id in self._markets:
            return self._markets[game_id]
        s = self.schema
        pool = self.pool.loc[game_id]
        row = self._row(game_id, pool[s.team])
        lines = self._lines(row)
        result = self._result(row)
        out = []
        if result["covered"] in ("home", "away"):
            out.append("spread")
        if lines["moneyline"] and result["winner"] in ("home", "away"):
            out.append("moneyline")
        has_total = "pred_total" in pool and not pd.isna(pool["pred_total"])
        if has_total and result["went"] in ("over", "under"):
            out.append("total")
        self._markets[game_id] = out
        return out

    def challenge_next(
        self, rng: random.Random, exclude: Iterable = (), market: str = "spread"
    ) -> dict:
        """A random historical game with pre-game info only (no result/model)
        that can be played on ``market``."""
        if not len(self.pool):
            raise LookupError("no historical games available")
        playable = [g for g in self.pool.index if market in self.markets(g)]
        if not playable:
            raise LookupError(f"no historical games for the {market} market")
        ids = [g for g in playable if g not in set(exclude)] or playable
        return self.challenge_game(rng.choice(ids))

    def challenge_game(self, game_id) -> dict:
        """A pool game's pre-game info only (no result/model)."""
        row = self._row(game_id, self.pool.loc[game_id, self.schema.team])
        header = self._header(row)
        return py(
            {
                **header,
                "markets": self.markets(game_id),
                "summaries": self._summaries(row),
                "stats": self.stat_definitions(),
                "pool_size": len(self.pool),
            }
        )

    def challenge_answers(self, game_id) -> dict:
        """Each playable market's outcome, odds and the model's pick, without
        the player's pick (the browser scores it: ``outcome`` is the winning
        pick, ``odds`` each pick's American odds)."""
        s = self.schema
        pool = self.pool.loc[game_id]
        row = self._row(game_id, pool[s.team])
        header = self._header(row)
        result = self._result(row)
        prediction = self._prediction(pool, header)
        answers = {}
        for market in self.markets(game_id):
            if market == "spread":
                outcome, model_pick = result["covered"], prediction["ats_pick"]
                odds = {"home": SPREAD_ODDS, "away": SPREAD_ODDS}
                extra = {"spread": header["spread"], "covered": outcome}
            elif market == "moneyline":
                outcome, model_pick = result["winner"], prediction["ml_pick"]
                odds = header["moneyline"]
                extra = {}
            else:
                outcome, model_pick = result["went"], prediction["ou_pick"]
                odds = header["total_odds"] or {"over": -110.0, "under": -110.0}
                extra = {"total_line": header["total_line"]}
            correct = model_pick == outcome
            model_units = (
                profit(odds[model_pick], correct) if model_pick is not None else 0.0
            )
            answers[market] = py(
                {
                    "game_id": game_id,
                    "market": market,
                    "outcome": outcome,
                    "odds": odds,
                    "result": result,
                    **extra,
                    "model": {
                        **prediction,
                        "pick": model_pick,
                        "correct": correct,
                        "units": model_units,
                    },
                }
            )
        return answers

    def challenge_answer(self, game_id, pick: str, market: str = "spread") -> dict:
        """Score the player's pick on ``market`` and reveal the model's."""
        answer = self.challenge_answers(game_id).get(market)
        if answer is None:
            raise LookupError(f"game {game_id} cannot be played on {market}")
        correct = pick == answer["outcome"]
        return {
            **answer,
            "pick": pick,
            "correct": correct,
            "units": profit(answer["odds"][pick], correct),
        }

    def available_markets(self) -> list[str]:
        """Markets the challenge offers (some pool game can be played on)."""
        if not len(self.pool):
            return []
        found = set()
        for game_id in self.pool.index:
            found |= set(self.markets(game_id))
            if len(found) == len(MARKETS):
                break
        return [m for m in MARKETS if m in found]

    def performance(self) -> dict | None:
        return self.performance_summary

    def rankings(self) -> dict:
        """Power ratings per season: one value per team per date, and how
        the season ended for the teams that reached the last playoff rounds."""
        table = self.rankings_table
        baked = (
            set(self.baked_rankings["season"]) if len(self.baked_rankings) else set()
        )
        seasons = []
        for season, frame in sorted(table.groupby("season"), reverse=True):
            dates = sorted(frame["date"].unique())
            wide = frame.pivot_table(
                index="team", columns="date", values="rating"
            ).reindex(columns=dates)
            teams = [
                {"team": self.team(team), "ratings": [py(round(v, 2)) for v in row]}
                for team, row in wide.iterrows()
            ]
            seasons.append(
                {
                    "season": season,
                    "source": "backtest" if season in baked else "current",
                    "dates": dates,
                    "teams": teams,
                    "playoffs": self.playoffs.get(int(season), {}),
                }
            )
        return py(
            {
                "seasons": seasons,
                "date_label": self.view.date_label,
                "playoff_labels": dict(self.view.playoff_labels),
            }
        )

    def info(self) -> dict:
        return py(
            {
                "sport": self.view.sport,
                "label": self.view.label,
                "date_label": self.view.date_label,
                "has_spread": bool(self.schema.market_spread),
                "challenge_games": len(self.pool),
                "markets": self.available_markets(),
                "built_at": self.meta.get("built_at"),
                "refreshed_at": self.meta.get("refreshed_at"),
                "model": self.meta.get("model"),
                "backtest": self.meta.get("backtest"),
            }
        )


def _calibration(prob: pd.Series, happened: pd.Series) -> list[dict]:
    """Mean predicted probability vs how often it happened, in 10% bins."""
    bins = pd.cut(prob, np.linspace(0, 1, 11), include_lowest=True)
    grouped = happened.groupby(bins, observed=True)
    predicted = prob.groupby(bins, observed=True).mean()
    return [
        {"predicted": predicted[b], "actual": grouped.mean()[b], "n": n}
        for b, n in grouped.size().items()
        if n
    ]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
