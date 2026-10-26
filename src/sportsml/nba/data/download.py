import time
from pathlib import Path

import pandas as pd
import tqdm

from .features import STATS_COLUMNS

# First digit of LeagueGameFinder's SEASON_ID. Preseason (1) and All-Star (3)
# games are dropped.
SEASON_TYPES = {"2": "regular", "4": "playoffs", "5": "play_in"}


def process_games(raw: pd.DataFrame) -> pd.DataFrame:
    """LeagueGameFinder rows (one per team per game) -> games table."""
    games = raw.dropna(subset=["GAME_ID", "TEAM_ID", "PTS"]).copy()
    season_id = games["SEASON_ID"].astype(str)
    games["SEASON_TYPE"] = season_id.str[0].map(SEASON_TYPES)
    games = games.dropna(subset=["SEASON_TYPE"])
    games["SEASON"] = season_id.str[1:].astype(int)
    games = games.drop_duplicates(["GAME_ID", "TEAM_ID"])
    games = games[games.groupby("GAME_ID")["TEAM_ID"].transform("size") == 2]

    games["TEAM"] = games["TEAM_ABBREVIATION"]
    games["LOCATION"] = games["MATCHUP"].str.contains("@").map({True: -1, False: 1})
    dates = pd.to_datetime(games["GAME_DATE"])
    games["DAY"] = (dates - dates.groupby(games["SEASON"]).transform("min")).dt.days
    games["REST"] = (
        dates.sort_values().groupby([games["SEASON"], games["TEAM_ID"]]).diff().dt.days
    )

    opp = games[["GAME_ID", "TEAM_ID", "TEAM", "TEAM_NAME", "REST"] + STATS_COLUMNS]
    opp = opp.rename(columns=lambda c: c if c == "GAME_ID" else f"{c}_OPP")
    games = games.merge(opp, on="GAME_ID")
    games = games[games["TEAM_ID"] != games["TEAM_ID_OPP"]]
    games["PLUS_MINUS"] = games["PTS"] - games["PTS_OPP"]
    return games.sort_values(["SEASON", "DAY", "GAME_ID"]).reset_index(drop=True)


def download(output_file: str = None) -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguegamefinder
    from nba_api.stats.static import teams

    raw = []
    for team in tqdm.tqdm(teams.get_teams()):
        gamefinder = leaguegamefinder.LeagueGameFinder(team_id_nullable=team["id"])
        raw.append(gamefinder.get_data_frames()[0])
        # try not to overload API service
        time.sleep(0.5)
    games = process_games(pd.concat(raw))
    if output_file is not None:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        games.to_csv(output_file, index=False)
    return games
