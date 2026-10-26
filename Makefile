VERSION ?= $(shell uv version --short)
REGISTRY ?= ghcr.io/mefortunato/sportsml
IMAGE ?= $(REGISTRY):$(VERSION)

.PHONY: build push pull run cli webdata web-build serve web-dev test lint format

# --- Docker: the full web app (frontend + API + baked data) -----------------
build:
	docker build -t $(IMAGE) -f docker/Dockerfile .

push:
	docker push $(IMAGE)

pull:
	docker pull $(IMAGE)

# serve the app on http://localhost:8000; add DOCKER_ARGS="--gpus all" for GPU
run:
	docker run --rm -p 8000:8000 $(DOCKER_ARGS) $(IMAGE)

# any CLI command inside the image, e.g. make cli ARGS="nfl predict"
cli:
	docker run -it --rm $(DOCKER_ARGS) -v $(CURDIR):/project -w /project $(IMAGE) \
		sportsml $(ARGS)

# --- Local web app development -------------------------------------------------
webdata:
	uv run sportsml web build --output_dir webdata

web-build:
	cd web && npm ci && npm run build

serve:
	uv run sportsml web serve --data_dir webdata --static_dir web/build

# frontend with hot reload on :5173, proxying /api to `make serve` on :8000
web-dev:
	cd web && npm run dev

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
