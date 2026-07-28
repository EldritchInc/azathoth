.PHONY: install test lint format typecheck check

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