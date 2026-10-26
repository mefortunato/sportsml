from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .api import SnapshotStore, create_router
from .refresh import refresh_forever
from .snapshot import Snapshot

logger = logging.getLogger(__name__)


class SinglePageApp(StaticFiles):
    """Static files with a fallback to ``index.html`` for client-side routes."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def load_store(data_dir: str | pathlib.Path) -> SnapshotStore:
    """One snapshot per sport subdirectory of ``data_dir``."""
    store = SnapshotStore()
    for path in sorted(pathlib.Path(data_dir).iterdir()):
        if (path / "meta.json").exists():
            snapshot = Snapshot.load(path)
            store.put(snapshot.view.sport, snapshot)
            logger.info("loaded %s from %s", snapshot.view.sport, path)
    return store


def create_app(
    data_dir: str | pathlib.Path | None = None,
    static_dir: str | pathlib.Path | None = None,
    refresh: bool | None = None,
    refresh_hours: float | None = None,
    store: SnapshotStore | None = None,
) -> FastAPI:
    """The API under ``/api`` and the frontend build at ``/``.

    Args:
        data_dir: Output of ``sportsml web build`` (or pass ``store``).
        static_dir: SvelteKit build directory; omitted -> API only.
        refresh: Re-download data on startup and every ``refresh_hours``
            (defaults: env ``SPORTSML_REFRESH`` != "0", and
            ``SPORTSML_REFRESH_HOURS`` or 6).
    """
    if refresh is None:
        refresh = os.getenv("SPORTSML_REFRESH", "1") != "0"
    if refresh_hours is None:
        refresh_hours = float(os.getenv("SPORTSML_REFRESH_HOURS", "6"))
    store = store or load_store(data_dir)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if refresh:
            task = asyncio.create_task(refresh_forever(store, refresh_hours))
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="SportsML", lifespan=lifespan)
    app.state.store = store
    app.include_router(create_router(store))
    if static_dir is not None and pathlib.Path(static_dir).is_dir():
        app.mount("/", SinglePageApp(directory=static_dir, html=True), name="site")
    return app
