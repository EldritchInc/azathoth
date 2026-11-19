"""Contract tests for what promoting an experiment's winner would save (ADR 0131)."""

from datetime import UTC, datetime, timedelta

import pytest

from azathoth import api
from azathoth.context import Context
from azathoth.persistence.repositories import Repositories
from azathoth.workflows import ProductionInvocation
from tests.api.test_experiment_comparison import (
    CHEAPER_MODEL,
    keep_runs,
    production_on,
    stocked,
)
from tests.cli.test_experiment_rendering import (
    FIRST_EXPERIMENT_ID,
    WORKFLOW_ID,
)


@pytest.fixture
def repositories(
    location: str,
) -> Repositories:
    """Return the instance's repositories, holding the experiment."""

    return stocked(location)


def invoke(
    stored: Repositories,
    *,
    days_ago: float,
) -> None:
    """Record one production invocation of the workflow, `days_ago` days before now."""

    stored.invocations.save(
        ProductionInvocation(
            workflow_id=WORKFLOW_ID,
            initial_context=Context(),
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


def test_the_winner_saves_the_difference_per_run_and_its_share_of_the_baseline(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)

    savings = instance.experiments.compare(FIRST_EXPERIMENT_ID).savings

    assert savings is not None
    assert savings.cost_usd == pytest.approx(0.04)
    assert savings.cost_percent == pytest.approx(80.0)
    assert savings.latency_seconds == pytest.approx(2.5)
    assert savings.latency_percent == pytest.approx(50.0)


def test_a_winner_that_costs_more_saves_a_negative_amount(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories, winner_costs=(0.10, 0.10), winner_seconds=(6.0, 6.0))

    savings = instance.experiments.compare(FIRST_EXPERIMENT_ID).savings

    assert savings is not None
    assert savings.cost_usd == pytest.approx(-0.05)
    assert savings.cost_percent == pytest.approx(-100.0)
    assert savings.latency_seconds == pytest.approx(-1.0)


def test_an_unknown_cost_leaves_only_the_time_saved(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories, winner_costs=(None, 0.01))

    savings = instance.experiments.compare(FIRST_EXPERIMENT_ID).savings

    assert savings is not None
    assert (savings.cost_usd, savings.cost_percent) == (None, None)
    assert savings.latency_seconds == pytest.approx(2.5)


def test_nothing_compared_saves_nothing(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    repositories.production_states.set(production_on(CHEAPER_MODEL))
    invoke(repositories, days_ago=1)

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert (comparison.savings, comparison.projection) == (None, None)


def test_savings_are_projected_over_the_last_30_days_of_invocations(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)

    for days_ago in (1, 10, 29):
        invoke(repositories, days_ago=days_ago)
    invoke(repositories, days_ago=45)

    projection = instance.experiments.compare(FIRST_EXPERIMENT_ID).projection

    assert projection is not None
    assert (projection.window_days, projection.invocations) == (30, 3)
    assert projection.cost_usd == pytest.approx(0.12)
    assert projection.latency_seconds == pytest.approx(7.5)
    assert projection.since <= datetime.now(UTC) - timedelta(days=30) + timedelta(minutes=1)


def test_without_recent_invocations_nothing_is_projected(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep_runs(repositories)
    invoke(repositories, days_ago=45)

    comparison = instance.experiments.compare(FIRST_EXPERIMENT_ID)

    assert comparison.savings is not None
    assert comparison.projection is None
