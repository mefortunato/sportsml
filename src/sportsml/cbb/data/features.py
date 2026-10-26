from ...core.schema import GameSchema

TEAM_STATS_COLUMNS = [
    "Win",
    "Score",
    "PlusMinus",
    "FGM",
    "FGA",
    "FGM3",
    "FGA3",
    "FTM",
    "FTA",
    "OR",
    "DR",
    "Ast",
    "TO",
    "Stl",
    "Blk",
    "PF",
]

OPP_TEAM_STATS_COLUMNS = [f"{col}_OPP" for col in TEAM_STATS_COLUMNS]

STATS_COLUMNS = TEAM_STATS_COLUMNS + OPP_TEAM_STATS_COLUMNS

SCHEMA = GameSchema(
    season="Season",
    date="DayNum",
    team="TeamID",
    opp="TeamID_OPP",
    game_id="_id",
    target="PlusMinus",
    stats=tuple(STATS_COLUMNS),
    location="Loc",
    team_name="Team",
    opp_name="Team_OPP",
)
