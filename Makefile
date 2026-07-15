.PHONY: install build clean \
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

# clean + build run once and in order, then the three suites run concurrently
# via -j3; the *-run targets carry no clean/build prereq so the sub-make cannot
# race a second clean against build.
test:
	@$(MAKE) clean
	@$(MAKE) build
	@$(MAKE) -j3 test-unit-run test-integration-run test-e2e-run

test-unit: clean build test-unit-run

test-integration: clean build test-integration-run

test-e2e: clean build test-e2e-run

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
