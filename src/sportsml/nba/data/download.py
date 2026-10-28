"""NBA games, box scores and betting lines from ESPN.

The schedule and team box scores come from sportsdataverse's ESPN NBA
release files (https://github.com/sportsdataverse/sportsdataverse-data, one
parquet file per season, refreshed daily around 11:45 UTC with the previous
night's games). The schedule is the source of truth for which games exist, so
upcoming games are kept with a missing result; postponed games are dropped
(ESPN gives the makeup game a new id).

Betting lines come from ESPN's odds API, one request per game: every
book ESPN lists, from the 2012-13 season on. Each market comes from the most
preferred book that has it (:data:`PROVIDERS`). Lines of finished games
never change, so they are cached per season on disk (``cache_dir``) with the
finished seasons' parquet files; a daily refresh only requests the newest
games and the next few days' upcoming ones (ESPN posts lines about a day
ahead).

Team keys are the franchise's current abbreviation (``GSW``, ``NYK``, ...,
as The Odds API's ``odds_map`` uses), from ESPN's franchise id, so a team
that moved or was renamed (Seattle -> Oklahoma City, New Jersey ->
Brooklyn) keeps one history; the name it played under stays in
``team_name`` / ``opp_name``.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import io
import json
import logging
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RELEASES = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
SCHEDULE_URL = RELEASES + "/espn_nba_schedules/nba_schedule_{season}.parquet"
TEAM_BOX_URL = RELEASES + "/espn_nba_team_boxscores/team_box_{season}.parquet"
ODDS_URL = (
    "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
    "/events/{0}/competitions/{0}/odds"
)

# ESPN abbreviations that differ from the standard (and The Odds API's).
ABBREVIATIONS = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA",
                 "WSH": "WAS"}  # fmt: skip

# ESPN's franchise ids; higher ids are All-Star and exhibition teams.
FRANCHISE_IDS = range(1, 31)

# ESPN's season types: 1 preseason and 4 All-Star are dropped.
SEASON_TYPES = {2: "regular", 3: "playoffs", 5: "play_in"}

# Sportsbooks in order of preference; any other book comes after them.
# Prediction sites (numberfire, teamrankings, accuscore), the "Opening" line
# and in-game ("Live Odds") lines are never used.
PROVIDERS = (
    "consensus",
    "DraftKings",
    "ESPN BET",
    "Caesars Sportsbook",
    "Caesars Sportsbook (New Jersey)",
    "Westgate",
    "BOVADA.lv",
    "BETONLINE.ag",
    "5Dimes.eu",
)
NOT_BOOKS = {"numberfire", "teamrankings", "accuscore", "Opening"}

# Box-score columns kept, with their games-table names.
BOX_COLUMNS = {
    "field_goals_made": "fgm",
    "field_goals_attempted": "fga",
    "three_point_field_goals_made": "fg3m",
    "three_point_field_goals_attempted": "fg3a",
    "free_throws_made": "ftm",
    "free_throws_attempted": "fta",
    "offensive_rebounds": "oreb",
    "defensive_rebounds": "dreb",
    "assists": "ast",
    "steals": "stl",
    "blocks": "blk",
    "total_turnovers": "tov",
    "fouls": "pf",
    "points_in_paint": "paint_points",
    "fast_break_points": "fast_break_points",
    "turnover_points": "turnover_points",
}

# Longest rest counted, in days (season openers get it too).
MAX_REST = 10

# Odds lookahead: upcoming games starting within this many days get lines.
LINES_DAYS = 3

# The first season (by ending year) with betting lines.
FIRST_LINES_SEASON = 2013


def season_of(day: datetime.date) -> int:
    """The season a date belongs to, by its ending year (2025-26 is 2026)."""
    return day.year + 1 if day.month >= 8 else day.year


def season_complete(season: int, today: datetime.datetime) -> bool:
    """Whether nothing in ``season`` can change (the Finals end in June)."""
    return today.date() > datetime.date(season, 7, 31)


def team_key(team_id, abbreviation) -> str:
    """A franchise's games-table key: its current standard abbreviation."""
    return CURRENT.get(int(team_id)) or ABBREVIATIONS.get(abbreviation, abbreviation)


