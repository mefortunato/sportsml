from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

SPORT = Sport(
    name="cbb",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 300, "out_dim": 100, "num_layers": 10},
)
