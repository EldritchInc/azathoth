"""Contract tests of the provider, invocation and content repositories (ADR 0102).

Models, the portfolio, provider observations, production invocations, their
runs and stored content behave the same on SQLite and PostgreSQL. On
PostgreSQL, processes racing for one idempotency key leave exactly one
invocation, and racing to store the same content stores it once.
"""

import threading
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

import pytest

from azathoth.inputs import CONTENT_TABLES, ContentStore, SqlContentStore, content_bytes_digest
from azathoth.persistence import Database, PostgresDatabase, Table
from azathoth.providers import (
    MODEL_PORTFOLIO_TABLES,
    MODEL_TABLES,
    PROVIDER_MODEL_OBSERVATION_TABLES,
    ModelPortfolioRepository,
    ModelRepository,
    ProviderModelObservationRepository,
    SqlModelPortfolioRepository,
    SqlModelRepository,
    SqlProviderModelObservationRepository,
)
from azathoth.workflows import (
    PRODUCTION_INVOCATION_RUN_TABLES,
    PRODUCTION_INVOCATION_TABLES,
    IdempotencyKeyInUseError,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationRepository,
    ProductionInvocationRunRepository,
    ProductionInvocationSuccess,
    SqlProductionInvocationRepository,
    SqlProductionInvocationRunRepository,
)
from tests.providers.test_model_repository import (
    create_first_model,
    create_second_model,
    create_third_model,
)
from tests.providers.test_portfolio_repository import create_entry
from tests.providers.test_provider_observation_repository import (
    create_first_observation,
    create_other_observation,
    create_second_observation,
)
from tests.workflows.test_production_invocation_idempotency_repository import (
    FIRST_INVOCATION_ID,
    FIRST_WORKFLOW_ID,
    KEY,
    OTHER_KEY,
    SECOND_INVOCATION_ID,
    SECOND_WORKFLOW_ID,
    THIRD_INVOCATION_ID,
    create_invocation,
)
from tests.workflows.test_production_invocation_run_repository import (
    FIRST_RUN_ID,
    SECOND_RUN_ID,
    create_association,
)

Repository = TypeVar("Repository")


def initialized(
    database: Database,
    tables: tuple[Table, ...],
    factory: Callable[[Database], Repository],
) -> Repository:
    """Initialize a database with a repository's tables, then open the repository."""

    database.initialize(tables)

    return factory(database)


def race(
    postgres_url: str,
    tables: tuple[Table, ...],
    attempt: Callable[[Database, int], None],
    *,
    racers: int = 6,
) -> list[BaseException]:
    """Run one attempt from several connections at once, returning what each raised."""

    databases = [PostgresDatabase(postgres_url) for _ in range(racers)]
    failures: list[BaseException] = []
    start = threading.Barrier(racers)

    databases[0].initialize(tables)

    def run(
        database: Database,
        index: int,
    ) -> None:
        start.wait()

        try:
            attempt(database, index)
        except BaseException as exc:
            failures.append(exc)

    threads = [
        threading.Thread(target=run, args=(database, index))
        for index, database in enumerate(databases)
    ]

    try:
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
    finally:
        for database in databases:
            database.close()

    return failures


# Models


def models(
    database: Database,
) -> ModelRepository:
    return initialized(database, MODEL_TABLES, SqlModelRepository)


def test_models_read_back_in_order_and_filter_by_provider(
    database: Database,
) -> None:
    repository = models(database)

    for model in (create_second_model(), create_first_model(), create_third_model()):
        repository.save(model)

    assert repository.get(create_first_model().identifier) == create_first_model()
    assert repository.get("nowhere/nothing") is None
    assert repository.models() == (
        create_second_model(),
        create_first_model(),
        create_third_model(),
    )
    assert repository.models_for_provider("openrouter") == tuple(
        model
        for model in (create_second_model(), create_first_model(), create_third_model())
        if model.provider == "openrouter"
    )


def test_a_duplicate_model_is_refused(
    database: Database,
) -> None:
    repository = models(database)
    repository.save(create_first_model())

    with pytest.raises(ValueError, match="already exists"):
        repository.save(create_first_model())


# The portfolio


def portfolio(
    database: Database,
) -> ModelPortfolioRepository:
    return initialized(database, MODEL_PORTFOLIO_TABLES, SqlModelPortfolioRepository)


