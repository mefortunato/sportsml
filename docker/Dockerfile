# Runs the `sportsml` CLI. The PyPI torch build bundles CUDA, so the same
# image trains on CPU, or on GPU with `docker run --gpus all ...`.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# dependencies first, so code changes don't reinstall them
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-default-groups

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups

ENV PATH="/app/.venv/bin:$PATH"
# mount your working directory here; data/, models/ and mlflow.db live in it
WORKDIR /project
ENTRYPOINT ["sportsml"]
