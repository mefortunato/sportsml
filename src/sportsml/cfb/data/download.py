"""College football games, box scores and betting lines from CollegeFootballData.

The schedule (``/games``) is the source of truth for which games exist, so
upcoming games are kept with a missing result. Team box scores
(``/games/teams``) and the betting market (``/lines``) are joined onto both
perspectives of every game, like the NFL's
:func:`~sportsml.nfl.data.download.build_games`.

Only games with at least one FBS team are kept. FCS (and lower-division)
opponents are pooled into one team, :data:`FCS`: an FCS school plays one or
two FBS games a year, too few to give it a team state of its own, while the
pooled team's last games are a fair picture of a typical FCS opponent. The
school's own name stays in ``team_name`` / ``opp_name``.

Responses of finished seasons and finished weeks are cached on disk
(``cache_dir``), so a daily refresh only fetches the current season's
schedule, lines and newest box scores (CFBD's free tier allows 1,000 calls
a month; a full download from 2004 takes about 400, a refresh 2-3).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

API = "https://api.collegefootballdata.com"

# Team key of every FCS / lower-division opponent.
FCS = "FCS"

# Sportsbooks in order of preference; any other provider comes after them.
PROVIDERS = (
    "consensus",
    "DraftKings",
    "ESPN Bet",
    "Bovada",
    "William Hill (New Jersey)",
    "Caesars Sportsbook (Colorado)",
    "teamrankings",
    "numberfire",
)

# Box-score categories that come as "made-attempted" strings.
SPLIT_STATS = {
    "totalPenaltiesYards": ("totalPenalties", "totalPenaltiesYards"),
    "completionAttempts": ("passingCompletions", "passingAttempts"),
    "fourthDownEff": ("fourthDownConv", "fourthDownAtt"),
    "thirdDownEff": ("thirdDownConv", "thirdDownAtt"),
}

# Longest rest counted, in days (season openers get it too).
MAX_REST = 21


def snake(key: str) -> str:
    """``homeTeam`` -> ``home_team`` (v2 of the API is camelCase, v1 snake)."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower()


def snake_keys(record: dict) -> dict:
    return {snake(k): v for k, v in record.items()}


def season_of(day: datetime.date) -> int:
    """The season a date belongs to (bowls in January count as last year's)."""
    return day.year if day.month >= 3 else day.year - 1


class Client:
    """``GET`` with the API key, retries on rate limits and an on-disk cache
    for responses that cannot change any more."""

    def __init__(self, cache_dir: str | None = None, retries: int = 4):
        key = os.getenv("CFBD_API_KEY")
        if not key:
            raise RuntimeError("set CFBD_API_KEY (free key: collegefootballdata.com)")
        self.headers = {"Authorization": f"Bearer {key}"}
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.retries = retries
        self.calls = 0

    def _path(self, path: str, params: dict) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps([path, sorted(params.items())])
        name = hashlib.sha1(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{path.strip('/').replace('/', '_')}-{name}.json"

    def get(self, path: str, final: bool = False, **params) -> list:
        """The JSON response; ``final`` responses are cached and reused."""
        cached = self._path(path, params)
        if cached is not None and cached.exists():
            return json.loads(cached.read_text())
        for attempt in range(self.retries + 1):
            self.calls += 1
            resp = httpx.get(
                API + path, params=params, headers=self.headers, timeout=60
            )
            if resp.status_code != 429 and resp.status_code < 500:
                break
            if attempt == self.retries:
                break
            time.sleep(2 ** (attempt + 1))
        resp.raise_for_status()
        data = resp.json()
        if final and cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(data))
        return data


