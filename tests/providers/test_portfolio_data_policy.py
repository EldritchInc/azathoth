"""Tests that a portfolio entry holds its declared data policy, in every repository (ADR 0123)."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from azathoth.providers import (
    InMemoryModelPortfolioRepository,
    ModelPortfolioEntry,
    ModelPortfolioRepository,
    SQLiteModelPortfolioRepository,
)
from azathoth.revisions import Author, content_digest
from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
)

FRONTIER = ModelPortfolioEntry(provider="openrouter", model="example/frontier")

LOCAL = ModelPortfolioEntry(provider="bedrock", model="example/local")

RETAINING = DataPolicy(retains_data=PolicyAnswer.YES, trains_on_data=PolicyAnswer.NO)


# Entries


def test_an_entrys_policy_is_unknown_until_declared() -> None:
    assert FRONTIER.data_policy == UNKNOWN_DATA_POLICY


def test_an_entry_of_unknown_policy_dumps_as_it_did_before_policies() -> None:
    assert FRONTIER.model_dump(mode="json") == {
        "provider": "openrouter",
        "model": "example/frontier",
    }
    assert content_digest(FRONTIER) == content_digest(
        ModelPortfolioEntry.model_validate_json(
            json.dumps({"provider": "openrouter", "model": "example/frontier"})
        )
    )


@pytest.mark.parametrize(
    "policy",
    [
        PRIVATE_DATA_POLICY,
        RETAINING,
        DataPolicy(trains_on_data=PolicyAnswer.NO),
    ],
    ids=["private", "retaining", "one-answer"],
)
def test_a_declared_policy_dumps_and_reads_back(
    policy: DataPolicy,
) -> None:
    entry = FRONTIER.model_copy(update={"data_policy": policy})

    assert entry.model_dump(mode="json")["data_policy"] == policy.model_dump(mode="json")
    assert ModelPortfolioEntry.model_validate_json(entry.model_dump_json()) == entry
    assert content_digest(entry) != content_digest(FRONTIER)


def test_an_entry_refuses_an_unknown_answer() -> None:
    with pytest.raises(ValueError):
        ModelPortfolioEntry.model_validate(
            {
                "provider": "openrouter",
                "model": "example/frontier",
                "data_policy": {"retains_data": "maybe"},
            }
        )


# Repositories

RepositoryFactory = Callable[[Path], ModelPortfolioRepository]

REPOSITORIES: dict[str, RepositoryFactory] = {
    "memory": lambda _path: InMemoryModelPortfolioRepository(),
    "sqlite": lambda path: SQLiteModelPortfolioRepository(path / "portfolio.db"),
}


@pytest.fixture(params=sorted(REPOSITORIES))
def repository(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> ModelPortfolioRepository:
    """Return an empty portfolio repository of each kind in turn."""

    factory = REPOSITORIES[str(request.param)]

    return factory(tmp_path)


def test_an_entry_is_saved_with_its_policy(
    repository: ModelPortfolioRepository,
) -> None:
    entry = FRONTIER.model_copy(update={"data_policy": PRIVATE_DATA_POLICY})

    repository.save(entry)

    assert repository.get(entry.identifier) == entry


def test_declaring_a_policy_replaces_it_and_returns_the_entry(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER)

    declared = repository.set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY)

    assert declared == FRONTIER.model_copy(update={"data_policy": PRIVATE_DATA_POLICY})
    assert repository.get(FRONTIER.identifier) == declared

    redeclared = repository.set_data_policy(FRONTIER.identifier, RETAINING)

    assert redeclared.data_policy == RETAINING
    assert repository.get(FRONTIER.identifier) == redeclared


def test_declaring_a_policy_keeps_the_entrys_place_and_provenance(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER, author=Author(name="Eris"))
    repository.save(LOCAL)

    before = repository.provenance(FRONTIER.identifier)

    repository.set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY)

    assert [entry.identifier for entry in repository.entries()] == [
        FRONTIER.identifier,
        LOCAL.identifier,
    ]
    assert repository.provenance(FRONTIER.identifier) == before
    assert repository.get(LOCAL.identifier) == LOCAL


def test_declaring_the_policy_of_an_unknown_entry_is_refused(
    repository: ModelPortfolioRepository,
) -> None:
    with pytest.raises(ValueError) as caught:
        repository.set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY)

    assert (
        str(caught.value) == "Model portfolio entry 'openrouter/example/frontier' does not exist."
    )
    assert repository.entries() == ()


def test_a_declared_policy_survives_reopening_the_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "portfolio.db"

    SQLiteModelPortfolioRepository(path).save(FRONTIER)
    SQLiteModelPortfolioRepository(path).set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY)

    reopened = SQLiteModelPortfolioRepository(path).get(FRONTIER.identifier)

    assert reopened is not None
    assert reopened.data_policy == PRIVATE_DATA_POLICY


# Who declared it


def test_an_entry_added_with_a_declared_policy_records_its_author_as_declaring_it(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(
        FRONTIER.model_copy(update={"data_policy": PRIVATE_DATA_POLICY}),
        author=Author(name="Eris"),
    )

    declaration = repository.policy_declaration(FRONTIER.identifier)
    provenance = repository.provenance(FRONTIER.identifier)

    assert declaration is not None and provenance is not None
    assert declaration.identifier == FRONTIER.identifier
    assert declaration.author == Author(name="Eris")
    assert declaration.declared_at == provenance.added_at


def test_an_entry_added_without_a_policy_records_no_declaration(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER, author=Author(name="Eris"))

    assert repository.policy_declaration(FRONTIER.identifier) is None
    assert repository.policy_declaration("openrouter/example/missing") is None


def test_each_declaration_replaces_who_declared_and_when(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER)
    repository.set_data_policy(FRONTIER.identifier, RETAINING, author=Author(name="Eris"))

    first = repository.policy_declaration(FRONTIER.identifier)

    repository.set_data_policy(
        FRONTIER.identifier,
        PRIVATE_DATA_POLICY,
        author=Author(name="Discordia", email="discordia@example.com"),
    )

    second = repository.policy_declaration(FRONTIER.identifier)

    assert first is not None and second is not None
    assert first.author == Author(name="Eris")
    assert second.author == Author(name="Discordia", email="discordia@example.com")
    assert second.declared_at >= first.declared_at


def test_a_declaration_without_an_author_records_none(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER)
    repository.set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY)

    declaration = repository.policy_declaration(FRONTIER.identifier)

    assert declaration is not None
    assert declaration.author is None


def test_a_declaration_leaves_the_entrys_digest_and_provenance_alone(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER, author=Author(name="Eris"))
    before = repository.provenance(FRONTIER.identifier)

    declared = repository.set_data_policy(
        FRONTIER.identifier,
        PRIVATE_DATA_POLICY,
        author=Author(name="Discordia"),
    )

    assert repository.provenance(FRONTIER.identifier) == before
    assert content_digest(declared) == content_digest(
        FRONTIER.model_copy(update={"data_policy": PRIVATE_DATA_POLICY})
    )


def test_removing_an_entry_removes_its_declaration(
    repository: ModelPortfolioRepository,
) -> None:
    repository.save(FRONTIER)
    repository.set_data_policy(FRONTIER.identifier, PRIVATE_DATA_POLICY, author=Author(name="Eris"))
    repository.delete(FRONTIER.identifier)

    assert repository.policy_declaration(FRONTIER.identifier) is None

    repository.save(FRONTIER)

    assert repository.policy_declaration(FRONTIER.identifier) is None


def test_a_declaration_survives_reopening_the_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "portfolio.db"

    SQLiteModelPortfolioRepository(path).save(FRONTIER)
    SQLiteModelPortfolioRepository(path).set_data_policy(
        FRONTIER.identifier,
        PRIVATE_DATA_POLICY,
        author=Author(name="Eris", email="eris@example.com"),
    )

    reopened = SQLiteModelPortfolioRepository(path).policy_declaration(FRONTIER.identifier)

    assert reopened is not None
    assert reopened.author == Author(name="Eris", email="eris@example.com")
    assert reopened.declared_at.tzinfo is not None
