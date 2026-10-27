"""Games table -> each row's team / opponent game-history token sequences.

A token is one earlier game of a team: its box-score stats, result and
location, standardized, plus (optionally) how strong both teams were going
into it and how its margin compared with what Elo expected. A row's history
is the team's previous ``history`` played games, most recent first, crossing
season boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from ...core.schema import GameSchema, played

# Pre-game strength of both teams in each token's game (opponent_strength).
STRENGTH_COLUMNS = ["_team_elo", "_opp_elo", "_opp_margin_avg"]
# The game's margin minus the margin pre-game Elo expected (elo_margin).
ELO_MARGIN_COLUMNS = ["_margin_vs_elo"]


def extra_columns(opponent_strength: bool, elo_margin: bool) -> list[str]:
    return (STRENGTH_COLUMNS if opponent_strength else []) + (
        ELO_MARGIN_COLUMNS if elo_margin else []
    )


def strength(
    games: pd.DataFrame,
    schema: GameSchema,
    opponent_strength: bool = True,
    elo_margin: bool = False,
) -> pd.DataFrame:
    """Each played row's pre-game strength features.

    ``_team_elo`` / ``_opp_elo``: Elo ratings going into the game;
    ``_opp_margin_avg``: the opponent's season-to-date average margin before
    the game; ``_margin_vs_elo``: the game's margin minus Elo's expected
    margin (rating gap plus home edge, in points). Elo and the averages
    depend on earlier games only; ``_margin_vs_elo`` adds the game's own
    result, like the raw margin already in each token.
    """
    import dataclasses

    from ..baselines import EloModel
    from ..sklearn.features import training_frame

    games = played(games, schema)
    out = pd.DataFrame(index=games.index)
    elo = EloModel(schema)
    if opponent_strength:
        ratings = elo.pre_game_ratings(games)
        margin = dataclasses.replace(schema, stats=(schema.target,))
        out["_team_elo"] = ratings["team_elo"]
        out["_opp_elo"] = ratings["opp_elo"]
        out["_opp_margin_avg"] = training_frame(games, margin)[
            f"opp_{schema.target}_avg"
        ]
    if elo_margin:
        expected = elo.replay(games) * elo.params.points_per_elo
        out["_margin_vs_elo"] = games[schema.target] - expected
    return out


@dataclass
class SequenceFeatures:
    """Token / context columns and their standardization; saved with a model."""

    token_columns: list[str]
    context_columns: list[str]
    history: int
    mean: dict[str, float]
    std: dict[str, float]
    schema: GameSchema | None = None
    opponent_strength: bool = False
    elo_margin: bool = False

    @classmethod
    def fit(
        cls,
        train_games: pd.DataFrame,
        schema: GameSchema,
        history: int,
        opponent_strength: bool = False,
        elo_margin: bool = False,
    ) -> SequenceFeatures:
        location = [schema.location] if schema.location else []
        tokens = list(dict.fromkeys([*schema.stats, schema.target, *location]))
        if extra := extra_columns(opponent_strength, elo_margin):
            tokens += extra
            train_games = train_games.join(
                strength(train_games, schema, opponent_strength, elo_margin)
            )
        context = location + list(schema.context)
        columns = list(dict.fromkeys(tokens + context))
        values = train_games[columns].apply(pd.to_numeric, errors="coerce")
        return cls(
            token_columns=tokens,
            context_columns=context,
            history=history,
            mean=values.mean().fillna(0.0).to_dict(),
            std=values.std().replace(0, 1).fillna(1.0).to_dict(),
            schema=schema,
            opponent_strength=opponent_strength,
            elo_margin=elo_margin,
        )

    @property
    def token_dim(self) -> int:
        return len(self.token_columns)

    @property
    def context_dim(self) -> int:
        return len(self.context_columns)

    def _standardize(self, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
        values = frame.reindex(columns=columns).apply(pd.to_numeric, errors="coerce")
        mean = pd.Series(self.mean)[columns]
        std = pd.Series(self.std)[columns]
        z = ((values - mean) / std).fillna(0.0)
        return z.to_numpy(dtype=np.float32).reshape(len(frame), len(columns))

    def tokens(self, games: pd.DataFrame) -> np.ndarray:
        """Standardized tokens for played ``games`` (strength computed from them)."""
        if self.opponent_strength or self.elo_margin:
            games = games.join(
                strength(games, self.schema, self.opponent_strength, self.elo_margin)
            )
        return self._standardize(games, self.token_columns)

    def context(self, matchups: pd.DataFrame) -> np.ndarray:
        return self._standardize(matchups, self.context_columns)


def histories(games: pd.DataFrame, schema: GameSchema, history: int) -> np.ndarray:
    """Positions (``iloc``) of each row's team's previous ``history`` games.

    Shape ``[len(games), history]``, most recent first, -1 where the team has
    fewer earlier games. ``games`` must be played games only.
    """
    team = pd.factorize(games[schema.team])[0]
    order = np.lexsort(
        (games[schema.date].to_numpy(), games[schema.season].to_numpy(), team)
    )
    ordered_team = team[order]
    out = np.full((len(games), history), -1, dtype=np.int64)
    for k in range(1, history + 1):
        previous = np.full(len(games), -1, dtype=np.int64)
        same_team = np.zeros(len(games), dtype=bool)
        previous[k:] = order[:-k]
        same_team[k:] = ordered_team[k:] == ordered_team[:-k]
        out[order, k - 1] = np.where(same_team, previous, -1)
    return out


def opponent_rows(games: pd.DataFrame, schema: GameSchema) -> np.ndarray:
    """``iloc`` of the opponent's row of the same game (-1 if absent)."""
    position = pd.Series(
        np.arange(len(games)),
        index=pd.MultiIndex.from_frame(games[[schema.game_id, schema.team]]),
    )
    opp = pd.MultiIndex.from_frame(games[[schema.game_id, schema.opp]])
    return position.reindex(opp).fillna(-1).astype(np.int64).to_numpy()