# ESPN franchise id -> current abbreviation (fixed since the 2014-15 renames).
CURRENT = {
    1: "ATL", 2: "BOS", 3: "NOP", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GSW", 10: "HOU", 11: "IND", 12: "LAC", 13: "LAL", 14: "MIA",
    15: "MIL", 16: "MIN", 17: "BKN", 18: "NYK", 19: "ORL", 20: "PHI", 21: "PHX",
    22: "POR", 23: "SAC", 24: "SAS", 25: "OKC", 26: "UTA", 27: "WAS", 28: "TOR",
    29: "MEM", 30: "CHA",
}  # fmt: skip


# -------------------------------------------------------------------- cache
class Cache:
    """Files that cannot change any more, under ``directory`` (``None``:
    nothing is cached)."""

    def __init__(self, directory: str | None):
        self.directory = Path(directory) if directory else None

    def path(self, name: str) -> Path | None:
        return self.directory / name if self.directory else None

    def read_bytes(self, name: str) -> bytes | None:
        path = self.path(name)
        return path.read_bytes() if path is not None and path.exists() else None

    def write_bytes(self, name: str, data: bytes) -> None:
        path = self.path(name)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def read_json(self, name: str) -> dict:
        data = self.read_bytes(name)
        return json.loads(data) if data else {}

    def write_json(self, name: str, data: dict) -> None:
        self.write_bytes(name, json.dumps(data, sort_keys=True).encode())


def _get(url: str, retries: int = 4) -> httpx.Response:
    for attempt in range(retries + 1):
        try:
            response = httpx.get(url, timeout=60, follow_redirects=True)
            if response.status_code != 429 and response.status_code < 500:
                return response
        except httpx.TransportError:
            if attempt == retries:
                raise
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return response


def season_file(url: str, name: str, final: bool, cache: Cache) -> pd.DataFrame:
    """A season's sportsdataverse parquet file (empty if it has none yet)."""
    data = cache.read_bytes(name) if final else None
    if data is None:
        response = _get(url)
        if response.status_code == 404:
            return pd.DataFrame()
        response.raise_for_status()
        data = response.content
        if final:
            cache.write_bytes(name, data)
    return pd.read_parquet(io.BytesIO(data))


# -------------------------------------------------------------------- lines
def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _moneyline(value) -> float:
    """American odds, or NaN for the placeholders some books report."""
    value = _number(value)
    return value if abs(value) >= 100 else np.nan


def _books(items: list[dict]) -> list[dict]:
    rank = {p: i for i, p in enumerate(PROVIDERS)}
    books = [
        item
        for item in items
        if (name := (item.get("provider") or {}).get("name") or "")
        and name not in NOT_BOOKS
        and "live" not in name.lower()
    ]
    return sorted(books, key=lambda i: rank.get(i["provider"]["name"], len(rank)))


def parse_odds(data: dict) -> dict:
    """ESPN's odds for one game -> the home team's lines.

    ``spread_line`` is the home team's expected margin (positive = home
    favored; ESPN's ``spread`` is the home handicap), with both sides' spread
    prices; ``total_line`` with the over / under prices; both moneylines.
    Each market comes from the most preferred book that has it, its prices
    from the same book.
    """
    books = _books(data.get("items") or [])
    out = {}
    for item in books:
        spread = _number(item.get("spread"))
        if np.isfinite(spread):
            home, away = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
            out |= {
                "spread_line": -spread if spread else 0.0,
                "spread_odds": _moneyline(home.get("spreadOdds")),
                "opp_spread_odds": _moneyline(away.get("spreadOdds")),
                "spread_provider": item["provider"]["name"],
            }
            break
    for item in books:
        total = _number(item.get("overUnder"))
        if np.isfinite(total) and total > 0:
            out |= {
                "total_line": total,
                "over_odds": _moneyline(item.get("overOdds")),
                "under_odds": _moneyline(item.get("underOdds")),
                "total_provider": item["provider"]["name"],
            }
            break
    for item in books:
        home = _moneyline((item.get("homeTeamOdds") or {}).get("moneyLine"))
        away = _moneyline((item.get("awayTeamOdds") or {}).get("moneyLine"))
        if np.isfinite(home) and np.isfinite(away):
            out |= {
                "moneyline": home,
                "opp_moneyline": away,
                "moneyline_provider": item["provider"]["name"],
            }
            break
    return {k: (None if isinstance(v, float) and np.isnan(v) else v)
            for k, v in out.items()}  # fmt: skip


