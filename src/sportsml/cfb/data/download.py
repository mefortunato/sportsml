import datetime
import logging
import os
from pathlib import Path

import httpx
import pandas as pd
import tqdm

logger = logging.getLogger(__name__)

GAME_URL = "https://api.collegefootballdata.com/games/teams"
CALENDAR_URL = "https://api.collegefootballdata.com/calendar"


def _headers() -> dict:
    key = os.getenv("CFBD_API_KEY")
    if not key:
        raise RuntimeError("set CFBD_API_KEY (free key: collegefootballdata.com)")
    return {"Authorization": f"Bearer {key}"}


def calendar(year: int):
    resp = httpx.get(CALENDAR_URL, params={"year": year}, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def season_weeks(calendar_weeks: list[dict]) -> list[dict]:
    """Non-spring weeks in chronological order.

    CFBD numbers postseason weeks from 1 again, so the API week number cannot
    order games; position in this list can.
    """
    weeks = [w for w in calendar_weeks if "spring" not in w["seasonType"]]
    return sorted(weeks, key=_week_start)


def _week_start(week: dict) -> str:
    # v2 of the API renamed firstGameStart -> startDate
    return week.get("startDate") or week.get("firstGameStart") or ""


def download_games(year: int, week: int, season_type="regular") -> pd.DataFrame:
    resp = httpx.get(
        GAME_URL,
        params={"year": year, "week": week, "seasonType": season_type},
        headers=_headers(),
    )
    resp.raise_for_status()
    games = [game_to_dataframe(game) for game in resp.json()]
    if not games:
        return pd.DataFrame()
    games = pd.concat(games, ignore_index=True)
    games["season"] = year
    return games


def possession_time(time: str):
    minutes, seconds = time.split(":")
    return int(minutes) + int(seconds) / 60


def game_to_dataframe(game) -> pd.DataFrame:
    """Both teams' rows (team stats + opponent stats) of one API game."""
    stats = []
    for team in game["teams"]:
        df = pd.DataFrame(team["stats"]).set_index("category").T

        if "possessionTime" in df:
            df["possessionTime"] = df["possessionTime"].apply(possession_time)

        if "totalPenaltiesYards" in df:
            df["totalPenaltiesYards"] = df["totalPenaltiesYards"].str.replace("--", "-")
            df[["totalPenalties", "totalPenaltiesYards"]] = df.pop(
                "totalPenaltiesYards"
            ).str.split("-", expand=True)

        if "completionAttempts" in df:
            df["completionAttempts"] = df["completionAttempts"].str.replace("--", "-")
            df[["passingCompletions", "passingAttempts"]] = df.pop(
                "completionAttempts"
            ).str.split("-", expand=True)

        if "fourthDownEff" in df:
            df["fourthDownEff"] = df["fourthDownEff"].str.replace("--", "-")
            df[["fourthDownConv", "fourthDownAtt"]] = df.pop("fourthDownEff").str.split(
                "-", expand=True
            )

        if "thirdDownEff" in df:
            df["thirdDownEff"] = df["thirdDownEff"].str.replace("--", "-")
            df[["thirdDownConv", "thirdDownAtt"]] = df.pop("thirdDownEff").str.split(
                "-", expand=True
            )

        df = df.apply(pd.to_numeric, errors="coerce")
        df["team"] = team["team"]
        df["conference"] = team.get("conference")
        df["location"] = 1 if team["homeAway"] == "home" else -1
        df["points"] = team["points"]
        stats.append(df.reset_index(drop=True))
    df = pd.concat(
        [
            pd.concat([stats[0], stats[1].add_prefix("opp_")], axis=1),
            pd.concat([stats[1], stats[0].add_prefix("opp_")], axis=1),
        ],
        axis=0,
    ).drop(columns=["opp_location"])
    df["result"] = df["points"] - df["opp_points"]
    df["game_id"] = str(game["id"])
    return df.reset_index(drop=True)


def download(output_file: str = None, first_season: int = 2004) -> pd.DataFrame:
    today = datetime.datetime.now(datetime.timezone.utc).isoformat()
    years = range(first_season, datetime.datetime.today().year + 1)
    games = []
    for year in tqdm.tqdm(years, desc="Years"):
        weeks = season_weeks(calendar(year))
        for order, week in enumerate(tqdm.tqdm(weeks, desc=str(year), leave=False), 1):
            if today < _week_start(week):
                continue
            week_games = download_games(year, week["week"], week["seasonType"])
            if week_games.empty:
                logger.warning(
                    "no games for %s %s week %s", year, week["seasonType"], week["week"]
                )
                continue
            week_games["week"] = order
            week_games["api_week"] = week["week"]
            week_games["season_type"] = week["seasonType"]
            games.append(week_games)
    games = pd.concat(games).reset_index(drop=True)
    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)
    return games
