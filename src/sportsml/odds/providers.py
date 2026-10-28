"""Betting lines from several providers, normalized to one table.

Each provider returns one row per game per sportsbook, from the home team's
side: ``book``, ``home`` / ``away`` (the sport's team keys), ``commence``
(UTC kickoff), ``spread`` (the home team's expected margin: positive when
the home team is favored, the opposite sign of the handicap books quote),
``spread_home_odds`` / ``spread_away_odds``, ``ml_home`` / ``ml_away``
(American moneylines), ``total``, ``over_odds`` / ``under_odds`` and, where
the provider has them, ``spread_open`` / ``total_open``. Missing markets
are NaN.

* :class:`OddsAPI`: https://the-odds-api.com (``ODDS_API_KEY``), every book
  in a region, one request per sport and refresh.
* :class:`CFBD`: https://collegefootballdata.com (``CFBD_API_KEY``), college
  football lines from several books, opening lines included.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from collections.abc import Callable

import httpx
import numpy as np
import pandas as pd

from ..cfb.data.download import FCS

logger = logging.getLogger(__name__)

COLUMNS = [
    "book", "home", "away", "commence", "spread", "spread_home_odds",
    "spread_away_odds", "ml_home", "ml_away", "total", "over_odds",
    "under_odds", "spread_open", "total_open",
]  # fmt: skip


def empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


class Provider:
    """Fetches current lines for a sport; ``remaining`` is the provider's
    reported request quota after the last fetch (None if it reports none)."""

    name = "provider"
    remaining: int | None = None

    def fetch(self) -> pd.DataFrame:
        raise NotImplementedError


# The Odds API's sport keys.
ODDS_API_SPORTS = {
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "nba": "basketball_nba",
    "cbb": "basketball_ncaab",
    "wcbb": "basketball_wncaab",
    "wnba": "basketball_wnba",
    "nhl": "icehockey_nhl",
    "mlb": "baseball_mlb",
}

# Sports without a point spread: their "spreads" are the puck / run line, a
# fixed 1.5 handicap, so only moneylines and totals are requested.
NO_SPREAD = {"nhl", "mlb", "icehockey_nhl", "baseball_mlb"}


class OddsAPI(Provider):
    """Every US book's spread, moneyline and total for a sport's upcoming
    games, in one request (about 3 credits: one per market; no spreads for
    :data:`NO_SPREAD` sports).

    Args:
        sport: Sport name (``ODDS_API_SPORTS``) or an Odds API sport key.
        names: Maps the API's team names to the sport's team keys (e.g. the
            NFL's ``odds_map``); unmapped names are kept as they are.
        api_key: Default ``ODDS_API_KEY``.
        get: ``get(url, params) -> (json, headers)``; tests pass a fake.
    """

    name = "oddsapi"
    host = "https://api.the-odds-api.com/v4"

    def __init__(
        self,
        sport: str,
        names: dict | None = None,
        api_key: str | None = None,
        regions: str = "us",
        get: Callable | None = None,
    ):
        self.sport = ODDS_API_SPORTS.get(sport, sport)
        self.markets = "h2h,totals" if self.sport in NO_SPREAD else "h2h,spreads,totals"
        self.names = names or {}
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        self.regions = regions
        self._get = get or _http_get

    def fetch(self) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError("set ODDS_API_KEY to fetch from The Odds API")
        data, headers = self._get(
            f"{self.host}/sports/{self.sport}/odds",
            {
                "apiKey": self.api_key,
                "regions": self.regions,
                "markets": self.markets,
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
        )
        remaining = headers.get("x-requests-remaining")
        self.remaining = int(float(remaining)) if remaining is not None else None
        rows = []
        for game in data:
            home, away = game["home_team"], game["away_team"]
            for book in game.get("bookmakers", []):
                row = {
                    "book": book.get("title") or book["key"],
                    "home": self.names.get(home, home),
                    "away": self.names.get(away, away),
                    "commence": game["commence_time"],
                }
                for market in book.get("markets", []):
                    prices = {o["name"]: o for o in market["outcomes"]}
                    if market["key"] == "h2h":
                        row["ml_home"] = prices.get(home, {}).get("price")
                        row["ml_away"] = prices.get(away, {}).get("price")
                    elif market["key"] == "spreads" and home in prices:
                        # books quote the home handicap: -3 is home by 3
                        row["spread"] = -prices[home]["point"]
                        row["spread_home_odds"] = prices[home]["price"]
                        row["spread_away_odds"] = prices.get(away, {}).get("price")
                    elif market["key"] == "totals" and "Over" in prices:
                        row["total"] = prices["Over"]["point"]
                        row["over_odds"] = prices["Over"]["price"]
                        row["under_odds"] = prices.get("Under", {}).get("price")
                rows.append(row)
        return _frame(rows)


class CFBD(Provider):
    """College football lines from CollegeFootballData's ``/lines``: one
    request per season week, several books per game, with opening lines.
    CFBD has no prices on spreads and totals (they are left NaN; the site
    assumes -110). Team keys are CFBD's team names, as in the CFB games
    table, and :data:`~sportsml.cfb.data.download.FCS` for an FCS side.

    Args:
        year / week / season_type: The week to fetch (default: the season
            and week containing today, from ``/calendar``).
        api_key: Default ``CFBD_API_KEY``.
        get: ``get(url, params, headers) -> (json, headers)``; tests pass a
            fake.
    """

    name = "cfbd"
    host = "https://api.collegefootballdata.com"

    def __init__(
        self,
        year: int | None = None,
        week: int | None = None,
        season_type: str | None = None,
        api_key: str | None = None,
        get: Callable | None = None,
        today: datetime.date | None = None,
    ):
        self.year, self.week, self.season_type = year, week, season_type
        self.api_key = api_key or os.getenv("CFBD_API_KEY")
        self._get = get or _http_get
        self.today = today

    def _call(self, path: str, params: dict):
        data, headers = self._get(
            f"{self.host}/{path}",
            params,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        remaining = headers.get("x-calllimit-remaining")
        if remaining is not None:
            self.remaining = int(float(remaining))
        return data

    def current_week(self) -> tuple[int, int, str]:
        """The season, week and season type of the next games, from the
        calendar: the first week that has not ended yet."""
        today = self.today or datetime.datetime.now(datetime.timezone.utc).date()
        year = today.year if today.month >= 3 else today.year - 1
        weeks = self._call("calendar", {"year": year})
        for week in sorted(
            weeks, key=lambda w: w.get("endDate") or w.get("lastGameStart")
        ):
            end = (week.get("endDate") or week.get("lastGameStart") or "")[:10]
            if end and datetime.date.fromisoformat(end) >= today:
                return year, int(week["week"]), week.get("seasonType", "regular")
        raise LookupError(f"no college football weeks left in {year}")

    def fetch(self) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError("set CFBD_API_KEY to fetch college football lines")
        year, week, season_type = self.year, self.week, self.season_type
        if year is None or week is None:
            year, week, season_type = self.current_week()
        params = {"year": year, "week": week, "seasonType": season_type or "regular"}
        rows = []
        for game in self._call("lines", params):
            home, away = game["homeTeam"], game["awayTeam"]
            # FCS opponents are one pooled team in the games table
            if game.get("homeClassification") not in (None, "fbs"):
                home = FCS
            if game.get("awayClassification") not in (None, "fbs"):
                away = FCS
            for line in game.get("lines", []):
                rows.append(
                    {
                        "book": line.get("provider"),
                        "home": home,
                        "away": away,
                        "commence": game.get("startDate"),
                        "spread": cfbd_spread(line, home, away, "spread"),
                        "spread_open": cfbd_spread(line, home, away, "spreadOpen"),
                        "ml_home": line.get("homeMoneyline"),
                        "ml_away": line.get("awayMoneyline"),
                        "total": line.get("overUnder"),
                        "total_open": line.get("overUnderOpen"),
                    }
                )
        return _frame(rows)


def cfbd_spread(line: dict, home: str, away: str, key: str) -> float:
    """The home team's expected margin from a CFBD line.

    CFBD's ``spread`` is the home handicap (negative: home favored); its
    ``formattedSpread`` ("Georgia -21.5") names the favorite and settles the
    sign when present.
    """
    value = line.get(key)
    if value is None:
        return np.nan
    margin = -float(value)
    match = re.match(r"^(.*)\s(-?\d+(?:\.\d+)?)$", line.get("formattedSpread") or "")
    if match and key == "spread":
        favorite, points = match.group(1).strip(), abs(float(match.group(2)))
        if favorite == home:
            margin = points
        elif favorite == away:
            margin = -points
    return margin


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).reindex(columns=COLUMNS)
    numeric = [c for c in COLUMNS if c not in ("book", "home", "away", "commence")]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame["commence"] = pd.to_datetime(frame["commence"], utc=True, errors="coerce")
    return frame


def _http_get(url: str, params: dict, headers: dict | None = None):
    response = httpx.get(url, params=params, headers=headers or {}, timeout=30)
    response.raise_for_status()
    return response.json(), response.headers


def provider_for(sport: str, name: str) -> Provider:
    """A sport's provider by name (``oddsapi`` or ``cfbd``), with the sport's
    sportsbook team-name map where it has one."""
    if name == "cfbd":
        return CFBD()
    if name == "oddsapi":
        names = {}
        try:
            import importlib

            names = importlib.import_module(f"sportsml.{sport}.data.names").odds_map
        except (ImportError, AttributeError):
            logger.info("no odds_map for %s: keeping sportsbook team names", sport)
        return OddsAPI(sport, names=names)
    raise ValueError(f"unknown odds provider {name!r} (oddsapi, cfbd)")
