from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

SPORT = Sport(
    name="nba",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 128, "out_dim": 64, "num_layers": 3},
    transformer={"history": 40},
)
