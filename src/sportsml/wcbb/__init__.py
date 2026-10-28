from ..cbb.data.features import SCHEMA
from ..core.sport import Sport
from .data.download import download

SPORT = Sport(
    name="wcbb",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 128, "out_dim": 64, "num_layers": 3},
    # as men's college basketball
    transformer={"history": 32, "total_weight": 1.0, "opponent_strength": True},
)
