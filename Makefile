.PHONY: install test lint format typecheck check container-test postgres-test

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

POSTGRES_TEST_CONTAINER = azathoth-postgres-test
POSTGRES_TEST_URL = postgresql://azathoth:azathoth@127.0.0.1:54329/azathoth

postgres-test:
	docker rm --force $(POSTGRES_TEST_CONTAINER) > /dev/null 2>&1 || true
	docker run --detach --rm --name $(POSTGRES_TEST_CONTAINER) --publish 127.0.0.1:54329:5432 \
		--env POSTGRES_USER=azathoth --env POSTGRES_PASSWORD=azathoth --env POSTGRES_DB=azathoth \
		postgres:17 > /dev/null
	until docker exec $(POSTGRES_TEST_CONTAINER) pg_isready --host=127.0.0.1 --username=azathoth --quiet; do sleep 1; done; \
	AZATHOTH_TEST_POSTGRES_URL=$(POSTGRES_TEST_URL) python -m pytest tests/persistence -ra; \
	status=$$?; \
	docker stop $(POSTGRES_TEST_CONTAINER) > /dev/null; \
	exit $$status
