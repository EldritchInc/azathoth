"""Tests that restricted data reaches an MCP client only through tools exposed for it (ADR 0123).

The operator declares that a tool's client may hold restricted data by
exposing it with `"sensitivity": "restricted"`. Its calls are labelled
restricted, so their prompts reach only models declared private, and a call
that cannot be served says why. A tool not so exposed returns no restricted
invocation.
"""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.jobs import JobStatus
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import (
    ContextPromptStrategySpec,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelPortfolioEntry
from azathoth.sensitivity import PRIVATE_DATA_POLICY, UNKNOWN_DATA_POLICY, Sensitivity
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp.access import STDIO_CALLER
from azathoth_mcp.catalog import ToolCatalog
from azathoth_mcp.exposure import ExposedWorkflow, ExposureDocument, parse_exposure
from azathoth_mcp.service import RestrictedInvocationError, ToolOutcome, ToolService
from tests.mcp.test_service import PRIMARY, instance_serving

CHART_ID = UUID("c4a70000-0000-4000-8000-000000000001")

STEP_ID = UUID("c4a70000-0000-4000-8000-000000000011")

CHART: JsonValue = {"chart": "Patient 412: stable."}


def chart_state() -> WorkflowProductionState:
    """Return the production state of a workflow whose one step shows its model the input."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=CHART_ID,
                name="summarize chart",
                description="Summarize a patient's chart.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=ContextPromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=UUID(int=STEP_ID.int + 1),
                            name="summarize",
                            description="Summarize the chart.",
                            version="1.0.0",
                        ),
                        template=PromptTemplate(
                            text="Summarize: {chart}",
                            bindings=(
                                PromptBinding(
                                    variable_name="chart",
                                    event_type="workflow.input.received",
                                    field_name="input",
                                ),
                            ),
                        ),
                        model_selection=PRIMARY,
                    ),
                ),
            ),
        ),
    )


class Server:
    """One server exposing the chart workflow as `summarize_chart`, labelled as given."""

    def __init__(
        self,
        database: Path,
        *,
        sensitivity: Sensitivity | None,
        private: bool,
    ) -> None:
        repositories = open_repositories(database)

        if repositories.production_states.get(CHART_ID) is None:
            repositories.production_states.set(chart_state())

        if repositories.portfolio.get(PRIMARY.identifier) is None:
            repositories.portfolio.save(
                ModelPortfolioEntry(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                    data_policy=PRIVATE_DATA_POLICY if private else UNKNOWN_DATA_POLICY,
                )
            )

        self.instance = instance_serving(database, PRIMARY)
        self.service = ToolService(
            catalog=ToolCatalog(
                ExposureDocument(
                    version=1,
                    tools=(
                        ExposedWorkflow(
                            workflow_id=CHART_ID,
                            name="summarize_chart",
                            description="Summarize a patient's chart.",
                            sensitivity=sensitivity,
                        ),
                    ),
                ),
                repositories.production_states,
            ),
            instance=self.instance,
            new_key=lambda: "generated-1",
        )

    def call(
        self,
        key: str = "chart-412",
    ) -> ToolOutcome:
        return asyncio.run(
            self.service.invoke(
                "summarize_chart",
                {"input": CHART, "idempotency_key": key},
                caller=STDIO_CALLER,
            )
        )


# Exposure


def test_a_tool_may_be_exposed_with_a_label() -> None:
    document = parse_exposure(
        json.dumps(
            {
                "version": 1,
                "tools": [
                    {
                        "workflow_id": str(CHART_ID),
                        "name": "summarize_chart",
                        "description": "Summarize a patient's chart.",
                        "sensitivity": "restricted",
                    }
                ],
            }
        )
    )

    (tool,) = document.tools

    assert tool.sensitivity is Sensitivity.RESTRICTED
    assert (
        ExposedWorkflow(
            workflow_id=CHART_ID,
            name="summarize_chart",
            description="Summarize.",
        ).sensitivity
        is None
    )


def test_an_unknown_label_is_refused() -> None:
    with pytest.raises(ValueError):
        ExposedWorkflow.model_validate(
            {
                "workflow_id": str(CHART_ID),
                "name": "summarize_chart",
                "description": "Summarize.",
                "sensitivity": "secret",
            }
        )


# Calls


def test_a_restricted_tools_call_is_restricted_and_answered_by_a_private_model(
    tmp_path: Path,
) -> None:
    server = Server(tmp_path / "azathoth.db", sensitivity=Sensitivity.RESTRICTED, private=True)

    outcome = server.call()

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.invocation_id is not None
    assert server.instance.invocations.get(outcome.invocation_id).sensitivity is (
        Sensitivity.RESTRICTED
    )

    evidence = server.service.get_invocation(
        {"invocation_id": str(outcome.invocation_id)},
        caller=STDIO_CALLER,
    )

    assert evidence.invocation_id == outcome.invocation_id


def test_a_restricted_tools_call_with_no_private_model_fails_and_says_why(
    tmp_path: Path,
) -> None:
    server = Server(tmp_path / "azathoth.db", sensitivity=Sensitivity.RESTRICTED, private=False)

    outcome = server.call()

    assert outcome.status is JobStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.message == (
        f"Step {STEP_ID} sent nothing. {PRIMARY.identifier} cannot receive restricted input: "
        "its portfolio entry does not say whether its provider retains data, and does not say "
        "whether it trains on data. If its provider neither retains nor trains on data, declare "
        f"that with `azathoth model policy {PRIMARY.identifier} --no-retention --no-training`; "
        "otherwise choose a model that may receive restricted input."
    )


def test_an_unlabelled_tools_call_is_internal_and_runs_on_any_model(
    tmp_path: Path,
) -> None:
    server = Server(tmp_path / "azathoth.db", sensitivity=None, private=False)

    outcome = server.call()

    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.invocation_id is not None
    assert server.instance.invocations.get(outcome.invocation_id).sensitivity is (
        Sensitivity.INTERNAL
    )


# Reading


def test_a_restricted_invocation_is_not_returned_through_a_tool_not_exposed_for_it(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"
    server = Server(database, sensitivity=None, private=True)

    made = server.instance.runs.invoke(
        CHART_ID,
        input=CHART,
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert made.invocation_id is not None

    with pytest.raises(RestrictedInvocationError) as caught:
        server.service.get_invocation(
            {"invocation_id": str(made.invocation_id)},
            caller=STDIO_CALLER,
        )

    assert str(caught.value) == (
        f"Invocation {made.invocation_id} is restricted, and the tool 'summarize_chart' is not "
        "exposed for restricted data, so its result is not returned. If this client may hold "
        'restricted data, the operator exposes the tool with "sensitivity": "restricted".'
    )

    restricted = Server(database, sensitivity=Sensitivity.RESTRICTED, private=True)

    assert (
        restricted.service.get_invocation(
            {"invocation_id": str(made.invocation_id)},
            caller=STDIO_CALLER,
        ).invocation_id
        == made.invocation_id
    )


def test_the_guide_quotes_the_refusals_exactly(
    tmp_path: Path,
) -> None:
    guide = (Path(__file__).parents[2] / "docs" / "mcp.md").read_text(encoding="utf-8")
    database = tmp_path / "azathoth.db"
    refused = Server(database, sensitivity=Sensitivity.RESTRICTED, private=False).call()
    made = Server(database, sensitivity=None, private=False).instance.runs.invoke(
        CHART_ID,
        input=CHART,
        sensitivity=api.Sensitivity.RESTRICTED,
    )

    assert refused.error is not None

    step = refused.error.message.replace(str(STEP_ID), "<STEP_ID>").replace(
        PRIMARY.identifier, "<MODEL>"
    )

    with pytest.raises(RestrictedInvocationError) as caught:
        Server(database, sensitivity=None, private=False).service.get_invocation(
            {"invocation_id": str(made.invocation_id)},
            caller=STDIO_CALLER,
        )

    read = str(caught.value).replace(str(made.invocation_id), "<INVOCATION_ID>")

    assert f"\n{step}\n" in guide
    assert f"\n{read}\n" in guide
