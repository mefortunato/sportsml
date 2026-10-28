import concurrent.futures
import datetime

import httpx
import pandas as pd

from ... import espn
from .download import MEN, NON_D1, WOMEN, College, season_of

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/{league}"

# The pooled non-Division I opponent (see download.NON_D1).
NON_D1_TEAM = {
    "team": NON_D1,
    "name": "Non-Division I opponent",
    "nickname": "Non-D1",
    "abbr": "N-D1",
    "color": "#6b7280",
    "color2": "#d1d5db",
    "logo": None,
    "conference": NON_D1,
    "division": None,
}


def _core(url: str) -> dict:
    response = httpx.get(url, params={"limit": 100}, timeout=30)
    response.raise_for_status()
    return response.json()


def conferences(league: str, season: int) -> list[dict]:
    """This season's Division I conferences from ESPN's core API, each with
    its ``shortName`` and its ``teams`` (ids), as :func:`espn.teams_frame`
    takes them (the site API's ``/groups`` lists only some of them)."""
    base = f"{CORE.format(league=league)}/seasons/{season}/types/2/groups"
    refs = [item["$ref"] for item in _core(f"{base}/50/children")["items"]]

    def conference(ref: str) -> dict:
        group = _core(ref)
        teams = _core(f"{base}/{group['id']}/teams")["items"]
        ids = [item["$ref"].split("/teams/")[1].split("?")[0] for item in teams]
        return {
            "name": group.get("name"),
            "shortName": group.get("shortName") or group.get("abbreviation"),
            "teams": [{"id": team} for team in ids],
        }

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        return list(pool.map(conference, refs))


def teams_frame(teams: list[dict], groups: list[dict]) -> pd.DataFrame:
    """ESPN's Division I ``/teams`` and :func:`conferences` -> web team
    metadata, plus the pooled non-Division I team. Keys are schools (ESPN's
    team ``location``), as in the games table."""
    frame = espn.teams_frame(
        teams, groups, key=lambda team: team["location"], nested=False, abbr=True
    )
    return pd.concat([frame, pd.DataFrame([NON_D1_TEAM])], ignore_index=True)


def load_college_teams(college: College) -> pd.DataFrame:
    """This season's Division I teams (names, colors, logos, conferences)."""
    today = datetime.datetime.now(datetime.timezone.utc).date()
    league = college.league.league
    teams = espn.site_json("basketball", league, "teams", groups=50, limit=500)
    return teams_frame(
        teams["sports"][0]["leagues"][0]["teams"],
        conferences(league, season_of(today)),
    )


def load_teams() -> pd.DataFrame:
    return load_college_teams(MEN)


def load_women_teams() -> pd.DataFrame:
    return load_college_teams(WOMEN)
