from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

SPORT = Sport(
    name="cfb",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 128, "out_dim": 64, "num_layers": 3},
    transformer={"history": 16, "total_weight": 1.0},
)
