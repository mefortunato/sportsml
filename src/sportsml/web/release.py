"""Train on this machine (e.g. with a GPU) and publish like the Train workflow.

``sportsml web train_local`` does what ``.github/workflows/train.yml`` does,
one sport after another: start from the ``webdata`` release, build each sport
with the shared ``backtest-cache`` release, then merge the sports that built
into ``webdata`` and start the Site workflow, which deploys them. The workflow
uses :func:`publish_webdata` as well, so both publish the same way.

Three releases connect this machine and the workflow:

- ``webdata``: what the site is built from;
- ``backtest-cache``: backtest seasons and models by key
  (:mod:`sportsml.web.cache`);
- ``data-cache``: each sport's download cache (``data-<sport>.tar.gz``), so a
  new machine, or a workflow run whose Actions cache was evicted (after 7
  unused days), does not repeat tens of thousands of odds requests.

This module is under ``web/``, outside :func:`~sportsml.web.build.code_hash`.
"""

from __future__ import annotations

import hashlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from ..core.sport import BUILTIN_SPORTS
from .cache import ReleaseStore

WEBDATA_TAG = "webdata"
WEBDATA_ASSET = "webdata.tar.gz"
BACKTEST_CACHE_TAG = "backtest-cache"
DATA_CACHE_TAG = "data-cache"
# the per-sport directories under data/<sport>/ that hold downloads
CACHE_DIRS = ("espn_cache", "nhl_cache", "mlb_cache")


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **kwargs)


def _webdata_store(repo: str | None) -> ReleaseStore:
    return ReleaseStore(
        WEBDATA_TAG,
        repo,
        run=_run,
        title="Web data (trained model and backtest)",
        notes="Written by the Train workflow or sportsml web train_local; "
        "the Site workflow builds from it.",
    )


def _data_store(repo: str | None) -> ReleaseStore:
    return ReleaseStore(
        DATA_CACHE_TAG,
        repo,
        run=_run,
        title="Download cache",
        notes="Each sport's finished seasons and lines "
        "(sportsml web pull_data / push_data).",
    )


