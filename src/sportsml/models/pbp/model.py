from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from lightning.pytorch.core.mixins import HyperparametersMixin
from torch import nn

from ...core.predictor import MatchupModel
from ...core.schema import GameSchema, played
from ..lightning import MarginModule
from ..transformer.data import SequenceFeatures, histories, opponent_rows, sequence
from ..transformer.model import PairHead, SequenceEncoder
from .data import PlayTable


class PlayEncoder(nn.Module, HyperparametersMixin):
    """Transformer over one game's plays -> an embedding of each side's game.

    Each token is one play (written from the home side) plus a learned
    position embedding of its place in the game. Two learned [CLS] tokens
    lead the sequence; their final states are the home and the away team's
    game embeddings.

    Args:
        play_dim: Features per play.
        max_plays: Longest play sequence.
        d_model / nhead / num_layers / dropout: Transformer sizes. Dropout
            is off by default: on CPU, dropout over every play's attention
            weights made training ~10x slower.
    """

    def __init__(
        self,
        play_dim: int,
        max_plays: int = 208,
        d_model: int = 32,
        nhead: int = 4,
        num_layers: int = 2,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.hparams["cls"] = self.__class__
        self.play_dim = play_dim
        self.out_dim = d_model
        self.embed = nn.Linear(play_dim, d_model)
        self.position = nn.Embedding(max_plays, d_model)
        self.cls_tokens = nn.Parameter(torch.randn(1, 2, d_model) * 0.02)
        layer = nn.TransformerEncoderLayer(
            d_model,
            nhead,
            dim_feedforward=4 * d_model,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, num_layers, enable_nested_tensor=False
        )
        self.norm = nn.LayerNorm(d_model)

    def forward(self, plays, pad) -> torch.Tensor:
        """
        Args:
            plays: ``[G, P, play_dim]``; pad: ``[G, P]`` bool, True past the
                game's last play.
        Returns:
            ``[G, 2, d_model]``: the home side's, then the away side's.
        """
        games, length, _ = plays.shape
        x = self.embed(plays) + self.position(torch.arange(length, device=plays.device))
        x = torch.cat([self.cls_tokens.expand(games, -1, -1), x], dim=1)
        pad = torch.cat([pad.new_zeros(games, 2), pad], dim=1)
        return self.norm(self.encoder(x, src_key_padding_mask=pad)[:, :2])


def gather(table: torch.Tensor, index: torch.Tensor) -> torch.Tensor:
    """``table[index]`` with zeros where ``index`` is -1."""
    padded = torch.cat([table.new_zeros(1, table.shape[-1]), table])
    return padded[index + 1]


def history_tokens(embedding, form, extras) -> torch.Tensor:
    """A history game's token: its embedding for the team, the mean of the
    opponent's ``form`` embeddings (``[..., form_games, d]``, zero rows
    where the opponent had no earlier game) and the extra features."""
    known = (form.abs().sum(-1, keepdim=True) > 0).float()
    mean = (form * known).sum(-2) / known.sum(-2).clamp(min=1)
    return torch.cat([embedding, mean, extras], dim=-1)


class PbpModel(MarginModule):
    """Play-by-play transformer -> game embeddings; a :class:`SequenceEncoder`
    over each team's recent game tokens -> team embeddings; a
    :class:`PairHead` on both teams' embeddings -> margin (and total).

    The play encoder trains end to end through the team encoder, plus an
    auxiliary loss (``aux_weight``): each history game's embedding regresses
    that game's own margin and total, which gives the play encoder a direct
    signal from every game it encodes.
    """

    SUBMODULES = ("game_encoder", "team_encoder", "head")

    def __init__(
        self,
        game_encoder: PlayEncoder,
        team_encoder: SequenceEncoder,
        head: PairHead,
        lr: float = 3e-4,
        weight_decay: float = 1e-4,
        target_mean: float | list[float] = 0.0,
        target_std: float | list[float] = 1.0,
        extra_targets: tuple[str, ...] = (),
        extra_weights: tuple[float, ...] = (),
        aux_weight: float = 0.5,
        aux_dim: int = 2,
        aux_mean: list[float] | None = None,
        aux_std: list[float] | None = None,
    ):
        super().__init__(
            lr, weight_decay, target_mean, target_std, extra_targets, extra_weights
        )
        self.game_encoder = game_encoder
        self.team_encoder = team_encoder
        self.head = head
        self.aux_weight = aux_weight
        self.aux_head = nn.Linear(game_encoder.out_dim, aux_dim)
        self.register_buffer(
            "aux_mean", torch.as_tensor(aux_mean or [0.0] * aux_dim).float()
        )
        self.register_buffer(
            "aux_std", torch.as_tensor(aux_std or [1.0] * aux_dim).float()
        )
        self._aux = None
        self.save_hyperparameters(ignore=list(self.SUBMODULES))
        self.save_submodules()

    def set_aux_scaling(self, mean, std) -> None:
        self.aux_mean.copy_(torch.as_tensor(np.asarray(mean, dtype=np.float32)))
        self.aux_std.copy_(torch.as_tensor(np.asarray(std, dtype=np.float32)))
        self.hparams.update({"aux_mean": list(map(float, mean))})
        self.hparams.update({"aux_std": list(map(float, std))})

    def configure_optimizers(self):
        return torch.optim.AdamW(
            self.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )

    def embed_games(self, plays, pad) -> torch.Tensor:
        """``[2 * G, d]`` game embeddings, row ``2 * game + side``."""
        return self.game_encoder(plays, pad).flatten(0, 1)

    def tokens(self, batch) -> torch.Tensor:
        """The batch's history-game tokens, from its plays."""
        games = self.embed_games(batch["plays"], batch["play_pad"])
        own = gather(games, batch["token_slot"])
        self._aux = (self.aux_head(own), batch["token_aux"], batch["token_slot"] >= 0)
        return history_tokens(
            own, gather(games, batch["token_form"]), batch["token_extras"]
        )

    def forward(self, batch) -> torch.Tensor:
        if "plays" in batch:
            tokens = self.tokens(batch)
            sides = {
                key: {
                    "tokens": gather(tokens, batch[key]["ref"]),
                    "seasons_ago": batch[key]["seasons_ago"],
                    "pad": batch[key]["ref"] < 0,
                }
                for key in ("team", "opp")
            }
        else:  # serving: tokens already gathered
            sides = {key: batch[key] for key in ("team", "opp")}
        team = self.team_encoder(**sides["team"])
        opp = self.team_encoder(**sides["opp"])
        return self.head(team, opp, batch["context"])

    def targets(self, batch) -> torch.Tensor:
        return batch["y"]

    def _step(self, batch, stage: str):
        self._aux = None
        loss = super()._step(batch, stage)
        if self.aux_weight and self._aux is not None:
            pred, y, has_plays = self._aux
            z = (y - self.aux_mean) / self.aux_std
            known = ~torch.isnan(z) & has_plays[:, None]
            error = (pred - torch.nan_to_num(z)) ** 2 * known
            aux = error.sum() / known.sum().clamp(min=1)
            self.log(f"{stage}_aux_loss", aux, on_epoch=True, batch_size=len(y))
            loss = loss + self.aux_weight * aux
        return loss


class PbpMatchupModel(MatchupModel):
    """Serves a :class:`PbpModel` from each team's latest games.

    Game embeddings are computed once per game (from the play table) and
    cached by game id, so a state refresh only encodes games it has not
    seen. The play table is reloaded from ``plays_path`` when a refresh
    brings games the table in memory lacks (and is not saved with the
    model). A played game without plays gets a zero embedding.
    """

    def __init__(
        self,
        schema: GameSchema,
        module: PbpModel,
        features: SequenceFeatures,
        form_games: int,
        plays: PlayTable | None = None,
        plays_path: str | None = None,
    ):
        self.schema = schema
        self.module = module.cpu().eval()
        self.features = features
        self.form_games = form_games
        self.plays_path = plays_path
        self.max_plays = plays.max_plays if plays is not None else 208
        self._plays = plays
        # games the current play table was found to lack
        self._absent: set = set()
        self.embeddings: dict = {}
        self.team_index: dict = {}
        self.state_season = None

    def __getstate__(self):
        return {**self.__dict__, "_plays": None, "_absent": set()}

    def _table(self, missing) -> PlayTable | None:
        table = self._plays
        absent = table is None or any(g not in table.index for g in missing)
        if absent and self.plays_path:
            table = self._plays = PlayTable.load(self.plays_path, self.max_plays)
        return table

    @torch.no_grad()
    def _embed(self, game_ids) -> None:
        missing = [
            g
            for g in pd.unique(game_ids)
            if g not in self.embeddings and g not in self._absent
        ]
        table = self._table(missing) if missing else None
        if table is None:
            return
        self._absent |= {g for g in missing if g not in table.index}
        index = [table.index[g] for g in missing if g in table.index]
        for start in range(0, len(index), 256):
            chunk = torch.as_tensor(index[start : start + 256])
            out = self.module.game_encoder(table.plays[chunk], table.pad[chunk])
            for i, emb in zip(chunk.tolist(), out.numpy()):
                g = table.game_ids[i]
                self.embeddings[g] = (emb, table.home[i], table.away[i])

    def game_embeddings(self, games: pd.DataFrame) -> np.ndarray:
        """``[len(games), d]`` each row's game embedding (zeros if unknown)."""
        s = self.schema
        self._embed(games[s.game_id])
        out = np.zeros((len(games), self.module.game_encoder.out_dim), np.float32)
        for i, (game, team) in enumerate(zip(games[s.game_id], games[s.team])):
            if game in self.embeddings:
                emb, home, away = self.embeddings[game]
                if team == home:
                    out[i] = emb[0]
                elif team == away:
                    out[i] = emb[1]
        return out

    def update_state(self, games: pd.DataFrame) -> None:
        s = self.schema
        games = played(games, s).sort_values([s.season, s.date], kind="stable")
        games = games.reset_index(drop=True)
        self.state_season = games[s.season].max()
        embedding = torch.from_numpy(self.game_embeddings(games))
        hist = histories(games, s, self.form_games)
        opp = opponent_rows(games, s)
        form = np.where((opp >= 0)[:, None], hist[np.maximum(opp, 0)], -1)
        extras = torch.from_numpy(self.features.tokens(games))
        with torch.no_grad():
            self.tokens = history_tokens(
                embedding, gather(embedding, torch.from_numpy(form)), extras
            )
        self.seasons = torch.from_numpy(games[s.season].to_numpy(dtype=np.float32))
        # teams of this season or the last (one waiting for its first game
        # of the season keeps its state)
        current = set(games.loc[games[s.season] >= self.state_season - 1, s.team])
        k = self.module.team_encoder.history
        index = []
        teams = [t for t in pd.unique(games[s.team]) if t in current]
        for team in teams:
            rows = np.flatnonzero(games[s.team].to_numpy() == team)[::-1][:k]
            index.append(np.pad(rows, (0, k - len(rows)), constant_values=-1))
        self.team_index = {team: i for i, team in enumerate(teams)}
        self.history = torch.from_numpy(np.array(index, dtype=np.int64).reshape(-1, k))

    @property
    def teams(self) -> list:
        return list(self.team_index)

    def predict_margin(self, matchups: pd.DataFrame) -> np.ndarray:
        return self.predict_outputs(matchups)["margin"]

    @torch.no_grad()
    def predict_outputs(self, matchups: pd.DataFrame) -> dict[str, np.ndarray]:
        s = self.schema
        season = (
            matchups[s.season].to_numpy(dtype=np.float32)
            if s.season in matchups
            else np.full(len(matchups), self.state_season, dtype=np.float32)
        )
        season = torch.from_numpy(season)

        def side(keys):
            index = self.history[[self.team_index[k] for k in keys]]
            return sequence(self.tokens, self.seasons, index, season)

        batch = {
            "team": side(matchups[s.team]),
            "opp": side(matchups[s.opp]),
            "context": torch.from_numpy(self.features.context(matchups)),
        }
        out = self.module.predict_outputs(batch).numpy()
        extra = self.module.extra_targets
        result = {"margin": out[:, 0]}
        if s.total and s.total in extra:
            result["total"] = out[:, 1 + extra.index(s.total)]
        return result
