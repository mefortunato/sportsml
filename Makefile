VERSION ?= $(shell uv version --short)
REGISTRY ?= ghcr.io/mefortunato/sportsml
IMAGE ?= $(REGISTRY):$(VERSION)

.PHONY: build push pull run test lint format

build:
	docker build -t $(IMAGE) -f docker/Dockerfile .

push:
	docker push $(IMAGE)

pull:
	docker pull $(IMAGE)

# e.g. make run ARGS="nfl fit sklearn"; add DOCKER_ARGS="--gpus all" for GPU
run:
	docker run -it --rm $(DOCKER_ARGS) -v $(CURDIR):/project $(IMAGE) $(ARGS)

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check

format:
	uv run ruff check --fix
	uv run ruff format