def _unpack(data: bytes, directory: pathlib.Path, only=None) -> None:
    """Extract a ``.tar.gz``; with ``only``, just those top-level directories."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = [
            m
            for m in tar.getmembers()
            if only is None or pathlib.PurePosixPath(m.name).parts[:1] in only
        ]
        tar.extractall(directory, members=members, filter="data")


def _download_webdata(store: ReleaseStore) -> bytes | None:
    """The current ``webdata`` asset, ``None`` only if there is no such
    release. Any other failure raises: publishing on top of nothing would
    take every sport not being published off the site."""
    done = store.gh("release", "view", store.tag, check=False)
    if done.returncode:
        if b"not found" in done.stderr.lower():
            return None
        raise RuntimeError(f"cannot read the {store.tag} release: {done.stderr!r}")
    data = store.get(WEBDATA_ASSET)
    if data is None and WEBDATA_ASSET in store.names():
        raise RuntimeError(f"cannot download {WEBDATA_ASSET}")
    return data


def publish_webdata(
    data_dir: str = "webdata",
    sports: list[str] | None = None,
    repo: str | None = None,
    ref: str = "main",
    rebuild_site: bool = True,
) -> None:
    """Merge built sports into the ``webdata`` release and start the Site
    workflow. Sports not published keep their build in the release.

    Args:
        data_dir: Holds ``<sport>/`` directories from ``sportsml web build``.
        sports: Which to publish (default: all with a ``meta.json``).
        repo: ``owner/name`` (default: what ``gh`` resolves).
        ref: The branch to run the Site workflow on.
        rebuild_site: Start the Site workflow (else its next run picks it up).
    """
    root = pathlib.Path(data_dir)
    if sports is None:
        built = root.glob("*/meta.json") if root.is_dir() else ()
        sports = sorted(p.parent.name for p in built)
    if not sports:
        raise SystemExit(f"nothing to publish: no sport built in {root}")
    for sport in sports:
        if not (root / sport / "meta.json").exists():
            raise SystemExit(f"{root / sport} is not a finished build")

    store = _webdata_store(repo)
    with tempfile.TemporaryDirectory() as tmp:
        merged = pathlib.Path(tmp) / "webdata"
        merged.mkdir()
        previous = _download_webdata(store)
        if previous is not None:
            _unpack(previous, merged)
        for sport in sports:
            shutil.rmtree(merged / sport, ignore_errors=True)
            shutil.copytree(root / sport, merged / sport)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            tar.add(merged, arcname=".")
    data = buffer.getvalue()
    store.put(WEBDATA_ASSET, data)
    print(f"published {', '.join(sports)} to the {WEBDATA_TAG} release")
    if rebuild_site:
        # Site waits for this exact asset: a download right after the upload
        # can still be served the previous one
        sha256 = hashlib.sha256(data).hexdigest()
        store.gh("workflow", "run", "site.yml", "--ref", ref,
                 "-f", f"webdata_sha256={sha256}")  # fmt: skip
        print("started the Site workflow")


def _cache_dirs(data_dir: str, sport: str) -> list[pathlib.Path]:
    base = pathlib.Path(data_dir) / sport
    return [base / name for name in CACHE_DIRS if (base / name).is_dir()]


def pull_data(
    sports: list[str] | None = None,
    data_dir: str = "data",
    repo: str | None = None,
) -> None:
    """Restore each sport's download cache from the ``data-cache`` release,
    unless this machine already has one (it only ever grows)."""
    store = _data_store(repo)
    for sport in sports or BUILTIN_SPORTS:
        if _cache_dirs(data_dir, sport):
            continue
        name = f"data-{sport}.tar.gz"
        if name not in store.names():
            print(f"{sport}: no download cache in the {store.tag} release")
            continue
        if (data := store.get(name)) is None:
            print(f"{sport}: could not download {name}")
            continue
        pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)
        _unpack(data, pathlib.Path(data_dir))
        print(f"{sport}: restored the download cache from {store.tag}")


def push_data(
    sports: list[str] | None = None,
    data_dir: str = "data",
    repo: str | None = None,
) -> None:
    """Upload each sport's download cache to the ``data-cache`` release."""
    store = _data_store(repo)
    for sport in sports or BUILTIN_SPORTS:
        if not (directories := _cache_dirs(data_dir, sport)):
            continue
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for directory in directories:
                tar.add(directory, arcname=f"{sport}/{directory.name}")
        store.put(f"data-{sport}.tar.gz", buffer.getvalue())
        print(f"{sport}: saved the download cache to {store.tag}")


def _output(*command: str) -> str:
    return _run(command, check=True, capture_output=True, text=True).stdout.strip()


def origin_repo() -> str:
    """``owner/name`` of the ``origin`` remote. Named explicitly because ``gh``
    alone may resolve to another remote."""
    url = _output("git", "remote", "get-url", "origin")
    match = re.search(r"github\.com[:/](.+?/.+?)(?:\.git)?/?$", url)
    if not match:
        raise SystemExit(f"origin is not a GitHub repository: {url}")
    return match.group(1)


