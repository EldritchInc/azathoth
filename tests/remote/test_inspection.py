"""Tests for what a remote tells a client it holds (ADR 0125)."""

import pytest
from pydantic import ValidationError

from azathoth.providers import ModelPortfolioEntry
from azathoth.remote import (
    CredentialsRequest,
    CredentialsResponse,
    Head,
    HeadsRequest,
    HeadsResponse,
    PortfolioRecord,
    PortfolioResponse,
    heads,
    held_lineages,
    missing_credentials,
    portfolio_records,
    production_digest,
)
from azathoth.revisions import Lineage, RevisionKind
from azathoth.sensitivity import PRIVATE_DATA_POLICY, UNKNOWN_DATA_POLICY, Sensitivity
from azathoth.workflows import WorkflowProductionState
from tests.remote.test_closure import (
    BENCHMARK,
    CHILD,
    COUNT,
    COUNT_2,
    PARENT,
    PARENT_ID,
    RUN,
    SUMMARIZE_STEP,
    Instance,
    child,
    specification,
    tool_step,
)
from tests.remote.test_pulling import with_benchmark
from tests.remote.test_receiving import local_with_history


def asked(
    instance: Instance,
    *lineages: Lineage,
) -> HeadsResponse:
    return heads(
        HeadsRequest(lineages=lineages),
        workflows=instance.workflows,
        tools=instance.tools,
        benchmarks=instance.benchmarks,
        production_states=instance.production_states,
    )


def digests(
    instance: Instance,
    lineage: Lineage,
) -> tuple[str, ...]:
    return tuple(record.revision_digest for record in instance.workflows.lineage(lineage.id))


# Heads


def test_a_head_is_the_latest_revisions_chain_and_number() -> None:
    held = local_with_history()

    assert asked(held, PARENT) == HeadsResponse(
        heads=(Head(lineage=PARENT, chain=digests(held, PARENT), number=2),)
    )


def test_a_forked_lineages_head_is_its_latest_revisions_own_chain() -> None:
    held = Instance()
    first = held.workflows.save_revision(child()).lineage
    held.workflows.save(specification(CHILD.id, tool_step(SUMMARIZE_STEP, "summarize", "2")))
    held.workflows.save(
        specification(CHILD.id, tool_step(SUMMARIZE_STEP, "summarize", "3")),
        based_on=first.revision_digest,
    )
    history = held.workflows.lineage(CHILD.id)

    (head,) = asked(held, CHILD).heads

    assert head.chain == (history[0].revision_digest, history[2].revision_digest)
    assert head.number == 3


def test_a_lineage_not_held_is_left_out_and_each_is_asked_once() -> None:
    held = local_with_history()

    assert [head.lineage for head in asked(held, BENCHMARK, PARENT, PARENT).heads] == [PARENT]


def test_asking_about_nothing_asks_about_everything_held() -> None:
    held = with_benchmark(local_with_history(), Sensitivity.PUBLIC)

    assert [head.lineage for head in asked(held).heads] == [
        CHILD,
        PARENT,
        COUNT,
        COUNT_2,
        RUN,
        BENCHMARK,
    ]
    assert list(
        held_lineages(workflows=held.workflows, tools=held.tools, benchmarks=held.benchmarks)
    ) == [CHILD, PARENT, COUNT, COUNT_2, RUN, BENCHMARK]


# Production


def promote(
    held: Instance,
    *,
    number: int | None,
) -> None:
    revision = held.workflows.revision(PARENT_ID, number or 1)

    assert revision is not None

    held.production_states.set(
        WorkflowProductionState(
            specification=revision.specification,
            specification_revision=number,
        )
    )


def test_a_workflow_in_production_names_the_revision_promoted() -> None:
    held = local_with_history()
    promote(held, number=1)

    (head,) = asked(held, PARENT).heads

    assert head.production_digest == digests(held, PARENT)[0]


