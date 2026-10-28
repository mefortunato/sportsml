from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA
from .data.plays import download_plays

SPORT = Sport(
    name="nfl",
    schema=SCHEMA,
    download=download,
    # tuned on 2025 validation: early stopping otherwise hits at epoch 1
    gnn={
        "hidden_dim": 128,
        "out_dim": 64,
        "num_layers": 3,
        "dropout": 0.2,
        "lr": 3e-4,
        "weight_decay": 1e-4,
    },
    # about one season of games, so openers still see a full season; the
    # total as a second output serves the over/under and left the margin's
    # backtest Brier unchanged (+0.0001 +/- 0.0026 on 2021-2025), while adding
    # every box-score stat made it worse (+0.0018 +/- 0.0030)
    transformer={"history": 20, "total_weight": 1.0},
    pbp={"history": 20, "total_weight": 1.0},
    plays=download_plays,
)
