PYTHON_IMAGE ?= python:3.12-slim
DOCKER_RUN := docker run --rm -v $(CURDIR):/hass -w /hass $(PYTHON_IMAGE)
DOCKER_RUN_LIVE := docker run --rm --network host -v $(CURDIR):/hass -w /hass \
  -e WISDOM_AMP_HOST \
  -e WISDOM_AMP_PORT \
  $(PYTHON_IMAGE)

.PHONY: help test test-verbose test-fast test-cov test-one test-live lint fix check dev-shell clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

test: ## Run the full pytest suite
	$(DOCKER_RUN) bash -c "pip install -q -e .[dev] && pytest -q"

test-verbose: ## Run pytest with verbose per-test output
	$(DOCKER_RUN) bash -c "pip install -q -e .[dev] && pytest -v"

test-fast: ## Run pytest with -x --tb=short (fail-fast dev loop)
	$(DOCKER_RUN) bash -c "pip install -q -e .[dev] && pytest -x --tb=short -q"

test-cov: ## Run pytest with coverage report
	$(DOCKER_RUN) bash -c "pip install -q -e .[dev] pytest-cov && \
	  pytest --cov=custom_components.wisdom_amp --cov-report=term-missing -q"

test-one: ## Run a specific test (TEST=tests/test_x.py::test_name)
	@test -n "$(TEST)" || (echo 'usage: make test-one TEST=tests/...'; exit 1)
	$(DOCKER_RUN) bash -c "pip install -q -e .[dev] && pytest -v $(TEST)"

test-live: ## Run the opt-in read-only live tests (needs WISDOM_AMP_HOST)
	@test -n "$$WISDOM_AMP_HOST" || (echo 'WISDOM_AMP_HOST not set'; exit 1)
	$(DOCKER_RUN_LIVE) bash -c "pip install -q -e .[dev] && pytest -m live --force-enable-socket -v tests/test_live_readonly.py"

lint: ## Lint with ruff (read-only)
	$(DOCKER_RUN) bash -c "pip install -q ruff && ruff check ."

fix: ## Auto-fix ruff findings where possible
	$(DOCKER_RUN) bash -c "pip install -q ruff && ruff check --fix ."

check: lint test ## Run lint and tests (the CI gate)

dev-shell: ## Drop into an interactive bash shell with deps installed
	docker run --rm -it -v $(CURDIR):/hass -w /hass $(PYTHON_IMAGE) bash -c \
	  "pip install -q -e .[dev] && bash"

clean: ## Remove pytest / ruff caches and Python build artifacts
	docker run --rm -v $(CURDIR):/t --entrypoint bash $(PYTHON_IMAGE) -c \
	  "find /t \( -name __pycache__ -o -name '*.egg-info' -o -name '.pytest_cache' -o -name '.ruff_cache' -o -name 'build' -o -name 'dist' \) -exec rm -rf {} + 2>/dev/null || true"
