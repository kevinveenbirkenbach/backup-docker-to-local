.PHONY: install build \
		test-e2e test test-unit test-integration

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

# ------------------------------------------------------------
# Run E2E tests inside the container (Docker socket required)
# ------------------------------------------------------------
# E2E via isolated Docker-in-Docker (DinD)
# - depends on local image build
# - starts a DinD daemon container on a dedicated network
# - loads the freshly built image into DinD
# - runs the unittest suite inside a container that talks to DinD via DOCKER_HOST
test-e2e: clean build
	@bash scripts/test-e2e.sh

test: test-unit test-integration test-e2e

test-unit: clean build
	@echo ">> Running unit tests"
	@docker run --rm -t $(IMAGE) \
	  bash -lc 'python -m unittest discover -t . -s tests/unit -p "test_*.py" -v'

test-integration: clean build
	@echo ">> Running integration tests"
	@docker run --rm -t $(IMAGE) \
	  bash -lc 'python -m unittest discover -t . -s tests/integration -p "test_*.py" -v'