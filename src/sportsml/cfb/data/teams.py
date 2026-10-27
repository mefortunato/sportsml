import datetime

import pandas as pd

from .download import FCS, Client, season_of, snake_keys

# The pooled FCS opponent (see download.FCS).
FCS_TEAM = {
    "team": FCS,
    "name": "FCS opponent",
    "nickname": "FCS",
    "abbr": "FCS",
    "color": "#6b7280",
    "color2": "#d1d5db",
    "logo": None,
    "conference": FCS,
    "division": None,
}


def _color(value) -> str | None:
    if not isinstance(value, str) or not value.strip("#"):
        return None
    return value if value.startswith("#") else f"#{value}"


def teams_frame(records: list[dict]) -> pd.DataFrame:
    """CFBD ``/teams/fbs`` -> web team metadata, plus the pooled FCS team.

    Keys are school names, as in the games table. A conference's division
    (where it still has them) is shown as ``"<conference> <division>"``.
    """
    rows = []
    for team in map(snake_keys, records):
        conference, division = team.get("conference"), team.get("division")
        logos = team.get("logos") or []
        rows.append(
            {
                "team": team["school"],
                "name": team["school"],
                "nickname": team.get("mascot") or team["school"],
                "abbr": team.get("abbreviation") or team["school"][:4].upper(),
                "color": _color(team.get("color")),
                "color2": _color(team.get("alternate_color") or team.get("alt_color")),
                "logo": logos[0] if logos else None,
                "conference": conference,
                "division": f"{conference} {division}"
                if conference and division
                else None,
            }
        )
    rows.append(FCS_TEAM)
    return pd.DataFrame(rows).drop_duplicates("team").reset_index(drop=True)


def load_teams(season: int | None = None) -> pd.DataFrame:
    """This season's FBS teams (name, colors, logo, conference) from CFBD."""
    today = datetime.datetime.now(datetime.timezone.utc).date()
    season = season or season_of(today)
    return teams_frame(Client().get("/teams/fbs", year=season))
