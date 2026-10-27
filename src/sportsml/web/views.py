"""How each sport is presented in the web app.

A :class:`SportView` is the web-side counterpart of
:class:`sportsml.core.sport.Sport`: which stats to show, what a "date" is
called, and where team names, colors and logos come from. Adding a sport to
the app means registering one view; the export and frontend are generic.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

# How a team's season ended, for the last rounds of the playoffs.
PLAYOFF_STAGES = ("champion", "runner_up", "semifinal")

# Team metadata columns every view's ``load_teams`` returns.
TEAM_COLUMNS = (
    "team", "name", "nickname", "color", "color2", "logo", "conference", "division",
)  # fmt: skip


@dataclass(frozen=True)
class Stat:
    """A per-game stat shown in team comparisons.

    Attributes:
        key: Identifier in the exported data.
        label: Display label.
        value: Per-row value from the team's perspective (games table rows).
        decimals: Digits shown.
        higher_is_better: Which side of a comparison is highlighted.
    """

    key: str
    label: str
    value: Callable[[pd.DataFrame], pd.Series]
    decimals: int = 1
    higher_is_better: bool = True


def column(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda rows: rows[name]


def total(*names: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda rows: rows[list(names)].sum(axis=1, min_count=1)


@dataclass(frozen=True)
class SportView:
    """Presentation of one sport.

    Attributes:
        sport: Name in the sport registry (``core.sport``).
        label: Display name, e.g. ``"NFL"``.
        date_label: What the schema's date column is called, e.g. ``"Week"``.
        stats: Stats compared on game and challenge pages.
        load_teams: Returns team metadata with :data:`TEAM_COLUMNS`.
        score: ``(team, opponent)`` points columns of the games table.
        kickoff: Kickoff time of a games-table row, for display.
        recent_games: How many recent games to show per team.
        playoffs: Played games -> ``{season: {team: stage}}`` for the teams
            that reached the last rounds (stages from
            :data:`PLAYOFF_STAGES`); ``None`` if the sport has no playoffs.
        playoff_labels: Display label per stage.
    """

    sport: str
    label: str
    date_label: str
    stats: tuple[Stat, ...]
    load_teams: Callable[[], pd.DataFrame]
    score: tuple[str, str]
    kickoff: Callable[[pd.Series], str | None] = lambda row: None
    recent_games: int = 5
    playoffs: Callable[[pd.DataFrame], dict[int, dict[str, str]]] | None = None
    playoff_labels: dict[str, str] = field(default_factory=dict)


BUILTIN_VIEWS = ("nfl", "cfb")
_views: dict[str, SportView] = {}


def register_view(view: SportView) -> SportView:
    _views[view.sport] = view
    return view


def get_view(sport: str) -> SportView:
    if sport not in _views and sport in BUILTIN_VIEWS:
        register_view(importlib.import_module(f"sportsml.web.sports.{sport}").VIEW)
    if sport not in _views:
        raise KeyError(f"no web view for sport {sport!r}")
    return _views[sport]