# ----------------------------------------------------------------- schedule
def schedule_frame(records: list[dict]) -> pd.DataFrame:
    """One row per ``/games`` game, snake_case columns, typed."""
    games = pd.DataFrame([snake_keys(r) for r in records])
    if games.empty:
        return games
    # v1 called the classification "division"
    for side in ("home", "away"):
        if f"{side}_classification" not in games and f"{side}_division" in games:
            games[f"{side}_classification"] = games[f"{side}_division"]
        if f"{side}_classification" not in games:
            games[f"{side}_classification"] = "fbs"
    games["start"] = pd.to_datetime(games["start_date"], utc=True, errors="coerce")
    for col in ("neutral_site", "conference_game", "completed", "start_time_tbd"):
        if col not in games:
            games[col] = False
        games[col] = games[col].fillna(False).astype(bool)
    for col in ("home_points", "away_points"):
        games[col] = pd.to_numeric(games[col], errors="coerce")
    games["id"] = games["id"].astype(str)
    return games


def chronological_weeks(games: pd.DataFrame) -> pd.Series:
    """Week of the season that orders every game, bowls included.

    Regular-season games keep the API's week. CFBD files the whole bowl
    season under postseason week 1, which would predict every playoff round
    from the same state; postseason games are numbered instead by the
    7-day block they fall in after the first bowl, following the last
    regular week.
    """
    week = pd.to_numeric(games["week"], errors="coerce")
    post = games["season_type"].eq("postseason")
    out = week.copy()
    for season, rows in games.groupby("season"):
        regular = rows.index[~post.loc[rows.index]]
        bowls = rows.index[post.loc[rows.index]]
        if not len(bowls):
            continue
        last = week.loc[regular].max() if len(regular) else 0
        # US time: kickoffs late on a Saturday are already Sunday in UTC
        day = (games.loc[bowls, "start"] - pd.Timedelta(hours=6)).dt.normalize()
        out.loc[bowls] = last + 1 + ((day - day.min()).dt.days // 7)
    return out.astype(int)


def game_types(games: pd.DataFrame) -> pd.Series:
    """``regular``, ``bowl``, ``playoff`` or ``final`` (national championship)."""
    notes = games.get("notes", pd.Series("", index=games.index)).fillna("")
    post = games["season_type"].eq("postseason")
    final = post & notes.str.contains("national championship", case=False)
    playoff = post & notes.str.contains(r"playoff|\bCFP\b", case=False)
    out = pd.Series("regular", index=games.index)
    out[post] = "bowl"
    out[playoff] = "playoff"
    out[final] = "final"
    return out


# ---------------------------------------------------------------- box score
def possession_time(time: str) -> float:
    minutes, seconds = str(time).split(":")
    return int(minutes) + int(seconds) / 60


def team_stats(team: dict) -> dict:
    """One team's ``/games/teams`` stats as numbers."""
    team = snake_keys(team)
    out = {}
    for stat in team.get("stats") or []:
        category, value = stat["category"], stat["stat"]
        if category in SPLIT_STATS:
            made, att = SPLIT_STATS[category]
            parts = str(value).replace("--", "-").split("-")
            if len(parts) == 2:
                out[made], out[att] = parts
        elif category == "possessionTime":
            try:
                out[category] = possession_time(value)
            except ValueError:
                pass
        else:
            out[category] = value
    out = {k: pd.to_numeric(v, errors="coerce") for k, v in out.items()}
    return out | {"team_name": team["team"]}


def box_scores(records: list[dict]) -> pd.DataFrame:
    """``/games/teams`` -> one row per team per game: ``game_id``,
    ``team_name`` and its stats."""
    rows = [
        {"game_id": str(game["id"]), **team_stats(team)}
        for game in records
        for team in game.get("teams") or []
    ]
    return pd.DataFrame(rows, columns=None if rows else ["game_id", "team_name"])


# -------------------------------------------------------------------- lines
def _ordered(lines: list[dict]) -> list[dict]:
    rank = {p: i for i, p in enumerate(PROVIDERS)}
    return sorted(lines, key=lambda line: (rank.get(line.get("provider"), 99),))


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _moneyline(value) -> float:
    """American odds, or NaN for the placeholders some books report."""
    value = _number(value)
    return value if abs(value) >= 100 else np.nan


def market(records: list[dict]) -> pd.DataFrame:
    """``/lines`` -> one row per game, from the home team's perspective.

    Each market comes from the most preferred book that has it
    (:data:`PROVIDERS`): ``spread_line`` (home team's expected margin, so
    positive = home favored), ``total_line``, and both moneylines from the
    same book. CFBD has no spread or over/under prices; bets on them are
    scored at -110.
    """
    rows = []
    for game in records:
        lines = _ordered([snake_keys(line) for line in game.get("lines") or []])
        row = {"game_id": str(game["id"])}
        for line in lines:
            spread = _number(line.get("spread"))
            if np.isfinite(spread):
                row |= {"spread_line": -spread, "spread_provider": line["provider"]}
                break
        for line in lines:
            total = _number(line.get("over_under"))
            if np.isfinite(total) and total > 0:
                row |= {"total_line": total, "total_provider": line["provider"]}
                break
        for line in lines:
            home = _moneyline(line.get("home_moneyline"))
            away = _moneyline(line.get("away_moneyline"))
            if np.isfinite(home) and np.isfinite(away):
                row |= {"moneyline": home, "opp_moneyline": away}
                row |= {"moneyline_provider": line["provider"]}
                break
        rows.append(row)
    return pd.DataFrame(rows, columns=None if rows else ["game_id"])


# -------------------------------------------------------------------- games
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
    """Days since each school's previous game (capped; openers get the cap)."""
    order = rows.sort_values("start")
    previous = order.groupby(["season", "team_name"])["start"].shift()
    days = (order["start"] - previous).dt.days.clip(upper=MAX_REST)
    return days.fillna(MAX_REST).reindex(rows.index)


def build_games(
    schedule: list[dict],
    team_box: list[dict] | pd.DataFrame,
    lines: list[dict] | pd.DataFrame | None = None,
    today: datetime.datetime | None = None,
) -> pd.DataFrame:
    """One row per team per game from CFBD's schedule, box scores and lines.

    Games without an FBS team are dropped, FCS sides are pooled into
    :data:`FCS`, and past games that were never completed (cancelled or
    postponed) are dropped; future ones are kept as upcoming games.
    """
    from .features import STATS_COLUMNS

    today = today or datetime.datetime.now(datetime.timezone.utc)
    games = schedule_frame(schedule)
    if games.empty:
        return games
    home_fbs = games["home_classification"].eq("fbs")
    away_fbs = games["away_classification"].eq("fbs")
    games = games[home_fbs | away_fbs].copy()
    upcoming = ~games["completed"] | games["home_points"].isna()
    cancelled = upcoming & (games["start"] < pd.Timestamp(today) - pd.Timedelta(days=1))
    games = games[~cancelled].copy()
    games.loc[upcoming, ["home_points", "away_points"]] = np.nan

    games["api_week"] = games["week"]
    games["week"] = chronological_weeks(games)
    games["game_type"] = game_types(games)
    games["postseason"] = games["season_type"].eq("postseason").astype(int)
    games["conference_game"] = games["conference_game"].astype(int)

    lines = lines if isinstance(lines, pd.DataFrame) else market(lines or [])
    lines = lines.rename(
        columns={
            "game_id": "id",
            "moneyline": "home_moneyline",
            "opp_moneyline": "away_moneyline",
        }
    )
    games = games.merge(lines, on="id", how="left")

    keep = ["id", "season", "week", "api_week", "season_type", "game_type",
            "start_date", "start_time_tbd", "neutral_site", "conference_game",
            "postseason", "venue", "notes", "spread_line", "total_line",
            "home_moneyline", "away_moneyline", "start"]  # fmt: skip
    sides = ["team", "conference", "classification", "points"]
    cols = keep + [f"{s}_{c}" for s in ("home", "away") for c in sides]
    games = games.reindex(columns=cols)
    rows = invert(games).rename(columns={"id": "game_id", "team": "team_name"})
    rows = rows.rename(columns={"opp_team": "opp_name"})

    rows["team"] = rows["team_name"].where(rows["classification"].eq("fbs"), FCS)
    rows["opp_team"] = rows["opp_name"].where(rows["opp_classification"].eq("fbs"), FCS)
    for prefix in ("", "opp_"):
        fcs = rows[f"{prefix}team"].eq(FCS)
        rows.loc[fcs, f"{prefix}conference"] = FCS
    rows["result"] = rows["points"] - rows["opp_points"]
    rows["total"] = rows["points"] + rows["opp_points"]
    rows["rest"] = rest_days(rows)
    rows.loc[rows["team"].eq(FCS), "rest"] = np.nan
    opp_rest = rows[["game_id", "team_name", "rest"]].rename(
        columns={"team_name": "opp_name", "rest": "opp_rest"}
    )
    rows = rows.merge(opp_rest, on=["game_id", "opp_name"], how="left")

    box = team_box if isinstance(team_box, pd.DataFrame) else box_scores(team_box)
    box = box.drop(columns=["points"], errors="ignore")
    box = box.drop_duplicates(["game_id", "team_name"])
    stats = [c for c in STATS_COLUMNS if c != "points"]
    box = box.reindex(columns=["game_id", "team_name", *stats])
    rows = rows.merge(box, on=["game_id", "team_name"], how="left")
    rows = rows.merge(
        box.rename(columns={"team_name": "opp_name", **{c: f"opp_{c}" for c in stats}}),
        on=["game_id", "opp_name"],
        how="left",
    )
    # finished games' stats only: a stray box score cannot leak into a preview
    rows.loc[rows["result"].isna(), stats + [f"opp_{c}" for c in stats]] = np.nan
    rows = rows.drop(columns=["start", "classification", "opp_classification"])
    return rows.sort_values(["season", "week", "game_id", "location"]).reset_index(
        drop=True
    )


# ----------------------------------------------------------------- download
def season_complete(season: int, today: datetime.datetime) -> bool:
    """Whether nothing in ``season`` can change (bowls end in mid-January)."""
    return today.date() > datetime.date(season + 1, 2, 15)


def fetch_season(client: Client, season: int, today: datetime.datetime) -> tuple:
    """``(schedule, box scores, lines)`` of one season."""
    final = season_complete(season, today)
    kwargs = {"year": season, "seasonType": "both"}
    schedule = client.get("/games", final=final, **kwargs)
    lines = client.get("/lines", final=final, **kwargs)

    games = schedule_frame(schedule)
    box = []
    if len(games):
        games = games[
            games["home_classification"].eq("fbs")
            | games["away_classification"].eq("fbs")
        ]
        for (season_type, week), rows in games.groupby(["season_type", "week"]):
            if not rows["completed"].any():
                continue
            box += client.get(
                "/games/teams",
                final=final or bool(rows["completed"].all()),
                year=season,
                week=int(week),
                seasonType=season_type,
            )
    return schedule, box, lines


def download(
    output_file: str | None = None,
    first_season: int = 2004,
    last_season: int | None = None,
    cache_dir: str | None = "data/cfb/cfbd_cache",
) -> pd.DataFrame:
    """Download every season's games, box scores and lines.

    Args:
        output_file: Also write the games table here.
        first_season / last_season: Seasons to download (default: through
            the current season). CFBD's box scores start in 2004; its
            betting lines in the 2010s.
        cache_dir: Reuse finished seasons' and weeks' responses from here
            (``None``: always download).
    """
    today = datetime.datetime.now(datetime.timezone.utc)
    last_season = last_season or season_of(today.date())
    client = Client(cache_dir)
    schedule, box, lines = [], [], []
    for season in range(first_season, last_season + 1):
        s, b, line = fetch_season(client, season, today)
        schedule += s
        box += b
        lines += line
        logger.info("%d: %d games (%d API calls so far)", season, len(s), client.calls)
    games = build_games(schedule, box, lines, today=today)
    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)
    return games
