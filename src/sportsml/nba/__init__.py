from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

SPORT = Sport(
    name="nba",
    schema=SCHEMA,
    download=download,
    gnn={"hidden_dim": 128, "out_dim": 64, "num_layers": 3},
    # about half a season of games; the total as a second output serves the
    # over/under. On 2024-2026 walk-forward backtests (Brier, paired 95% CI)
    # history 20 was no better (+0.0009 +/- 0.0016) and opponent strength
    # changed nothing (-0.0007 +/- 0.0014)
    transformer={"history": 40, "total_weight": 1.0},
)
