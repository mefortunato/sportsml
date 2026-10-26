VERSION ?= $(shell uv version --short)
REGISTRY ?= ghcr.io/mefortunato/sportsml
IMAGE ?= $(REGISTRY):$(VERSION)

.PHONY: build push pull cli webdata site-data site web-dev artifact test lint format

# --- Docker: the CLI / training image ------------------------------------------
build:
	docker build -t $(IMAGE) -f docker/Dockerfile .

push:
	docker push $(IMAGE)

pull:
	docker pull $(IMAGE)

# any CLI command inside the image, e.g. make cli ARGS="nfl predict";
# add DOCKER_ARGS="--gpus all" for GPU
cli:
	docker run -it --rm $(DOCKER_ARGS) -v $(CURDIR):/project $(IMAGE) $(ARGS)

# --- Static site ----------------------------------------------------------------
# train, backtest and rank (slow; the Train workflow does this on GitHub)
webdata:
	uv run sportsml web build --output_dir webdata

# re-download results and export every page's data to web/static/data (fast;
# the daily Site workflow does this)
site-data:
	uv run sportsml web export --data_dir webdata --output_dir web/static --refresh true

# the site in web/build (set BASE_PATH=/sportsml to match GitHub Pages)
site: site-data
	cd web && npm ci && npm run build

# frontend with hot reload on :5173, reading web/static/data
web-dev:
	cd web && npm run dev

# one-page build (hash routing, inlined), e.g. for a claude.ai artifact:
# web/build-artifact/ holds sportsml.html plus data/
artifact:
	cd web && npm ci && npm run build:artifact
	uv run sportsml web export --data_dir webdata --output_dir web/build-artifact

# --- Checks ---------------------------------------------------------------------
test:
	uv run pytest
	cd web && npm test

lint:
	uv run ruff check
	uv run ruff format --check
	cd web && npm run check

format:
	uv run ruff check --fix
	uv run ruff format
