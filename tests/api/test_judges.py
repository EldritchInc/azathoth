"""Contract tests for the semantic judge rotation through the service API (ADR 0129)."""

from collections.abc import Iterator

import pytest

from azathoth import api
from azathoth.evaluation import JudgeEntry
from azathoth.persistence.repositories import open_repositories
from tests.api.test_models import ALPHA, BETA, StaticDirectory, modelled, parses

__all__ = ["modelled"]

MISSING = "provider-x/example/missing"


@pytest.fixture
def unreachable(
    location: str,
) -> Iterator[api.Azathoth]:
    """Return an instance whose only provider cannot be asked, closed afterwards."""

    with api.Azathoth(
        open_repositories(location),
        directories=(StaticDirectory("provider-a", (ALPHA,), failure="Provider A is down."),),
    ) as instance:
        yield instance


def test_an_empty_rotation_lists_no_judges(
    modelled: api.Azathoth,
) -> None:
    assert modelled.judges.list() == ()


def test_an_authorized_served_model_is_appended_to_the_rotation(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    modelled.portfolio.add(BETA.identifier)

    added = modelled.judges.add(BETA.identifier)
    modelled.judges.add(ALPHA.identifier)

    assert added == api.JudgeSummary(
        identifier=BETA.identifier,
        provider="provider-b",
        model="example/beta",
        position=1,
        authorized=True,
        command="azathoth judge list",
    )
    assert [(judge.identifier, judge.position) for judge in modelled.judges.list()] == [
        (BETA.identifier, 1),
        (ALPHA.identifier, 2),
    ]
    assert parses(added.command)


def test_a_model_no_provider_serves_is_not_added(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as refused:
        modelled.judges.add(MISSING)

    assert str(refused.value) == f"Model {MISSING!r} is not currently available."
    assert modelled.judges.list() == ()


def test_a_model_the_portfolio_does_not_authorize_is_not_added(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.ModelNotAuthorizedError) as refused:
        modelled.judges.add(ALPHA.identifier)

    assert refused.value.code == "model_not_authorized"
    assert str(refused.value) == f"Model {ALPHA.identifier!r} is not authorized."
    assert modelled.judges.list() == ()


def test_a_judge_already_in_the_rotation_is_not_added_again(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    modelled.judges.add(ALPHA.identifier)

    with pytest.raises(api.ConflictError) as refused:
        modelled.judges.add(ALPHA.identifier)

    assert str(refused.value) == f"Judge {ALPHA.identifier!r} is already in the rotation."
    assert len(modelled.judges.list()) == 1


def test_a_judge_is_removed_and_the_rest_keep_their_order(
    modelled: api.Azathoth,
) -> None:
    modelled.portfolio.add(ALPHA.identifier)
    modelled.portfolio.add(BETA.identifier)
    modelled.judges.add(ALPHA.identifier)
    modelled.judges.add(BETA.identifier)

    removed = modelled.judges.remove(ALPHA.identifier)

    assert (removed.identifier, removed.position) == (ALPHA.identifier, 1)
    assert [(judge.identifier, judge.position) for judge in modelled.judges.list()] == [
        (BETA.identifier, 1),
    ]


def test_a_model_that_is_not_a_judge_is_not_removed(
    modelled: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as refused:
        modelled.judges.remove(ALPHA.identifier)

    assert str(refused.value) == f"Judge {ALPHA.identifier!r} is not in the rotation."


def test_listing_and_removing_reach_no_provider(
    unreachable: api.Azathoth,
    location: str,
) -> None:
    open_repositories(location).judges.add(JudgeEntry(provider="provider-a", model="example/alpha"))

    assert [judge.identifier for judge in unreachable.judges.list()] == [ALPHA.identifier]
    assert unreachable.judges.remove(ALPHA.identifier).identifier == ALPHA.identifier
    assert unreachable.judges.list() == ()


def test_a_judge_the_portfolio_no_longer_authorizes_is_listed_as_such(
    modelled: api.Azathoth,
    location: str,
) -> None:
    open_repositories(location).judges.add(JudgeEntry(provider="provider-a", model="example/alpha"))

    [judge] = modelled.judges.list()

    assert judge.authorized is False


def test_a_closed_instance_lists_no_judges(
    modelled: api.Azathoth,
) -> None:
    modelled.close()

    with pytest.raises(api.InstanceClosedError):
        modelled.judges.list()
