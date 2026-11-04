import hashlib
import io
import json
import pathlib
import subprocess
import tarfile

import pytest

from sportsml.web import release

CHECK_GPU = release._check_gpu


def tar_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, text in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(text)
            tar.addfile(info, io.BytesIO(text.encode()))
    return buffer.getvalue()


def names_in(data: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        return {m.name for m in tar.getmembers() if m.isfile()}


class FakeWorld:
    """Stands in for gh, git and the sport build subprocesses."""

    def __init__(self, assets=None, status="", head="abc", failing=()):
        self.assets = assets or {}  # {tag: {name: bytes}}
        self.status, self.head, self.failing = status, head, failing
        self.calls = []
        self.view_error = None

    def __call__(self, command, check=False, **kwargs):
        command = list(command)
        self.calls.append(command)
        out, code, err = "", 0, b""
        if command[0] == "git":
            if command[1:3] == ["remote", "get-url"]:
                out = "git@github.com:me/sportsml.git"
            elif command[1] == "status":
                out = self.status
            elif command[1] == "rev-parse":
                out = "abc" if command[2] == "origin/main" else self.head
        elif command[:2] == ["gh", "repo"]:
            out = "ADMIN"
        elif command[:2] == ["gh", "run"]:
            out = "0"
        elif command[:3] == ["gh", "release", "view"]:
            tag = command[3]
            if self.view_error:
                code, err = 1, self.view_error
            elif tag not in self.assets:
                code, err = 1, b"release not found"
            else:
                out = json.dumps(
                    {"assets": [{"name": n} for n in self.assets[tag]]}
                ).encode()
        elif command[:3] == ["gh", "release", "download"]:
            tag, pattern = command[3], command[command.index("--pattern") + 1]
            if pattern in self.assets.get(tag, {}):
                target = pathlib.Path(command[command.index("--dir") + 1])
                (target / pattern).write_bytes(self.assets[tag][pattern])
            else:
                code = 1
        elif command[:3] == ["gh", "release", "create"]:
            self.assets[command[3]] = {}
        elif command[:3] == ["gh", "release", "upload"]:
            path = pathlib.Path(command[4])
            self.assets[command[3]][path.name] = path.read_bytes()
        elif "build" in command:
            sport = command[command.index("--sports") + 1].strip("[]")
            directory = pathlib.Path(command[command.index("--output_dir") + 1]) / sport
            if sport in self.failing:
                code = 1
            else:
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "meta.json").write_text('{"new": true}')
        if check and code:
            raise subprocess.CalledProcessError(code, command, stderr=err)
        if kwargs.get("text") and isinstance(out, bytes):
            out = out.decode()
        if not kwargs.get("text") and isinstance(out, str):
            out = out.encode()
        return subprocess.CompletedProcess(command, code, out, err)

    def called(self, *prefix):
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = FakeWorld(
        {
            "webdata": {
                "webdata.tar.gz": tar_of(
                    {"./nfl/meta.json": "old", "./nba/meta.json": "old"}
                )
            }
        }
    )
    monkeypatch.setattr(release, "_run", fake)
    monkeypatch.setattr(release, "_check_gpu", lambda: None)
    return fake


def test_publish_merges_into_the_release_and_starts_the_site(world, tmp_path):
    (tmp_path / "built/nfl").mkdir(parents=True)
    (tmp_path / "built/nfl/meta.json").write_text("new")

    release.publish_webdata("built", repo="me/sportsml")

    data = world.assets["webdata"]["webdata.tar.gz"]
    assert names_in(data) == {"./nfl/meta.json", "./nba/meta.json"}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        assert tar.extractfile("./nfl/meta.json").read() == b"new"
        assert tar.extractfile("./nba/meta.json").read() == b"old"
    site = world.called("gh", "workflow", "run", "site.yml")[0]
    assert f"webdata_sha256={hashlib.sha256(data).hexdigest()}" in site
    assert site[-2:] == ["--repo", "me/sportsml"]


def test_a_failed_read_never_publishes_over_the_other_sports(world, tmp_path):
    (tmp_path / "built/nfl").mkdir(parents=True)
    (tmp_path / "built/nfl/meta.json").write_text("new")
    before = dict(world.assets["webdata"])
    world.view_error = b"HTTP 502: bad gateway"

    with pytest.raises(RuntimeError, match="cannot read"):
        release.publish_webdata("built", repo="me/sportsml")

    assert world.assets["webdata"] == before
    assert not world.called("gh", "workflow")


