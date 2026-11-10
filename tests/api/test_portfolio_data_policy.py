"""Contract tests for declaring what a portfolio model's provider does with data (ADR 0123)."""

from collections.abc import Iterator

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import ModelPortfolioEntry
from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
)
from tests.api.test_models import ALPHA, BETA, StaticDirectory

RETAINING = api.DataPolicy(retains_data=api.PolicyAnswer.YES, trains_on_data=api.PolicyAnswer.NO)


@pytest.fixture
def modelled(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance whose providers serve Alpha and Beta, closed afterwards."""

    with api.Azathoth(
        open_repositories(location),
        directories=(
            StaticDirectory("provider-a", (ALPHA,)),
            StaticDirectory("provider-b", (BETA,)),
        ),
    ) as instance:
        yield instance


def test_the_api_offers_the_policy_model() -> None:
    assert api.DataPolicy is DataPolicy
    assert api.PolicyAnswer is PolicyAnswer


def test_a_model_is_authorized_with_its_policy_unknown(
    modelled: api.Azathoth,
) -> None:
    entry = modelled.portfolio.add(ALPHA.identifier)

    assert entry.data_policy == UNKNOWN_DATA_POLICY
    assert entry.receives_restricted is False


def test_a_model_is_authorized_with_the_policy_declared(
    modelled: api.Azathoth,
    location: str,
) -> None:
    entry = modelled.portfolio.add(ALPHA.identifier, data_policy=PRIVATE_DATA_POLICY)

    assert entry.data_policy == PRIVATE_DATA_POLICY
    assert entry.receives_restricted is True
    assert modelled.portfolio.list() == (entry,)

    stored = open_repositories(location).portfolio.get(ALPHA.identifier)

    assert stored is not None
    assert stored.data_policy == PRIVATE_DATA_POLICY


def test_declaring_a_policy_replaces_it(
    modelled: api.Azathoth,
    location: str,
) -> None:
    added = modelled.portfolio.add(ALPHA.identifier)
    modelled.portfolio.add(BETA.identifier)

    private = modelled.portfolio.set_data_policy(ALPHA.identifier, PRIVATE_DATA_POLICY)

    assert private.data_policy == PRIVATE_DATA_POLICY
    assert private.receives_restricted is True
    declared = {"data_policy", "receives_restricted", "policy_declared_by", "policy_declared_at"}

    assert private.model_dump(exclude=declared) == added.model_dump(exclude=declared)

    retaining = modelled.portfolio.set_data_policy(ALPHA.identifier, RETAINING)

    assert retaining.data_policy == RETAINING
    assert retaining.receives_restricted is False
    assert [entry.identifier for entry in modelled.portfolio.list()] == [
        ALPHA.identifier,
        BETA.identifier,
    ]
    assert modelled.portfolio.list()[0] == retaining


def test_declaring_the_policy_of_a_model_not_authorized_is_refused(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        modelled.portfolio.set_data_policy(ALPHA.identifier, PRIVATE_DATA_POLICY)

    assert str(raised.value) == "Model 'provider-a/example/alpha' is not authorized."
    assert modelled.portfolio.list() == ()


def test_declaring_a_policy_asks_no_provider(
    location: str,
) -> None:
    open_repositories(location).portfolio.save(
        ModelPortfolioEntry(provider=ALPHA.provider, model=ALPHA.model)
    )

    with api.Azathoth(open_repositories(location), directories=()) as instance:
        declared = instance.portfolio.set_data_policy(ALPHA.identifier, PRIVATE_DATA_POLICY)

    assert declared.receives_restricted is True


def test_a_policy_entry_is_its_own_json(
    modelled: api.Azathoth,
) -> None:
    entry = modelled.portfolio.add(ALPHA.identifier, data_policy=RETAINING)

    assert api.PortfolioEntry.model_validate_json(entry.model_dump_json()) == entry
    assert entry.model_dump(mode="json")["data_policy"] == {
        "retains_data": "yes",
        "trains_on_data": "no",
    }


def test_who_declared_a_policy_and_when_is_listed(
    location: str,
) -> None:
    open_repositories(location).portfolio.save(
        ModelPortfolioEntry(provider=ALPHA.provider, model=ALPHA.model)
    )

    with api.Azathoth(open_repositories(location), directories=(), author="Eris") as instance:
        undeclared = instance.portfolio.list()[0]
        declared = instance.portfolio.set_data_policy(ALPHA.identifier, PRIVATE_DATA_POLICY)
        (listed,) = instance.portfolio.list()

    declaration = open_repositories(location).portfolio.policy_declaration(ALPHA.identifier)

    assert declaration is not None
    assert (undeclared.policy_declared_by, undeclared.policy_declared_at) == (None, None)
    assert declared.policy_declared_by == api.Author(name="Eris", email=None)
    assert declared.policy_declared_at == declaration.declared_at
    assert listed == declared


def test_a_model_authorized_with_a_policy_names_its_author_as_declaring_it(
    location: str,
) -> None:
    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory("provider-a", (ALPHA,)),),
        author="Eris",
    ) as instance:
        entry = instance.portfolio.add(ALPHA.identifier, data_policy=PRIVATE_DATA_POLICY)

    assert entry.policy_declared_by == api.Author(name="Eris", email=None)
    assert entry.policy_declared_at == entry.added_at