def test_a_state_promoted_before_revisions_is_found_by_its_content() -> None:
    held = local_with_history()
    promote(held, number=None)

    assert (
        production_digest(
            PARENT,
            workflows=held.workflows,
            production_states=held.production_states,
        )
        == digests(held, PARENT)[0]
    )


def test_a_state_whose_revision_is_not_held_names_none() -> None:
    held = local_with_history()
    revision = held.workflows.revision(PARENT_ID, 2)

    assert revision is not None

    held.production_states.set(
        WorkflowProductionState(specification=revision.specification, specification_revision=9)
    )

    assert asked(held, PARENT).heads[0].production_digest is None

    held.production_states.set(
        WorkflowProductionState(
            specification=child().model_copy(update={"metadata": revision.specification.metadata})
        )
    )

    assert asked(held, PARENT).heads[0].production_digest is None


def test_only_a_workflow_is_in_production() -> None:
    held = local_with_history()
    promote(held, number=1)

    assert (
        production_digest(
            Lineage(kind=RevisionKind.TOOL, id=PARENT_ID, version="1.0.0"),
            workflows=held.workflows,
            production_states=held.production_states,
        )
        is None
    )

    (tool_head,) = asked(held, COUNT).heads

    assert tool_head.production_digest is None


# Portfolios


def test_a_portfolio_names_each_model_and_its_declared_policy() -> None:
    held = Instance()
    held.portfolio.save(ModelPortfolioEntry(provider="openrouter", model="example/frontier"))
    held.portfolio.save(
        ModelPortfolioEntry(
            provider="bedrock", model="example/private", data_policy=PRIVATE_DATA_POLICY
        )
    )

    assert portfolio_records(held.portfolio) == PortfolioResponse(
        entries=(
            PortfolioRecord(
                identifier="openrouter/example/frontier", data_policy=UNKNOWN_DATA_POLICY
            ),
            PortfolioRecord(identifier="bedrock/example/private", data_policy=PRIVATE_DATA_POLICY),
        )
    )
    assert portfolio_records(Instance().portfolio) == PortfolioResponse()


# Credentials


@pytest.mark.parametrize(
    ("names", "environ", "missing"),
    [
        (("SEARCH_TOKEN",), {"SEARCH_TOKEN": "s3cret"}, ()),
        (("SEARCH_TOKEN",), {}, ("SEARCH_TOKEN",)),
        (("SEARCH_TOKEN",), {"SEARCH_TOKEN": ""}, ("SEARCH_TOKEN",)),
        (("AWS_*",), {"AWS_REGION": "us-east-1"}, ()),
        (("AWS_*",), {"AWS": "x"}, ("AWS_*",)),
        (("B", "A", "B"), {}, ("B", "A")),
        (("search_token",), {"SEARCH_TOKEN": "s3cret"}, ("search_token",)),
    ],
    ids=["set", "unset", "empty", "wildcard", "wildcard-unset", "once-in-order", "case"],
)
def test_the_names_an_environment_does_not_set_are_missing(
    names: tuple[str, ...],
    environ: dict[str, str],
    missing: tuple[str, ...],
) -> None:
    assert missing_credentials(CredentialsRequest(names=names), environ) == CredentialsResponse(
        missing=missing
    )


def test_on_windows_names_match_in_any_case() -> None:
    assert (
        missing_credentials(
            CredentialsRequest(names=("search_token",)),
            {"SEARCH_TOKEN": "s3cret"},
            case_insensitive=True,
        )
        == CredentialsResponse()
    )


@pytest.mark.parametrize("name", ["", "1TOKEN", "TOKEN-NAME", "*", "AWS_**", "TOKEN NAME"])
def test_a_name_that_is_no_variable_or_grant_is_refused(
    name: str,
) -> None:
    with pytest.raises(ValidationError):
        CredentialsRequest(names=(name,))


def test_a_head_has_a_chain() -> None:
    with pytest.raises(ValidationError):
        Head(lineage=PARENT, chain=(), number=1)