def fetch_odds(game_id: str) -> dict:
    response = _get(ODDS_URL.format(game_id))
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return parse_odds(response.json())


def season_lines(
    season: int,
    final_ids: list[str],
    upcoming_ids: list[str],
    cache: Cache,
    workers: int = 8,
) -> dict[str, dict]:
    """``{game_id: lines}`` for a season's finished games (cached) and the
    given upcoming ones (fetched every time)."""
    name = f"odds_{season}.json"
    cached = cache.read_json(name)
    missing = [g for g in final_ids if g not in cached]
    wanted = missing + [g for g in upcoming_ids if g not in cached]
    if wanted:
        logger.info("%d: fetching lines of %d games", season, len(wanted))
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            fetched = dict(zip(wanted, pool.map(fetch_odds, wanted)))
        if missing:
            cache.write_json(name, cached | {g: fetched[g] for g in missing})
        cached = cached | fetched
    return {g: cached[g] for g in final_ids + upcoming_ids if g in cached}


# -------------------------------------------------------------------- games
def schedule_frame(schedule: pd.DataFrame) -> pd.DataFrame:
    """sportsdataverse schedule -> one row per NBA game (home / away
    columns), typed. All-Star, preseason and exhibition games are dropped."""
    if schedule.empty:
        return pd.DataFrame()
    games = schedule.copy()
    games["season_type"] = pd.to_numeric(games["season_type"], errors="coerce")
    games["game_type"] = games["season_type"].map(SEASON_TYPES)
    games = games.dropna(subset=["game_type"])
    for side in ("home", "away"):
        games[f"{side}_id"] = pd.to_numeric(games[f"{side}_id"], errors="coerce")
        games = games[games[f"{side}_id"].isin(FRANCHISE_IDS)]
        games[f"{side}_score"] = pd.to_numeric(games[f"{side}_score"], errors="coerce")
    games["game_id"] = games["game_id"].astype(str)
    games["start"] = pd.to_datetime(games["date"], utc=True, errors="coerce")
    games["start_date"] = games["start"].dt.strftime("%Y-%m-%dT%H:%MZ")
    games["completed"] = games["status_type_completed"].fillna(False).astype(bool)
    games["neutral_site"] = games["neutral_site"].fillna(False).astype(bool)
    return games.drop_duplicates("game_id").reset_index(drop=True)


def box_frame(team_box: pd.DataFrame) -> pd.DataFrame:
    """sportsdataverse team box scores -> ``game_id``, ``team_id`` and the
    :data:`BOX_COLUMNS` stats."""
    cols = ["game_id", "team_id", *BOX_COLUMNS.values()]
    if team_box.empty:
        return pd.DataFrame(columns=cols)
    box = team_box.rename(columns=BOX_COLUMNS).reindex(columns=cols)
    box["game_id"] = box["game_id"].astype(str)
    box["team_id"] = pd.to_numeric(box["team_id"], errors="coerce")
    stats = list(BOX_COLUMNS.values())
    box[stats] = box[stats].apply(pd.to_numeric, errors="coerce")
    return box.drop_duplicates(["game_id", "team_id"])


