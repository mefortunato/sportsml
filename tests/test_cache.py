import json
import pathlib
import subprocess

import pandas as pd
import pytest

from sportsml.web.build import build, code_hash, push_cache
from sportsml.web.cache import DirectoryStore, ReleaseStore, open_store

from .conftest import make_games

GAMES = make_games(seasons=(2020, 2021, 2022, 2023, 2024))


@pytest.fixture
def spies(monkeypatch):
    """Records the seasons each build backtests and how often it trains."""
    import sportsml.backtest
    import sportsml.models.transformer

    calls = {"backtest": [], "fit": 0}
    backtest, fit = (
        sportsml.backtest.backtest,
        sportsml.models.transformer.fit_transformer,
    )

    def spy_backtest(*args, seasons=None, **kwargs):
        calls["backtest"].append(list(seasons))
        return backtest(*args, seasons=seasons, **kwargs)

    def spy_fit(*args, **kwargs):
        # the model for upcoming games (backtest seasons fit their own)
        calls["fit"] += str(kwargs.get("save_dir", "")).endswith("model")
        return fit(*args, **kwargs)

    monkeypatch.setattr(sportsml.backtest, "backtest", spy_backtest)
    monkeypatch.setattr(sportsml.models.transformer, "fit_transformer", spy_fit)
    return calls


def run(output_dir, **kwargs):
    build(sports=["toy"], output_dir=str(output_dir), games=GAMES,
          backtest_seasons=2, max_epochs=1, **kwargs)  # fmt: skip
    return pd.read_csv(pathlib.Path(output_dir) / "toy" / "pool.csv")


def test_machines_share_backtest_seasons_and_models(tmp_path, spies):
    cache = str(tmp_path / "cache")
    pool = run(tmp_path / "gpu_box", cache=cache)
    assert spies["backtest"] == [[2022, 2023]] and spies["fit"] == 1
    names = DirectoryStore(cache).names()
    assert sum(n.startswith("toy-2022-") for n in names) == 2  # pool, rankings
    assert sum(n.startswith("toy-model-") for n in names) == 1

    # another machine, nothing of its own: the seasons come from the cache
    spies["backtest"].clear()
    pool2 = run(tmp_path / "workflow", cache=cache, reuse_model_days=30)
    assert spies["backtest"] == [] and spies["fit"] == 1  # nor is it trained
    pd.testing.assert_frame_equal(pool2, pool)
    meta = json.loads((tmp_path / "workflow" / "toy" / "meta.json").read_text())
    assert (
        meta["model"]["metrics"] and (tmp_path / "workflow" / "toy" / "model").is_dir()
    )

    # without reuse_model_days the model is trained; refresh_backtest redoes
    # every season and replaces the cache's entries
    run(tmp_path / "workflow", cache=cache, refresh_backtest=True)
    assert spies["backtest"] == [[2022, 2023]] and spies["fit"] == 2


def test_an_old_model_is_not_reused(tmp_path, spies):
    cache = str(tmp_path / "cache")
    run(tmp_path / "a", cache=cache)
    store = DirectoryStore(cache)
    name = next(n for n in store.names() if n.startswith("toy-model-"))
    target = tmp_path / "unpacked"
    key = name.removeprefix("toy-model-").removesuffix(".tar.gz")
    assert store.get_model("toy", key, target, max_age_days=1)["trained_at"]
    assert store.get_model("toy", key, target, max_age_days=0) is None


def test_push_cache_seeds_the_store_from_a_build(tmp_path, spies):
    run(tmp_path / "webdata")
    cache = str(tmp_path / "cache")
    push_cache(cache, data_dir=str(tmp_path / "webdata"))
    spies["backtest"].clear()
    run(tmp_path / "elsewhere", cache=cache)
    assert spies["backtest"] == []


def test_code_hash_of_a_sport_leaves_out_the_other_sports():
    assert code_hash("nfl") == code_hash("nfl")
    assert code_hash("nfl") != code_hash("nhl") != code_hash()


class FakeGh:
    """``gh`` with a release that does not exist until it is created."""

    def __init__(self):
        self.assets, self.created, self.calls = {}, False, []

    def __call__(self, args, check=True, **kwargs):
        self.calls.append(args)
        command = args[1:3]
        out, code = b"", 0
        if command == ["release", "view"]:
            code = 0 if self.created else 1
            out = json.dumps({"assets": [{"name": n} for n in self.assets]}).encode()
        elif command == ["release", "create"]:
            self.created = True
        elif command == ["release", "upload"]:
            path = pathlib.Path(args[4])
            self.assets[path.name] = path.read_bytes()
        elif command == ["release", "download"]:
            name, directory = (
                args[args.index("--pattern") + 1],
                args[args.index("--dir") + 1],
            )
            if name in self.assets:
                (pathlib.Path(directory) / name).write_bytes(self.assets[name])
            else:
                code = 1
        if check and code:
            raise subprocess.CalledProcessError(code, args)
        return subprocess.CompletedProcess(args, code, out, b"")


def test_release_store_reads_and_writes_assets_with_gh():
    gh = FakeGh()
    store = ReleaseStore("backtest-cache", "me/sportsml", run=gh)
    assert store.names() == set()
    frame = pd.DataFrame({"season": [2024], "x": [1.5]})
    store.put_season("nhl", 2024, "abc", frame, frame)
    assert gh.created and len(gh.assets) == 2
    assert all(call[-2:] == ["--repo", "me/sportsml"] for call in gh.calls)
    fresh = ReleaseStore("backtest-cache", "me/sportsml", run=gh)
    pool, _ = fresh.get_season("nhl", 2024, "abc")
    pd.testing.assert_frame_equal(pool, frame)
    assert fresh.get_season("nhl", 2023, "abc") is None


def test_open_store_specs(tmp_path):
    assert open_store(None) is None
    assert isinstance(open_store(str(tmp_path)), DirectoryStore)
    store = open_store("release:me/sportsml@backtest-cache")
    assert (store.tag, store.repo) == ("backtest-cache", "me/sportsml")
    assert open_store("release:backtest-cache").repo is None