def sequence(tokens, seasons, index, season) -> dict[str, torch.Tensor]:
    """Gather token sequences; ``index`` -1 entries are padding.

    Args:
        tokens: ``[N, F]`` token table; seasons: ``[N]`` their seasons.
        index: ``[B, K]`` rows of ``tokens`` per sequence.
        season: ``[B]`` season being predicted (for ``seasons_ago``).
    """
    pad = index < 0
    safe = index.clamp(min=0)
    seasons_ago = (season[:, None] - seasons[safe]).masked_fill(pad, 0)
    return {
        "tokens": tokens[safe].masked_fill(pad[..., None], 0.0),
        "seasons_ago": seasons_ago.float(),
        "pad": pad,
    }


class SequenceData(torch.utils.data.Dataset):
    """Training samples (rows of played games) as batches of sequences.

    Index it with a list of sample positions (e.g. via a ``BatchSampler``)
    to get a whole batch.
    """

    def __init__(
        self,
        games: pd.DataFrame,
        schema: GameSchema,
        features: SequenceFeatures,
        rows: np.ndarray | None = None,
    ):
        self.tokens = torch.from_numpy(features.tokens(games))
        self.seasons = torch.tensor(games[schema.season].to_numpy(dtype=np.float32))
        self.history = torch.from_numpy(histories(games, schema, features.history))
        opp = torch.from_numpy(opponent_rows(games, schema))
        self.opp_history = torch.where(
            (opp >= 0)[:, None], self.history[opp.clamp(min=0)], -1
        )
        self.context = torch.from_numpy(features.context(games))
        self.y = torch.tensor(games[schema.target].to_numpy(dtype=np.float32))
        self.rows = torch.arange(len(games)) if rows is None else torch.as_tensor(rows)

    def with_rows(self, rows) -> SequenceData:
        other = object.__new__(SequenceData)
        other.__dict__ = {**self.__dict__, "rows": torch.as_tensor(rows)}
        return other

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, positions) -> dict:
        rows = self.rows[torch.as_tensor(positions)]
        season = self.seasons[rows]
        return {
            "team": sequence(self.tokens, self.seasons, self.history[rows], season),
            "opp": sequence(self.tokens, self.seasons, self.opp_history[rows], season),
            "context": self.context[rows],
            "y": self.y[rows],
        }
