.PHONY: install test lint format typecheck check container-test

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	python -m mypy src/azathoth tests

check:
	python -m ruff check .
	python -m ruff format --check .
	python -m mypy src/azathoth tests
	python -m pytest

container-test:
	docker build --tag azathoth:test .
	AZATHOTH_RUN_CONTAINER_TESTS=1 AZATHOTH_CONTAINER_IMAGE=azathoth:test python -m pytest tests/container -ra
