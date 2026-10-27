import torch
import torch_geometric as pyg

from .graph import edge_subgraph, edge_time


class SnapshotDataset(torch.utils.data.Dataset):
    """One sample per (season, date): that season's games up to the date.

    Each sample marks its own targets, so samples can be batched freely:

    * ``on_date``: edges played on the snapshot date (excluded from the
      message-passing context).
    * ``target``: ``on_date`` edges whose teams both have earlier games.

    With ``carry_seasons`` a snapshot also holds that many earlier seasons'
    games, ``edge_time`` gives each edge's age (see
    :func:`~.graph.edge_time`), and a target needs both teams to have any
    game in the snapshot (so season openers are targets too).
    """

    def __init__(
        self,
        graph: pyg.data.Data,
        seasons: list[int],
        carry_seasons: int = 0,
        season_length: float = 1.0,
    ):
        self.carry = carry_seasons
        self.season_length = season_length
        window = [s - k for s in seasons for k in range(carry_seasons + 1)]
        self.graph = edge_subgraph(
            graph, torch.isin(graph.season, torch.tensor(window))
        )
        g = self.graph
        keys = torch.stack([g.season.double(), g.date], dim=1)
        if not carry_seasons:
            self.snapshots = torch.unique(keys[g.valid], dim=0).tolist()
            return
        mine = torch.isin(g.season, torch.tensor(seasons))
        candidates = torch.unique(keys[mine], dim=0).tolist()
        self.snapshots = [k for k in candidates if self._snapshot(*k).target.any()]

    def __len__(self):
        return len(self.snapshots)

    def __getitem__(self, idx: int) -> pyg.data.Data:
        return self._snapshot(*self.snapshots[idx])

    def _snapshot(self, season: float, date: float) -> pyg.data.Data:
        g, season = self.graph, int(season)
        if not self.carry:
            sub = edge_subgraph(g, (g.season == season) & (g.date <= date))
            sub.on_date = sub.date == date
            sub.target = sub.on_date & sub.valid
            return sub
        sub = edge_subgraph(
            g,
            (g.season >= season - self.carry)
            & ((g.season < season) | (g.date <= date)),
        )
        sub.on_date = (sub.season == season) & (sub.date == date)
        seen = torch.zeros(sub.num_nodes, dtype=torch.bool)
        seen[sub.edge_index[:, ~sub.on_date].flatten()] = True
        sub.target = sub.on_date & seen[sub.edge_index[0]] & seen[sub.edge_index[1]]
        sub.edge_time = edge_time(sub, season, date, self.season_length)
        return sub
