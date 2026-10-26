from ..core.sport import Sport
from .data.download import download
from .data.features import SCHEMA

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
)
