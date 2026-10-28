from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

SPORT = Sport(
    name="nba",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 128, "out_dim": 64, "num_layers": 3},
    # about half a season of games; the total as a second output serves the
    # over/under
    transformer={"history": 40, "total_weight": 1.0},
)
