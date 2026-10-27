import torch
from lightning.pytorch.core.mixins import HyperparametersMixin


class MirroredHead(torch.nn.Module, HyperparametersMixin):
    """Predicts from each side's matchup, so swapping the teams flips the
    margin exactly.

    Each side's score comes from its own embedding against the other's:
    ``s(A, B) = f(off_A, def_B)``. With separate offense and defense nodes
    (``off_def``, nodes ``i`` and ``num_teams + i``) ``off`` and ``def`` are
    the team's two embeddings; otherwise both are the team's one embedding.
    Outputs combine the sides by ``kinds``: ``"diff"`` (the margin,
    ``s(T, O) - s(O, T)``), ``"sum"`` (the total) or ``"own"`` (a stat of the
    team's own, ``s(T, O)``). Pre-game context (location, rest, ...) adds a
    separate term per output, so it can carry home field.

    Args:
        in_dim: Node embedding size.
        kinds: How each output combines the two sides (default one "diff").
        hidden_dim: Hidden size of ``f`` (None: linear).
        context_dim: Pre-game context features per edge.
        off_def: Nodes are offense / defense pairs.
    """

    def __init__(
        self,
        in_dim: int,
        kinds: tuple[str, ...] = ("diff",),
        hidden_dim: int | None = None,
        context_dim: int = 0,
        off_def: bool = False,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.hparams["cls"] = self.__class__
        if any(k not in ("diff", "sum", "own") for k in kinds):
            raise ValueError(f"kinds must be 'diff', 'sum' or 'own': {kinds}")
        self.in_dim = in_dim
        self.out_dim = len(kinds)
        self.context_dim = context_dim
        self.off_def = off_def
        self.register_buffer("diff", torch.tensor([k == "diff" for k in kinds]))
        self.register_buffer("own", torch.tensor([k == "own" for k in kinds]))
        if hidden_dim is None:
            self.side = torch.nn.Linear(2 * in_dim, self.out_dim)
        else:
            self.side = torch.nn.Sequential(
                torch.nn.Linear(2 * in_dim, hidden_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(hidden_dim, self.out_dim),
            )
        if context_dim:
            self.context = torch.nn.Linear(context_dim, self.out_dim)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        context: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """``[num_edges, out_dim]`` for edges opponent -> team (team indices;
        with ``off_def`` the defense node of team ``i`` is ``n + i``)."""
        opp, team = edge_index
        n = len(x) // 2 if self.off_def else 0
        off = lambda i: x[i]  # noqa: E731
        dfn = (lambda i: x[n + i]) if self.off_def else off  # noqa: E731
        mine = self.side(torch.cat([off(team), dfn(opp)], dim=-1))
        theirs = self.side(torch.cat([off(opp), dfn(team)], dim=-1))
        out = torch.where(self.diff, mine - theirs, mine + theirs)
        out = torch.where(self.own, mine, out)
        if self.context_dim:
            out = out + self.context(context)
        return out
