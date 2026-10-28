"""Play-by-play tables and the batches a :class:`~.model.PbpModel` trains on.

A game's plays are one sequence (written from the home team's side, see
:mod:`sportsml.nfl.data.plays`); the game encoder turns it into one
embedding per side. A games-table row (one team in one game) points at its
game's sequence and its side. A row's history is the team's previous
``history`` played games, as in the transformer family; each history game's
token is that game's embedding for the team, the opponent's form (the mean
embedding of the opponent's previous ``form_games`` games, so a strong
showing against a strong opponent reads differently from one against a weak
opponent) and the opponent-strength extras (pre-game Elo of both teams, the
opponent's season-to-date margin).

Training batches hold every row of a few consecutive dates of one season, so
the rows' histories share most of their games and each game in the batch is
encoded once.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from ...core.schema import GameSchema
from ..transformer.data import SequenceFeatures, histories, opponent_rows

KEY_COLUMNS = ("game_id", "home_team", "away_team")


class PlayTable:
    """Every game's play features, padded to ``max_plays`` plays.

    Args:
        plays: One row per play in game order, with ``game_id``,
            ``home_team``, ``away_team`` and numeric feature columns.
        max_plays: Longer games keep their first ``max_plays`` plays.
    """

    def __init__(self, plays: pd.DataFrame, max_plays: int = 208):
        columns = [c for c in plays.columns if c not in KEY_COLUMNS]
        self.columns = columns
        self.max_plays = max_plays
        code, game_ids = pd.factorize(plays["game_id"])
        self.game_ids = np.asarray(game_ids)
        self.index = {g: i for i, g in enumerate(self.game_ids)}
        first = plays.groupby(code, sort=True).head(1)
        self.home = first["home_team"].to_numpy()
        self.away = first["away_team"].to_numpy()

        position = plays.groupby(code).cumcount().to_numpy()
        keep = position < max_plays
        values = plays[columns].to_numpy(dtype=np.float32)
        values = np.nan_to_num(values[keep])
        table = np.zeros((len(self.game_ids), max_plays, len(columns)), np.float32)
        table[code[keep], position[keep]] = values
        length = np.bincount(code[keep], minlength=len(self.game_ids))
        self.plays = torch.from_numpy(table)
        self.pad = torch.arange(max_plays)[None, :] >= torch.from_numpy(length)[:, None]

    @classmethod
    def load(cls, path: str, max_plays: int = 208) -> PlayTable:
        return cls(pd.read_parquet(path), max_plays)

    @property
    def play_dim(self) -> int:
        return len(self.columns)

    def sides(self, games: pd.DataFrame, schema: GameSchema) -> np.ndarray:
        """Each row's ``2 * game + side`` (side 0 home, 1 away) in this
        table, -1 where the table lacks the game or its teams differ."""
        game = pd.Series(self.index).reindex(games[schema.game_id]).to_numpy()
        known = ~np.isnan(game)
        game = np.where(known, game, 0).astype(np.int64)
        team = games[schema.team].to_numpy()
        home, away = team == self.home[game], team == self.away[game]
        side = np.where(home, 0, np.where(away, 1, -1))
        return np.where(known & (side >= 0), 2 * game + side, -1)


class PbpData(torch.utils.data.Dataset):
    """Training samples (rows of played games); index it with a list of
    positions (one batch, see :func:`date_batches`) to get a whole batch."""

    def __init__(
        self,
        games: pd.DataFrame,
        schema: GameSchema,
        features: SequenceFeatures,
        plays: PlayTable,
        form_games: int = 4,
        extra_targets: tuple[str, ...] = (),
        rows: np.ndarray | None = None,
    ):
        self.plays = plays
        self.slot = plays.sides(games, schema)
        self.extras = features.tokens(games)
        self.seasons = games[schema.season].to_numpy(dtype=np.float32)
        self.history = histories(games, schema, features.history)
        opp = opponent_rows(games, schema)
        self.opp_history = np.where(
            (opp >= 0)[:, None], self.history[np.maximum(opp, 0)], -1
        )
        self.form = self.opp_history[:, :form_games]
        self.context = features.context(games).astype(np.float32)
        targets = [schema.target, *extra_targets]
        y = games[targets].apply(pd.to_numeric, errors="coerce")
        self.y = y.to_numpy(dtype=np.float32)
        if not extra_targets:
            self.y = self.y[:, 0]
        # the game's own margin and total from each side (auxiliary targets)
        aux = [schema.target] + ([schema.total] if schema.total else [])
        self.aux_y = games[aux].apply(pd.to_numeric, errors="coerce")
        self.aux_y = self.aux_y.to_numpy(dtype=np.float32)
        self.rows = np.arange(len(games)) if rows is None else np.asarray(rows)

    def with_rows(self, rows) -> PbpData:
        other = object.__new__(PbpData)
        other.__dict__ = {**self.__dict__, "rows": np.asarray(rows)}
        return other

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, positions) -> dict:
        rows = self.rows[np.asarray(positions)]
        team, opp = self.history[rows], self.opp_history[rows]
        # the history games' rows (tokens) and the opponents' rows behind
        # each token's form, then the games those rows need encoded
        tokens = np.unique(np.concatenate([team.ravel(), opp.ravel()]))
        tokens = tokens[tokens >= 0]
        form = self.form[tokens]
        needed = np.concatenate([tokens, form[form >= 0]])
        slots = self.slot[needed]
        games = np.unique(slots[slots >= 0] // 2)
        local = np.full(len(self.plays.game_ids), -1, dtype=np.int64)
        local[games] = np.arange(len(games))

        def slot(rows):
            s = np.where(rows >= 0, self.slot[np.maximum(rows, 0)], -1)
            return np.where(s >= 0, 2 * local[s // 2] + s % 2, -1)

        position = np.full(len(self.slot), -1, dtype=np.int64)
        position[tokens] = np.arange(len(tokens))

        def side(history):
            ref = np.where(history >= 0, position[np.maximum(history, 0)], -1)
            ago = self.seasons[rows][:, None] - self.seasons[np.maximum(history, 0)]
            return {
                "ref": torch.from_numpy(ref),
                "seasons_ago": torch.from_numpy(np.where(ref >= 0, ago, 0.0)),
            }

        game_index = torch.from_numpy(games)
        return {
            "games": game_index,
            "plays": self.plays.plays[game_index],
            "play_pad": self.plays.pad[game_index],
            "token_slot": torch.from_numpy(slot(tokens)),
            "token_form": torch.from_numpy(slot(form)),
            "token_extras": torch.from_numpy(self.extras[tokens]),
            "token_aux": torch.from_numpy(self.aux_y[tokens]),
            "team": side(team),
            "opp": side(opp),
            "context": torch.from_numpy(self.context[rows]),
            "y": torch.from_numpy(self.y[rows]),
        }


def date_batches(
    games: pd.DataFrame,
    schema: GameSchema,
    rows: np.ndarray,
    batch_dates: int = 6,
    shuffle: bool = False,
    seed: int | None = None,
) -> list[np.ndarray]:
    """Positions within ``rows`` grouped by season and block of
    ``batch_dates`` consecutive dates (in a random order with ``shuffle``)."""
    frame = games.iloc[rows]
    rank = frame.groupby(schema.season)[schema.date].rank(method="dense")
    block = ((rank.to_numpy() - 1) // batch_dates).astype(np.int64)
    key = pd.MultiIndex.from_arrays([frame[schema.season].to_numpy(), block])
    codes = pd.factorize(key, sort=True)[0]
    batches = [np.flatnonzero(codes == c) for c in range(codes.max() + 1)]
    if shuffle:
        order = np.random.default_rng(seed).permutation(len(batches))
        batches = [batches[i] for i in order]
    return batches


class DateBatches(torch.utils.data.Sampler):
    """:func:`date_batches`, reshuffled every epoch when ``shuffle``."""

    def __init__(self, games, schema, rows, batch_dates, shuffle, seed=0):
        self.args = (games, schema, rows, batch_dates)
        self.shuffle = shuffle
        self.seed = seed
        self.epoch = 0
        self.n = len(date_batches(*self.args))

    def __len__(self):
        return self.n

    def __iter__(self):
        seed = None if self.seed is None else self.seed + self.epoch
        self.epoch += 1
        yield from date_batches(*self.args, shuffle=self.shuffle, seed=seed)
