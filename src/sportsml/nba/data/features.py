from ...core.schema import GameSchema

STATS_COLUMNS = [
    "PTS",
    "FGM",
    "FGA",
    "FG3M",
    "FG3A",
    "FTM",
    "FTA",
    "OREB",
    "DREB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
]

OPP_STATS_COLUMNS = [f"{col}_OPP" for col in STATS_COLUMNS]

SCHEMA = GameSchema(
    season="SEASON",
    date="DAY",
    team="TEAM",
    opp="TEAM_OPP",
    game_id="GAME_ID",
    target="PLUS_MINUS",
    stats=tuple(STATS_COLUMNS + OPP_STATS_COLUMNS),
    location="LOCATION",
    context=("REST", "REST_OPP"),
    categorical=("SEASON_TYPE",),
    paired=(("REST", "REST_OPP"),),
    team_name="TEAM_NAME",
    opp_name="TEAM_NAME_OPP",
    display=("GAME_DATE",),
)
