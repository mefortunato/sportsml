# The SportsML web app: SvelteKit frontend + FastAPI backend, with each
# sport's data, trained model and historical (challenge) predictions baked in
# at build time. At runtime the server re-downloads results and refreshes
# team state every few hours (SPORTSML_REFRESH=0 disables it).
#
#   docker build -t sportsml -f docker/Dockerfile .
#   docker run --rm -p 8000:8000 sportsml       # http://localhost:8000
#
# Building needs network access (nflverse data) and takes ~15-20 minutes,
# mostly the walk-forward backtest that produces the challenge games.

# --- 1. frontend -> static files -------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2. python app + baked data ----------------------------------------------
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# dependencies first, so code changes don't reinstall them
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-default-groups

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups

ENV PATH="/app/.venv/bin:$PATH"

# download, train and backtest; one directory per sport under /app/webdata
ARG SPORTS="[nfl]"
ARG BACKTEST_SEASONS=5
RUN MLFLOW_TRACKING_URI=sqlite:////tmp/mlflow.db \
    sportsml web build --sports "$SPORTS" --backtest_seasons "$BACKTEST_SEASONS" \
        --output_dir /app/webdata

COPY --from=web /web/build /app/static

ENV SPORTSML_REFRESH=1 SPORTSML_REFRESH_HOURS=6
EXPOSE 8000
CMD ["sportsml", "web", "serve", "--data_dir", "/app/webdata", \
     "--static_dir", "/app/static", "--host", "0.0.0.0", "--port", "8000"]