def test_the_portfolio_keeps_order_and_deletes_one_entry(
    database: Database,
) -> None:
    repository = portfolio(database)

    first = create_entry(model="example/first")
    second = create_entry(model="example/second")
    third = create_entry(provider="other", model="example/third")

    for entry in (first, second, third):
        repository.save(entry)

    repository.delete(second.identifier)

    assert repository.entries() == (first, third)
    assert repository.get(first.identifier) == first
    assert repository.get(second.identifier) is None


def test_the_portfolio_refuses_a_duplicate_and_an_unknown_deletion(
    database: Database,
) -> None:
    repository = portfolio(database)
    repository.save(create_entry())

    with pytest.raises(ValueError, match="already exists"):
        repository.save(create_entry())

    with pytest.raises(ValueError, match="does not exist"):
        repository.delete("example/missing")


# Provider observations


def observations(
    database: Database,
) -> ProviderModelObservationRepository:
    return initialized(
        database,
        PROVIDER_MODEL_OBSERVATION_TABLES,
        SqlProviderModelObservationRepository,
    )


def test_observations_read_back_in_order_and_the_latest_is_found(
    database: Database,
) -> None:
    repository = observations(database)

    first = create_first_observation()
    other = create_other_observation()
    second = create_second_observation()

    for observation in (first, other, second):
        repository.save(observation)

    assert repository.get(first.id) == first
    assert repository.get(UUID(int=0)) is None
    assert repository.observations() == (first, other, second)
    assert repository.observations_for_model(first.identifier) == tuple(
        observation
        for observation in (first, other, second)
        if observation.identifier == first.identifier
    )
    assert repository.latest(second.identifier) == second
    assert repository.latest("nowhere/nothing") is None


def test_a_duplicate_observation_is_refused(
    database: Database,
) -> None:
    repository = observations(database)
    repository.save(create_first_observation())

    with pytest.raises(ValueError, match="already exists"):
        repository.save(create_first_observation())


# Production invocations


def invocations(
    database: Database,
) -> ProductionInvocationRepository:
    return initialized(
        database,
        PRODUCTION_INVOCATION_TABLES,
        SqlProductionInvocationRepository,
    )


def test_invocations_read_back_in_order_and_filter_by_workflow(
    database: Database,
) -> None:
    repository = invocations(database)

    first = create_invocation(key=None)
    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID, workflow_id=SECOND_WORKFLOW_ID, key=None
    )
    third = create_invocation(invocation_id=THIRD_INVOCATION_ID, key=None)

    for invocation in (first, second, third):
        repository.save(invocation)

    assert repository.get(FIRST_INVOCATION_ID) == first
    assert repository.get(UUID(int=0)) is None
    assert repository.invocations() == (first, second, third)
    assert repository.invocations_for_workflow(FIRST_WORKFLOW_ID) == (first, third)


def test_an_invocation_is_found_by_its_idempotency_key(
    database: Database,
) -> None:
    repository = invocations(database)
    keyed = create_invocation()

    repository.save(keyed)

    assert repository.invocation_for_idempotency_key(KEY) == keyed
    assert repository.invocation_for_idempotency_key(OTHER_KEY) is None


def test_a_reused_idempotency_key_is_refused_and_records_nothing(
    database: Database,
) -> None:
    repository = invocations(database)
    repository.save(create_invocation())

    with pytest.raises(IdempotencyKeyInUseError):
        repository.save(create_invocation(invocation_id=SECOND_INVOCATION_ID))

    assert [invocation.id for invocation in repository.invocations()] == [FIRST_INVOCATION_ID]


def test_the_same_invocation_twice_is_a_duplicate_not_a_reused_key(
    database: Database,
) -> None:
    repository = invocations(database)
    repository.save(create_invocation())

    with pytest.raises(ValueError, match=f"Production invocation {FIRST_INVOCATION_ID} already"):
        repository.save(create_invocation())


def test_any_number_of_invocations_may_have_no_key(
    database: Database,
) -> None:
    repository = invocations(database)

    for invocation_id in (FIRST_INVOCATION_ID, SECOND_INVOCATION_ID, THIRD_INVOCATION_ID):
        repository.save(create_invocation(invocation_id=invocation_id, key=None))

    assert len(repository.invocations()) == 3


