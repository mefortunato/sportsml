# SportsML

ML for sports

## Installation

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

This creates the virtual environment and installs all dependencies (including PyTorch with CUDA support on Linux/Windows).

## Running

Commands can be run with `uv run`:

```sh
uv run sportsml --help
```

Alternatively, you can activate the virtual environment directly:

```sh
source .venv/bin/activate
sportsml ...
python ...
```
