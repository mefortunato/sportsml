"""``sportsml <sport> {download,process,fit,predict,backtest,benchmark}``.

Every registered sport gets the same subcommands; per-sport defaults (paths,
GNN sizes) come from its :class:`~sportsml.core.sport.Sport` entry.
"""

import jsonargparse
import jsonargparse.typing
import pandas as pd

from . import __version__
from .backtest import backtest, benchmark
from .core.process import process
from .core.sport import Sport, all_sports
from .inference.utils import predict
from .models.gnn.fit import fit_gnn, gnn_config
from .models.sklearn.fit import fit_sklearn
from .models.transformer.fit import fit_transformer, transformer_config
from .web.build import build as web_build
from .web.build import serve as web_serve
from .web.export import export as web_export

# Table arguments (``str | pd.DataFrame``) stay CSV paths on the command line
# and are read by the command itself. Without this, jsonargparse would read an
# existing file's text into the argument while trying the DataFrame branch.
jsonargparse.typing.register_type(
    pd.DataFrame,
    serializer=lambda v: v if isinstance(v, str) else "<DataFrame>",
    deserializer=lambda v: v,
)

SKLEARN_MODEL = {
    "class_path": "sklearn.ensemble.RandomForestRegressor",
    "init_args": {
        "n_estimators": 300,
        "min_samples_leaf": 5,
        "max_features": 0.3,
        "n_jobs": -1,
        "random_state": 0,
    },
}


def version():
    """Print the version of the sportsml package."""
    print(__version__)


ENCODER = "sportsml.models.gnn.nn.encoder.edge_conv_encoder.EdgeConvEncoder"


def gnn_model_config(sport: Sport) -> dict:
    config = gnn_config(sport.name)
    config["encoder"] = {"class_path": ENCODER, "init_args": config["encoder"]}
    return config


def trainer_config(sport: Sport) -> dict:
    callbacks = "lightning.pytorch.callbacks"
    return {
        "max_epochs": 100,
        "accelerator": "auto",
        "devices": 1,
        "logger": {
            "class_path": "lightning.pytorch.loggers.MLFlowLogger",
            "init_args": {
                "experiment_name": sport.name,
                "tracking_uri": "sqlite:///mlflow.db",
            },
        },
        "callbacks": [
            {
                "class_path": f"{callbacks}.EarlyStopping",
                "init_args": {"monitor": "val_loss", "patience": 10, "mode": "min"},
            },
            {
                "class_path": f"{callbacks}.ModelCheckpoint",
                "init_args": {"monitor": "val_loss", "mode": "min"},
            },
        ],
    }


def sport_defaults(sport: Sport) -> dict:
    n = sport.name
    raw, games = f"data/{n}/raw.csv", f"data/{n}/games.csv"
    return {
        f"{n}.download.output_file": raw,
        f"{n}.process.sport": n,
        f"{n}.process.games": raw,
        f"{n}.process.output_file": games,
        f"{n}.fit.sklearn.sport": n,
        f"{n}.fit.sklearn.games": games,
        f"{n}.fit.sklearn.model": SKLEARN_MODEL,
        f"{n}.fit.sklearn.save_dir": f"models/{n}/sklearn",
        f"{n}.fit.gnn.sport": n,
        f"{n}.fit.gnn.games": games,
        f"{n}.fit.gnn.model": gnn_model_config(sport),
        f"{n}.fit.gnn.trainer": trainer_config(sport),
        f"{n}.fit.gnn.save_dir": f"models/{n}/gnn",
        f"{n}.fit.transformer.sport": n,
        f"{n}.fit.transformer.games": games,
        f"{n}.fit.transformer.model": transformer_config(n),
        f"{n}.fit.transformer.trainer": trainer_config(sport),
        f"{n}.fit.transformer.save_dir": f"models/{n}/transformer",
        f"{n}.predict.model_dir": f"models/{n}/sklearn",
        f"{n}.predict.games": games,
        f"{n}.predict.output_file": f"predictions/{n}.csv",
        f"{n}.backtest.sport": n,
        f"{n}.backtest.games": games,
        f"{n}.backtest.output_dir": f"backtests/{n}",
        f"{n}.benchmark.sport": n,
        f"{n}.benchmark.games": games,
        f"{n}.benchmark.output_dir": f"backtests/{n}",
    }


def cli(args=None) -> None:
    """Console entry point (its return value would become the exit status)."""
    run(args)


def run(args=None):
    """Parse ``args`` and run the command; returns the command's result."""
    sports = all_sports()
    components = {
        name: {
            "download": sport.download,
            "process": process,
            "fit": {
                "sklearn": fit_sklearn,
                "gnn": fit_gnn,
                "transformer": fit_transformer,
            },
            "predict": predict,
            "backtest": backtest,
            "benchmark": benchmark,
        }
        for name, sport in sports.items()
    }
    components["web"] = {"build": web_build, "serve": web_serve, "export": web_export}
    components["version"] = version
    defaults = {}
    for sport in sports.values():
        defaults |= sport_defaults(sport)
    return jsonargparse.auto_cli(
        components,
        args=args,
        as_positional=False,
        set_defaults=defaults,
        parser_mode="omegaconf+",
    )


if __name__ == "__main__":
    cli()
