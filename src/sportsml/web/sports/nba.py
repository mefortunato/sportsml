import pandas as pd

from ...nba.data.teams import load_teams
from ..views import SportView, Stat, column, total


def kickoff(row: pd.Series) -> str | None:
    """``YYYY-MM-DD HH:MM`` US Eastern."""
    start = pd.to_datetime(row.get("start_date"), utc=True, errors="coerce")
    if pd.isna(start):
        return None
    return start.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M")


def playoffs(games: pd.DataFrame) -> dict[int, dict[str, str]]:
    """NBA champion and runner-up, and the conference finals losers.

    ESPN's playoff notes changed wording over the years (and are blank in
    some), so the rounds come from the bracket: the Finals are the series of
    the season's last playoff game, and each finalist's previous playoff
    opponent lost its conference finals. A season is marked once its
    champion has won four Finals games.
    """
    out: dict[int, dict[str, str]] = {}
    rows = games[games["game_type"].eq("playoffs")].sort_values(["season", "day"])
    for season, season_rows in rows.groupby("season"):
        last = season_rows.iloc[-1]
        finalists = {last["team"], last["opp_team"]}
        finals = season_rows[
            season_rows["team"].isin(finalists)
            & season_rows["opp_team"].isin(finalists)
        ]
        wins = finals[finals["result"] > 0]["team"].value_counts()
        if wins.empty or wins.max() < 4:
            continue  # the playoffs are still on
        champion = wins.idxmax()
        stages = {
            str(team): "champion" if team == champion else "runner_up"
            for team in finalists
        }
        for team in finalists:
            earlier = season_rows[
                season_rows["team"].eq(team) & ~season_rows["opp_team"].isin(finalists)
            ]
            if len(earlier):
                stages.setdefault(str(earlier.iloc[-1]["opp_team"]), "semifinal")
        out[int(season)] = stages
    return out


def date_name(row: pd.Series) -> str | None:
    """``Oct 28``: NBA dates are game days, shown by their calendar date."""
    day = pd.to_datetime(row.get("game_date"), errors="coerce")
    return None if pd.isna(day) else f"{day:%b} {day.day}"


def pct(made: str, attempted: str):
    def value(rows: pd.DataFrame) -> pd.Series:
        att = rows[attempted]
        return 100 * rows[made] / att.where(att > 0)

    return value


VIEW = SportView(
    sport="nba",
    label="NBA",
    date_label="Day",
    load_teams=load_teams,
    score=("points", "opp_points"),
    kickoff=kickoff,
    playoffs=playoffs,
    playoff_labels={
        "champion": "Won NBA Finals",
        "runner_up": "Lost NBA Finals",
        "semifinal": "Lost conference finals",
    },
    date_name=date_name,
    upcoming_dates=7,
    split_season=True,
    recent_games=8,
    stats=(
        Stat("points", "Points scored", column("points")),
        Stat("points_allowed", "Points allowed", column("opp_points"), 1, False),
        Stat("fg_pct", "Field goal %", pct("fgm", "fga")),
        Stat("fg3_pct", "Three-point %", pct("fg3m", "fg3a")),
        Stat("fg3a", "Three-point attempts", column("fg3a")),
        Stat("ft_pct", "Free throw %", pct("ftm", "fta")),
        Stat("rebounds", "Rebounds", total("oreb", "dreb")),
        Stat("oreb", "Offensive rebounds", column("oreb")),
        Stat("assists", "Assists", column("ast")),
        Stat("turnovers", "Turnovers", column("tov"), 1, False),
        Stat("steals", "Steals", column("stl")),
        Stat("blocks", "Blocks", column("blk")),
    ),
)
