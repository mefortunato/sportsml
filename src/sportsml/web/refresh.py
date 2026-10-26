"""Keep served data current: re-download results and rebuild snapshots.

Refreshing re-runs the sport's download and ``process`` steps and rebuilds
the snapshot with the saved model (team state is refreshed, nothing is
retrained). A failed refresh keeps the snapshot already being served.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import pandas as pd

from ..core.process import process
from ..core.sport import get_sport
from .api import SnapshotStore

logger = logging.getLogger(__name__)


def download_games(sport: str) -> pd.DataFrame:
    return process(sport, get_sport(sport).download())


def refresh_sport(
    store: SnapshotStore,
    sport: str,
    download: Callable[[str], pd.DataFrame] = download_games,
) -> bool:
    """Rebuild ``sport``'s snapshot from fresh data; False (and keep the
    current one) on any error."""
    try:
        games = download(sport)
        store.put(sport, store.get(sport).refreshed(games))
    except Exception:
        logger.exception("refreshing %s failed; still serving previous data", sport)
        return False
    logger.info("refreshed %s", sport)
    return True


async def refresh_forever(
    store: SnapshotStore,
    every_hours: float,
    download: Callable[[str], pd.DataFrame] = download_games,
) -> None:
    """Refresh every sport now, then every ``every_hours`` hours."""
    while True:
        for sport in list(store.snapshots):
            await asyncio.to_thread(refresh_sport, store, sport, download)
        await asyncio.sleep(every_hours * 3600)