def day_numbers(games: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """``(game_date, day, week)`` of every game.

    ``game_date`` is the US Eastern date, ``day`` the days since the season's
    first game and ``week`` the Monday-to-Sunday week of the season (1: the
    opener's).
    """
    local = games["start"].dt.tz_convert("America/New_York")
    date = local.dt.tz_localize(None).dt.normalize()
    first = date.groupby(games["season"]).transform("min")
    monday = first - pd.to_timedelta(first.dt.weekday, unit="D")
    day = (date - first).dt.days
    week = (date - monday).dt.days // 7 + 1
    return date.dt.strftime("%Y-%m-%d"), day, week


def invert(home: pd.DataFrame) -> pd.DataFrame:
    """Both perspectives of one-row-per-game ``home_*`` / ``away_*`` columns."""

    def side(team: str, opp: str, location) -> pd.DataFrame:
        renames = {}
        for col in home:
            if col.startswith(f"{team}_"):
                renames[col] = col.removeprefix(f"{team}_")
            elif col.startswith(f"{opp}_"):
                renames[col] = "opp_" + col.removeprefix(f"{opp}_")
        out = home.rename(columns=renames)
        out["location"] = location
        return out

    neutral = home["neutral_site"].to_numpy()
    away = side("away", "home", np.where(neutral, 0, -1))
    away["spread_line"] = -away["spread_line"]
    home = side("home", "away", np.where(neutral, 0, 1))
    return pd.concat([home, away], ignore_index=True)


def rest_days(rows: pd.DataFrame) -> pd.Series:
    """Days since each team's previous game (1: a back-to-back; capped, and
    openers get the cap)."""
    order = rows.sort_values("game_date")
    dates = pd.to_datetime(order["game_date"])
    previous = dates.groupby([order["season"], order["team"]]).shift()
    days = (dates - previous).dt.days.clip(upper=MAX_REST)
    return days.fillna(MAX_REST).reindex(rows.index)


LINE_COLUMNS = ["spread_line", "spread_odds", "opp_spread_odds", "total_line",
                "over_odds", "under_odds", "moneyline", "opp_moneyline"]  # fmt: skip


def build_games(
    schedule: pd.DataFrame,
    team_box: pd.DataFrame,
    lines: dict[str, dict] | None = None,
    today: datetime.datetime | None = None,
) -> pd.DataFrame:
    """One row per team per game from ESPN's schedule, box scores and lines.

    Past games that were never completed (postponed) are dropped; future
    ones are kept as upcoming games with missing results and stats.
    """
    from .features import STATS_COLUMNS

    today = today or datetime.datetime.now(datetime.timezone.utc)
    games = schedule_frame(schedule)
    if games.empty:
        return games
    upcoming = ~games["completed"] | games["home_score"].isna()
    stale = upcoming & (games["start"] < pd.Timestamp(today) - pd.Timedelta(days=1))
    games = games[~stale].copy()
    games.loc[upcoming, ["home_score", "away_score"]] = np.nan
    games["game_date"], games["day"], games["week"] = day_numbers(games)
    games["postseason"] = games["game_type"].ne("regular").astype(int)

    market = pd.DataFrame.from_dict(lines or {}, orient="index")
    market = market.reindex(columns=LINE_COLUMNS).rename(
        columns={
            "moneyline": "home_moneyline",
            "opp_moneyline": "away_moneyline",
            "spread_odds": "home_spread_odds",
            "opp_spread_odds": "away_spread_odds",
        }
    )
    games = games.merge(market, left_on="game_id", right_index=True, how="left")
    # over / under prices belong to the game, not a side
    games = games.rename(columns={"over_odds": "ou_over", "under_odds": "ou_under"})

    keep = ["game_id", "season", "day", "week", "game_date", "start_date",
            "game_type", "postseason", "neutral_site", "notes_headline",
            "spread_line", "total_line", "ou_over", "ou_under"]  # fmt: skip
    sides = ["id", "abbreviation", "display_name", "score", "moneyline",
             "spread_odds"]  # fmt: skip
    cols = keep + [f"{s}_{c}" for s in ("home", "away") for c in sides]
    rows = invert(games.reindex(columns=cols))
    rows = rows.rename(
        columns={
            "display_name": "team_name",
            "opp_display_name": "opp_name",
            "score": "points",
            "opp_score": "opp_points",
            "ou_over": "over_odds",
            "ou_under": "under_odds",
            "notes_headline": "notes",
        }
    )
    rows["team"] = [team_key(i, a) for i, a in zip(rows["id"], rows["abbreviation"])]
    rows["opp_team"] = [
        team_key(i, a) for i, a in zip(rows["opp_id"], rows["opp_abbreviation"])
    ]
    rows["result"] = rows["points"] - rows["opp_points"]
    rows["total"] = rows["points"] + rows["opp_points"]
    rows["rest"] = rest_days(rows)
    opp_rest = rows[["game_id", "team", "rest"]].rename(
        columns={"team": "opp_team", "rest": "opp_rest"}
    )
    rows = rows.merge(opp_rest, on=["game_id", "opp_team"], how="left")

    box = box_frame(team_box)
    stats = [c for c in STATS_COLUMNS if c != "points"]
    box = box.reindex(columns=["game_id", "team_id", *stats])
    rows = rows.merge(
        box.rename(columns={"team_id": "id"}), on=["game_id", "id"], how="left"
    )
    rows = rows.merge(
        box.rename(columns={"team_id": "opp_id", **{c: f"opp_{c}" for c in stats}}),
        on=["game_id", "opp_id"],
        how="left",
    )
    # finished games' stats only: a stray box score cannot leak into a preview
    rows.loc[rows["result"].isna(), stats + [f"opp_{c}" for c in stats]] = np.nan
    rows = rows.drop(columns=["id", "opp_id", "abbreviation", "opp_abbreviation"])
    return rows.sort_values(["season", "day", "game_id", "location"]).reset_index(
        drop=True
    )


# ----------------------------------------------------------------- download
def fetch_season(
    season: int,
    today: datetime.datetime,
    cache: Cache,
    lines_days: int = LINES_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """``(schedule, team box scores, lines)`` of one season."""
    final = season_complete(season, today)
    schedule = season_file(
        SCHEDULE_URL.format(season=season), f"schedule_{season}.parquet", final, cache
    )
    box = season_file(
        TEAM_BOX_URL.format(season=season), f"team_box_{season}.parquet", final, cache
    )
    lines = {}
    games = schedule_frame(schedule)
    if season >= FIRST_LINES_SEASON and len(games):
        now = pd.Timestamp(today)
        done = games["completed"]
        soon = ~done & games["start"].between(
            now - pd.Timedelta(hours=12), now + pd.Timedelta(days=lines_days)
        )
        lines = season_lines(
            season,
            list(games.loc[done, "game_id"]),
            list(games.loc[soon, "game_id"]),
            cache,
        )
    return schedule, box, lines


def download(
    output_file: str | None = None,
    first_season: int = 2004,
    last_season: int | None = None,
    cache_dir: str | None = "data/nba/espn_cache",
) -> pd.DataFrame:
    """Download every season's games, box scores and lines.

    Args:
        output_file: Also write the games table here.
        first_season / last_season: Seasons to download, by ending year
            (default: 2003-04 through the current season). ESPN's betting
            lines start in 2012-13.
        cache_dir: Reuse finished seasons' files and finished games' lines
            from here (``None``: always download). A full download makes
            about 18,000 odds requests; a daily refresh a few dozen.
    """
    today = datetime.datetime.now(datetime.timezone.utc)
    last_season = last_season or season_of(today.date())
    cache = Cache(cache_dir)
    schedules, boxes, lines = [], [], {}
    for season in range(first_season, last_season + 1):
        schedule, box, season_lines_ = fetch_season(season, today, cache)
        schedules.append(schedule)
        boxes.append(box)
        lines |= season_lines_
        logger.info("%d: %d games, %d with lines", season, len(schedule),
                    len(season_lines_))  # fmt: skip
    games = build_games(
        pd.concat(schedules, ignore_index=True),
        pd.concat(boxes, ignore_index=True),
        lines,
        today=today,
    )
    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)
    return games
