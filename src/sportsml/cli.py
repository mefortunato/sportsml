"""``sportsml <sport> {download,process,fit,predict}`` built from the registry.

Every registered sport gets the same subcommands; per-sport defaults (paths,
GNN sizes) come from its :class:`~sportsml.core.sport.Sport` entry.
"""

import jsonargparse
import jsonargparse.typing
import pandas as pd

from . import __version__
from .core.process import process
from .core.sport import Sport, all_sports
from .inference.utils import predict
from .models.gnn.fit import fit_gnn, gnn_config
from .models.sklearn.fit import fit_sklearn

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


def gnn_trainer_config(sport: Sport) -> dict:
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
        f"{n}.fit.gnn.trainer": gnn_trainer_config(sport),
        f"{n}.fit.gnn.save_dir": f"models/{n}/gnn",
        f"{n}.predict.model_dir": f"models/{n}/sklearn",
        f"{n}.predict.games": games,
        f"{n}.predict.output_file": f"predictions/{n}.csv",
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
            "fit": {"sklearn": fit_sklearn, "gnn": fit_gnn},
            "predict": predict,
        }
        for name, sport in sports.items()
    }
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
