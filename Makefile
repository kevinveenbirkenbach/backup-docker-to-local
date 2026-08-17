.PHONY: install install-lint build clean lint ruff ruff-fix \
		test test-unit test-integration test-e2e \
		test-unit-run test-integration-run test-e2e-run

# Default python if no venv is active
PY_DEFAULT ?= python3

IMAGE_NAME ?= baudolo
IMAGE_TAG  ?= local
IMAGE      := $(IMAGE_NAME):$(IMAGE_TAG)

install:
	@set -eu; \
	PY="$(PY_DEFAULT)"; \
	if [ -n "$${VIRTUAL_ENV:-}" ] && [ -x "$${VIRTUAL_ENV}/bin/python" ]; then \
		PY="$${VIRTUAL_ENV}/bin/python"; \
	fi; \
	echo ">>> Using python: $$PY"; \
	"$$PY" -m pip install --upgrade pip; \
	"$$PY" -m pip install -e .; \
	command -v baudolo >/dev/null 2>&1 || { \
		echo "ERROR: baudolo not found on PATH after install"; \
		exit 2; \
	}; \
	baudolo --help >/dev/null 2>&1 || true

# ------------------------------------------------------------
# Build the baudolo Docker image
# ------------------------------------------------------------
build:
	@echo ">> Building Docker image $(IMAGE)"
	docker build -t $(IMAGE) .

clean:
	git clean -fdX .

# Separate from `install` so the test image does not have to carry the linter.
install-lint:
	@$(PY_DEFAULT) -m pip install -q -e ".[lint]"

# Runs on the host, not in the image, so it also covers what the Dockerfile
# does not copy.
ruff: install-lint
	@echo ">> Running ruff over the whole repository"
	@$(PY_DEFAULT) -m ruff check .
	@$(PY_DEFAULT) -m ruff format --check .

ruff-fix: install-lint
	@$(PY_DEFAULT) -m ruff check --fix .
	@$(PY_DEFAULT) -m ruff format .

lint: ruff

# build runs once, then lint and the three suites run concurrently via -j4; the
# *-run targets carry no build prereq so the sub-make cannot race a second build.
# `clean` is deliberately not a prerequisite; .dockerignore keeps the image
# context clean instead.
test:
	@$(MAKE) build
	@$(MAKE) -j4 lint test-unit-run test-integration-run test-e2e-run

test-unit: build test-unit-run

test-integration: build test-integration-run

test-e2e: build test-e2e-run

test-unit-run:
	@echo ">> Running unit tests"
	@docker run --rm -t $(IMAGE) \
	  bash -lc 'python -m unittest discover -t . -s tests/unit -p "test_*.py" -v'

test-integration-run:
	@echo ">> Running integration tests"
	@docker run --rm -t $(IMAGE) \
	  bash -lc 'python -m unittest discover -t . -s tests/integration -p "test_*.py" -v'

# E2E via isolated Docker-in-Docker (DinD): starts a DinD daemon on a dedicated
# network, loads the freshly built image into it, and runs tests/e2e inside a
# container that talks to DinD via DOCKER_HOST.
test-e2e-run:
	@bash scripts/test-e2e.sh
