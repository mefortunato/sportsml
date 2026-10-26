from ...core.schema import GameSchema

STATS_COLUMNS = [
    "points",
    "rushingTDs",
    "passingTDs",
    "kickReturnYards",
    "kickReturnTDs",
    "kickReturns",
    "kickingPoints",
    "interceptionYards",
    "interceptionTDs",
    "passesIntercepted",
    "fumblesRecovered",
    "totalFumbles",
    "possessionTime",
    "interceptions",
    "fumblesLost",
    "turnovers",
    "yardsPerRushAttempt",
    "rushingAttempts",
    "rushingYards",
    "yardsPerPass",
    "netPassingYards",
    "totalYards",
    "firstDowns",
    "totalPenalties",
    "totalPenaltiesYards",
    "passingCompletions",
    "passingAttempts",
    "fourthDownAtt",
    "fourthDownConv",
    "thirdDownAtt",
    "thirdDownConv",
]

OPP_STATS_COLUMNS = [f"opp_{col}" for col in STATS_COLUMNS]

SCHEMA = GameSchema(
    season="season",
    # chronological week of the season; bowls come after the last regular week
    date="week",
    team="team",
    opp="opp_team",
    game_id="game_id",
    target="result",
    stats=tuple(STATS_COLUMNS + OPP_STATS_COLUMNS),
    location="location",
    categorical=("conference", "opp_conference"),
    paired=(("conference", "opp_conference"),),
)
