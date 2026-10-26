from __future__ import annotations

import random
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .snapshot import Snapshot


class SnapshotStore:
    """The live snapshot per sport; refreshes replace entries atomically."""

    def __init__(self, snapshots: dict[str, Snapshot] | None = None, seed=None):
        self.snapshots = dict(snapshots or {})
        self.rng = random.Random(seed)

    def get(self, sport: str) -> Snapshot:
        try:
            return self.snapshots[sport]
        except KeyError:
            raise HTTPException(404, f"unknown sport {sport!r}") from None

    def put(self, sport: str, snapshot: Snapshot) -> None:
        self.snapshots[sport] = snapshot


class Answer(BaseModel):
    pick: Literal["home", "away"]


def create_router(store: SnapshotStore) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/sports")
    def sports() -> list[dict]:
        return [snapshot.info() for snapshot in store.snapshots.values()]

    @router.get("/{sport}")
    def sport_info(sport: str) -> dict:
        return store.get(sport).info()

    @router.get("/{sport}/teams")
    def teams(sport: str) -> list[dict]:
        return list(store.get(sport).teams.values())

    @router.get("/{sport}/upcoming")
    def upcoming(sport: str, season: int | None = None, date: float | None = None):
        return store.get(sport).upcoming(season, date)

    @router.get("/{sport}/games/{game_id}")
    def game(sport: str, game_id: str) -> dict:
        found = store.get(sport).game(game_id)
        if found is None:
            raise HTTPException(404, f"unknown game {game_id!r}")
        return found

    @router.get("/{sport}/performance")
    def performance(sport: str) -> dict:
        found = store.get(sport).performance()
        if found is None:
            raise HTTPException(404, "no backtest for this sport")
        return found

    @router.get("/{sport}/rankings")
    def rankings(sport: str) -> dict:
        return store.get(sport).rankings()

    @router.get("/{sport}/challenge/next")
    def challenge_next(sport: str, exclude: list[str] = Query(default=[])) -> dict:
        try:
            return store.get(sport).challenge_next(store.rng, exclude)
        except LookupError as error:
            raise HTTPException(404, str(error)) from None

    @router.post("/{sport}/challenge/{game_id}")
    def challenge_answer(sport: str, game_id: str, answer: Answer) -> dict:
        snapshot = store.get(sport)
        if not len(snapshot.pool) or game_id not in snapshot.pool.index:
            raise HTTPException(404, f"{game_id!r} is not a challenge game")
        return snapshot.challenge_answer(game_id, answer.pick)

    @router.get("/{path:path}", include_in_schema=False)
    def not_found(path: str):
        raise HTTPException(404, f"no API route /api/{path}")

    return router