def test_an_invocation_has_one_terminal_result(
    database: Database,
) -> None:
    repository = invocations(database)
    repository.save(create_invocation())

    success = ProductionInvocationSuccess(invocation_id=FIRST_INVOCATION_ID, result={"n": 7})

    assert repository.result(FIRST_INVOCATION_ID) is None

    repository.save_result(success)

    assert repository.result(FIRST_INVOCATION_ID) == success

    with pytest.raises(ValueError, match="already has a terminal result"):
        repository.save_result(
            ProductionInvocationFailure(
                invocation_id=FIRST_INVOCATION_ID,
                error_code=ProductionInvocationErrorCode.TIMEOUT,
                message="Too slow.",
            )
        )

    assert repository.result(FIRST_INVOCATION_ID) == success


def test_a_result_needs_its_invocation(
    database: Database,
) -> None:
    repository = invocations(database)

    with pytest.raises(ValueError, match="does not exist"):
        repository.save_result(
            ProductionInvocationSuccess(invocation_id=SECOND_INVOCATION_ID, result=None)
        )


def test_processes_racing_for_one_key_leave_exactly_one_invocation(
    postgres_url: str,
) -> None:
    def attempt(
        database: Database,
        index: int,
    ) -> None:
        SqlProductionInvocationRepository(database).save(
            create_invocation(invocation_id=UUID(int=index + 1))
        )

    failures = race(postgres_url, PRODUCTION_INVOCATION_TABLES, attempt)

    database = PostgresDatabase(postgres_url)

    try:
        recorded = SqlProductionInvocationRepository(database).invocations()
    finally:
        database.close()

    assert len(recorded) == 1
    assert len(failures) == 5
    assert all(isinstance(failure, IdempotencyKeyInUseError) for failure in failures)


# Invocation runs


def invocation_runs(
    database: Database,
) -> ProductionInvocationRunRepository:
    return initialized(
        database,
        PRODUCTION_INVOCATION_RUN_TABLES,
        SqlProductionInvocationRunRepository,
    )


def test_an_invocation_has_one_run(
    database: Database,
) -> None:
    repository = invocation_runs(database)

    first = create_association(invocation_id=SECOND_INVOCATION_ID, run_id=FIRST_RUN_ID)
    second = create_association(invocation_id=FIRST_INVOCATION_ID, run_id=SECOND_RUN_ID)

    repository.save(first)
    repository.save(second)

    assert repository.get(SECOND_INVOCATION_ID) == first
    assert repository.get(UUID(int=0)) is None
    assert repository.associations() == (first, second)

    with pytest.raises(ValueError, match="already has a workflow run"):
        repository.save(create_association(invocation_id=SECOND_INVOCATION_ID, run_id=UUID(int=9)))


# Content


def content(
    database: Database,
) -> ContentStore:
    return initialized(database, CONTENT_TABLES, SqlContentStore)


def test_content_reads_back_byte_for_byte(
    database: Database,
) -> None:
    store = content(database)
    data = bytes(range(256)) * 3 + "the old ones wait — ü".encode()

    digest = store.put(data)

    assert digest == content_bytes_digest(data)
    assert store.get(digest) == data
    assert store.contains(digest)
    assert store.get("0" * 64) is None
    assert not store.contains("0" * 64)


def test_storing_the_same_content_again_changes_nothing(
    database: Database,
) -> None:
    store = content(database)

    assert store.put(b"same") == store.put(b"same")

    with database.transaction() as session:
        assert session.fetchone("SELECT COUNT(*), MAX(size_bytes) FROM content_blobs") == (1, 4)


def test_empty_content_is_content(
    database: Database,
) -> None:
    store = content(database)

    assert store.get(store.put(b"")) == b""


def test_processes_racing_to_store_the_same_content_store_it_once(
    postgres_url: str,
) -> None:
    def attempt(
        database: Database,
        index: int,
    ) -> None:
        SqlContentStore(database).put(b"shared content")

    assert race(postgres_url, CONTENT_TABLES, attempt) == []

    database = PostgresDatabase(postgres_url)

    try:
        with database.transaction() as session:
            assert session.fetchone("SELECT COUNT(*) FROM content_blobs") == (1,)
    finally:
        database.close()