def _check_can_publish(repo: str) -> None:
    """Fail now rather than after hours of training. The site exports with
    main's code, so what it deploys must have been built from that code."""
    permission = _run(
        ("gh", "repo", "view", repo, "--json", "viewerPermission",
         "--jq", ".viewerPermission"),
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    if permission.returncode:
        raise SystemExit(f"gh cannot read {repo} (gh auth login?): {permission.stderr}")
    if permission.stdout.strip() not in ("WRITE", "MAINTAIN", "ADMIN"):
        raise SystemExit(f"this gh account cannot write to {repo}")
    if _output("git", "status", "--porcelain"):
        raise SystemExit(
            "uncommitted changes: commit them, or pass --publish false to "
            "try them without publishing"
        )
    _output("git", "fetch", "--quiet", "origin", "main")
    head = _output("git", "rev-parse", "HEAD")
    if head != _output("git", "rev-parse", "origin/main"):
        raise SystemExit(
            "HEAD is not origin/main: check out and pull main, or pass "
            "--publish false to try this code without publishing"
        )


def _check_gpu() -> None:
    import torch

    if not torch.cuda.is_available():
        raise SystemExit(
            "torch sees no GPU (see nvidia-smi); pass --require_gpu false to "
            "train on the CPU anyway"
        )
    print(f"training on {torch.cuda.get_device_name(0)}")


def _warn_if_workflow_running(repo: str) -> None:
    running = _run(
        ("gh", "run", "list", "--repo", repo, "--workflow", "train.yml",
         "--status", "in_progress", "--json", "databaseId", "--jq", "length"),
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    if running.returncode == 0 and running.stdout.strip() not in ("", "0"):
        print(
            "warning: the Train workflow is running too. Each sport's last "
            "publish wins, so it may replace what this run publishes."
        )


def _load_env(path: str = ".env") -> None:
    """``KEY=value`` lines into the environment, which wins over the file."""
    file = pathlib.Path(path)
    for line in file.read_text().splitlines() if file.is_file() else ():
        line = line.strip().removeprefix("export ")
        key, separator, value = line.partition("=")
        if separator and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _error_text(error: Exception) -> str:
    stderr = getattr(error, "stderr", None)
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    return f"{error}: {stderr}" if stderr else str(error)


def train_local(
    sports: list[str] | None = None,
    output_dir: str = "webdata",
    publish: bool = True,
    require_gpu: bool = True,
    refresh_backtest: bool = False,
    reuse_model_days: float = 0,
    repo: str | None = None,
) -> None:
    """The Train workflow on this machine: build each sport in turn and publish
    those that built. A sport that fails keeps its previous build; the exit
    status is then non-zero. Replaces ``<output_dir>/<sport>/``. Reads secrets
    such as ``CBBD_API_KEY`` from ``.env``.

    Each sport builds in its own process, as each does in its own job in the
    workflow. Finished seasons and models reach the ``backtest-cache`` release
    as they complete, so an interrupted run loses little: run it again, with
    ``--reuse_model_days 1`` to keep the models it already trained.

    Args:
        sports: Sports to build (default: all).
        output_dir: Writes ``<output_dir>/<sport>/``.
        publish: With ``false``, write nothing to GitHub (no cache
            either, so uncommitted code is safe to try).
        require_gpu: Stop if torch sees no GPU.
        refresh_backtest: Backtest every season again.
        reuse_model_days: Use a cached model at most this many days old.
        repo: ``owner/name`` (default: the ``origin`` remote).
    """
    _load_env()
    sports = list(sports or BUILTIN_SPORTS)
    repo = repo or origin_repo()
    if publish:
        _check_can_publish(repo)
        _warn_if_workflow_running(repo)
    if require_gpu:
        _check_gpu()
    if "cbb" in sports and not os.environ.get("CBBD_API_KEY"):
        print(
            "warning: CBBD_API_KEY is not set (put it in .env), so new college "
            "basketball lines come from ESPN"
        )

    # the previous build: its backtest seasons can be reused
    root = pathlib.Path(output_dir)
    for sport in sports:
        shutil.rmtree(root / sport, ignore_errors=True)
    previous = _download_webdata(_webdata_store(repo))
    if previous is None:
        print(f"no {WEBDATA_TAG} release yet: backtesting every season")
    else:
        root.mkdir(parents=True, exist_ok=True)
        _unpack(previous, root, only={(sport,) for sport in sports})
    pull_data(sports, repo=repo)

    built, failed = [], []
    for sport in sports:
        print(f"--- {sport} ---", flush=True)
        command = [
            sys.executable, "-m", "sportsml.cli", "web", "build",
            "--sports", f"[{sport}]",
            "--output_dir", output_dir,
            "--refresh_backtest", str(refresh_backtest).lower(),
            "--reuse_model_days", str(reuse_model_days),
        ]  # fmt: skip
        if publish:
            command += ["--cache", f"release:{repo}@{BACKTEST_CACHE_TAG}"]
        ok = _run(command, check=False).returncode == 0
        (built if ok else failed).append(sport)
        if publish:
            # also after a failure: the lines fetched until ESPN refused more
            try:
                push_data([sport], repo=repo)
            except (OSError, subprocess.SubprocessError) as error:
                print(f"warning: {sport} download cache not saved: "
                      f"{_error_text(error)}")  # fmt: skip

    if not publish:
        print(f"built {built or 'nothing'} in {root}; not published")
    elif built:
        publish_webdata(output_dir, built, repo=repo)
    if failed:
        raise SystemExit(f"failed, keeping their previous builds: {failed}")


__all__ = ["publish_webdata", "pull_data", "push_data", "train_local"]
