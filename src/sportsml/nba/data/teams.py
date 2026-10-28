import httpx
import pandas as pd

from .download import team_key

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def _color(value) -> str | None:
    if not isinstance(value, str) or not value.strip("#"):
        return None
    return value if value.startswith("#") else f"#{value}"


def teams_frame(teams: list[dict], groups: list[dict]) -> pd.DataFrame:
    """ESPN ``/teams`` and ``/groups`` -> web team metadata.

    Keys are the games table's (``team_key``); the conference is ``East`` /
    ``West`` and the division its name (``Atlantic``, ...).
    """
    placed = {}
    for conference in groups:
        for division in conference.get("children") or []:
            for team in division.get("teams") or []:
                placed[str(team["id"])] = (
                    conference.get("abbreviation") or conference["name"],
                    division["name"],
                )
    rows = []
    for team in teams:
        team = team.get("team", team)
        logos = team.get("logos") or []
        conference, division = placed.get(str(team["id"]), (None, None))
        rows.append(
            {
                "team": team_key(team["id"], team["abbreviation"]),
                "name": team["displayName"],
                "nickname": team.get("shortDisplayName") or team.get("name"),
                "color": _color(team.get("color")),
                "color2": _color(team.get("alternateColor")),
                "logo": logos[0]["href"] if logos else None,
                "conference": conference,
                "division": division,
            }
        )
    return pd.DataFrame(rows).drop_duplicates("team").reset_index(drop=True)


def load_teams() -> pd.DataFrame:
    """The 30 teams' names, colors, logos, conferences and divisions from ESPN."""

    def get(path: str) -> dict:
        response = httpx.get(f"{SITE}/{path}", timeout=30)
        response.raise_for_status()
        return response.json()

    teams = get("teams")["sports"][0]["leagues"][0]["teams"]
    return teams_frame(teams, get("groups")["groups"])
