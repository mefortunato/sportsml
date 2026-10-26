from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from .schema import GameSchema

BUILTIN_SPORTS = ("nfl", "cfb", "nba", "cbb", "wcbb")

_registry: dict[str, Sport] = {}


@dataclass(frozen=True)
class Sport:
    """Everything the CLI and models need to know about one sport.

    Attributes:
        name: CLI name, e.g. ``"nfl"``.
        schema: Column roles of the sport's games table.
        download: Fetches source data and returns a games table.
        gnn: Default GNN sizes (``hidden_dim``, ``out_dim``, ``num_layers``).
    """

    name: str
    schema: GameSchema
    download: Callable[..., pd.DataFrame]
    gnn: dict = field(default_factory=dict)


def register_sport(sport: Sport) -> Sport:
    """Make a sport available to :func:`get_sport` (and so to every model)."""
    _registry[sport.name] = sport
    return sport


def get_sport(name: str) -> Sport:
    if name not in _registry and name in BUILTIN_SPORTS:
        register_sport(importlib.import_module(f"sportsml.{name}").SPORT)
    if name not in _registry:
        known = sorted(set(BUILTIN_SPORTS) | set(_registry))
        raise ValueError(f"unknown sport {name!r}; choose from {known}")
    return _registry[name]


def all_sports() -> dict[str, Sport]:
    """Built-in sports followed by any registered with :func:`register_sport`."""
    names = list(BUILTIN_SPORTS) + [n for n in _registry if n not in BUILTIN_SPORTS]
    return {name: get_sport(name) for name in names}