def test_the_first_publish_creates_the_release(world, tmp_path):
    del world.assets["webdata"]
    (tmp_path / "built/nfl").mkdir(parents=True)
    (tmp_path / "built/nfl/meta.json").write_text("new")

    release.publish_webdata("built", repo="me/sportsml")

    assert names_in(world.assets["webdata"]["webdata.tar.gz"]) == {"./nfl/meta.json"}


def test_publish_requires_a_finished_build(world, tmp_path):
    (tmp_path / "built/nfl").mkdir(parents=True)
    with pytest.raises(SystemExit, match="nothing to publish"):
        release.publish_webdata("built")
    with pytest.raises(SystemExit, match="not a finished build"):
        release.publish_webdata("built", ["nfl"])


def test_train_local_publishes_what_built_and_reports_what_failed(world):
    world.failing = ("nba",)

    with pytest.raises(SystemExit, match="nba"):
        release.train_local(["nfl", "nba"])

    with tarfile.open(
        fileobj=io.BytesIO(world.assets["webdata"]["webdata.tar.gz"]), mode="r:gz"
    ) as tar:
        assert b"new" in tar.extractfile("./nfl/meta.json").read()
        assert tar.extractfile("./nba/meta.json").read() == b"old"
    builds = [c for c in world.calls if "build" in c]
    # origin's repository, not whatever gh resolves
    assert all("release:me/sportsml@backtest-cache" in c for c in builds)
    assert len(world.called("gh", "workflow", "run")) == 1


def test_train_local_starts_from_the_release(world, tmp_path, monkeypatch):
    seen = {}
    inner = world.__call__

    def spy(command, **kwargs):
        if "build" in command:
            seen["meta"] = (tmp_path / "webdata/nfl/meta.json").read_text()
        return inner(command, **kwargs)

    monkeypatch.setattr(release, "_run", spy)
    (tmp_path / "webdata/nfl").mkdir(parents=True)
    (tmp_path / "webdata/nfl/stale.csv").write_text("x")

    release.train_local(["nfl"])

    assert seen["meta"] == "old"
    assert not (tmp_path / "webdata/nfl/stale.csv").exists()
    assert not (tmp_path / "webdata/nba").exists()


@pytest.mark.parametrize(
    "state, message",
    [({"status": " M src/x.py"}, "uncommitted"), ({"head": "def"}, "origin/main")],
)
def test_train_local_only_publishes_mains_code(world, state, message):
    world.status = state.get("status", "")
    world.head = state.get("head", "abc")
    with pytest.raises(SystemExit, match=message):
        release.train_local(["nfl"])
    assert not [c for c in world.calls if "build" in c]


def test_publish_false_writes_nothing_to_github(world):
    world.status, world.head = " M src/x.py", "def"
    before = dict(world.assets["webdata"])

    release.train_local(["nfl"], publish=False)

    build = next(c for c in world.calls if "build" in c)
    assert "--cache" not in build
    assert world.assets["webdata"] == before
    assert not world.called("gh", "release", "upload")
    assert not world.called("gh", "workflow")


def test_train_local_stops_without_a_gpu(world, monkeypatch):
    import torch

    monkeypatch.setattr(release, "_check_gpu", CHECK_GPU)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(SystemExit, match="no GPU"):
        release.train_local(["nfl"])
    assert not [c for c in world.calls if "build" in c]


def test_download_cache_round_trip_keeps_what_a_machine_has(world, tmp_path):
    cache = tmp_path / "data/cbb/espn_cache"
    cache.mkdir(parents=True)
    (cache / "lines.json").write_text("{}")
    release.push_data(["cbb", "nfl"], repo="me/sportsml")
    assert list(world.assets["data-cache"]) == ["data-cbb.tar.gz"]
    assert names_in(world.assets["data-cache"]["data-cbb.tar.gz"]) == {
        "cbb/espn_cache/lines.json"
    }

    (cache / "lines.json").write_text('{"newer": 1}')
    release.pull_data(["cbb"], repo="me/sportsml")
    assert (cache / "lines.json").read_text() == '{"newer": 1}'

    (cache / "lines.json").unlink()
    cache.rmdir()
    release.pull_data(["cbb", "nfl"], repo="me/sportsml")
    assert (cache / "lines.json").read_text() == "{}"


def test_env_file_fills_in_what_the_environment_lacks(tmp_path, monkeypatch):
    monkeypatch.setenv("SET_ALREADY", "keep")
    monkeypatch.delenv("FROM_FILE", raising=False)
    env = tmp_path / ".env"
    env.write_text("# note\nexport FROM_FILE='abc'\nSET_ALREADY=other\n\n")
    release._load_env(str(env))
    assert release.os.environ["FROM_FILE"] == "abc"
    assert release.os.environ["SET_ALREADY"] == "keep"
    monkeypatch.delenv("FROM_FILE")
