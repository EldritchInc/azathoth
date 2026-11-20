"""Contract tests for where a model or a tool is used (ADR 0133)."""

import pytest

from azathoth import api
from azathoth.persistence.repositories import Repositories, open_repositories
from azathoth.strategies import StrategyResourceBinding
from azathoth.workflows import WorkflowProductionState
from tests.cli.test_usage_commands import (
    IMPLEMENTATION_ID,
    MODEL_IDENTIFIER,
    PROMPT_WORKFLOW_ID,
    RUN_ID,
    STARTED_AT,
    STEP_ID,
    TOOL_ID,
    TOOL_NAME,
    TOOL_WORKFLOW_ID,
    UNKNOWN_TOOL_ID,
    UNUSED_MODEL_IDENTIFIER,
    create_definition,
    create_prompt_workflow,
    create_run,
    create_tool_workflow,
)


@pytest.fixture
def repositories(location: str) -> Repositories:
    """Return the instance's repositories."""

    return open_repositories(location)


def model_in_use(stored: Repositories) -> None:
    """Configure, promote and run the prompt workflow on the model."""

    workflow = create_prompt_workflow()
    stored.workflows.save(workflow)
    stored.production_states.set(WorkflowProductionState(specification=workflow))
    stored.runs.save(
        create_run(
            workflow=workflow.metadata,
            resource=StrategyResourceBinding(kind="model", identifier=MODEL_IDENTIFIER),
        )
    )


def tool_in_use(stored: Repositories) -> None:
    """Define the tool, and configure, promote and run the workflow that requires it."""

    workflow = create_tool_workflow()
    stored.tools.save_definition(create_definition())
    stored.workflows.save(workflow)
    stored.production_states.set(WorkflowProductionState(specification=workflow))
    stored.runs.save(
        create_run(
            workflow=workflow.metadata,
            resource=StrategyResourceBinding(
                kind="tool",
                identifier=str(IMPLEMENTATION_ID),
                attributes={"tool_id": str(TOOL_ID), "tool_version": "1.0.0", "runtime": "python"},
            ),
        )
    )


#
# Models
#


def test_a_model_is_said_to_be_configured_in_production_and_in_run_history(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    model_in_use(repositories)

    usage = instance.models.usage(MODEL_IDENTIFIER)

    assert isinstance(usage, api.ModelUsage)
    assert usage.identifier == MODEL_IDENTIFIER
    assert usage.in_production
    (workflow,) = usage.workflows
    assert (workflow.workflow_id, workflow.configured) == (PROMPT_WORKFLOW_ID, True)
    assert workflow.production == (api.ProductionStepUsage(step_id=STEP_ID, role="primary"),)
    (run,) = workflow.runs
    assert (run.run_id, run.started_at) == (RUN_ID, STARTED_AT)
    assert run.steps == (api.StepAttemptUsage(step_id=STEP_ID, attempt_number=1),)


def test_an_unused_model_is_used_nowhere_and_is_not_an_error(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    repositories.workflows.save(create_prompt_workflow())

    usage = instance.models.usage(UNUSED_MODEL_IDENTIFIER)

    assert usage.workflows == ()
    assert not usage.in_production


#
# Tools
#


def test_a_tool_is_said_to_be_configured_in_production_and_in_run_history(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    tool_in_use(repositories)

    usage = instance.tools.usage(TOOL_ID)

    assert isinstance(usage, api.ToolUsage)
    assert usage.tool_names == (TOOL_NAME,)
    assert usage.in_production
    (workflow,) = usage.workflows
    assert (workflow.workflow_id, workflow.configured, workflow.production) == (
        TOOL_WORKFLOW_ID,
        True,
        True,
    )
    (run,) = workflow.runs
    assert run.executions == (
        api.ToolExecutionUsage(
            step_id=STEP_ID,
            attempt_number=1,
            implementation_id=IMPLEMENTATION_ID,
            tool_version="1.0.0",
            runtime="python",
        ),
    )


def test_a_defined_tool_nothing_uses_is_used_nowhere(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    repositories.tools.save_definition(create_definition())

    usage = instance.tools.usage(TOOL_ID)

    assert usage.tool_names == (TOOL_NAME,)
    assert usage.workflows == ()


def test_a_tool_nothing_defines_and_no_run_executed_is_not_found(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    repositories.tools.save_definition(create_definition())

    with pytest.raises(api.NotFoundError, match=f"Tool {UNKNOWN_TOOL_ID} is not configured."):
        instance.tools.usage(UNKNOWN_TOOL_ID)


def test_a_models_usage_is_its_own_json(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    model_in_use(repositories)

    usage = instance.models.usage(MODEL_IDENTIFIER)

    assert api.ModelUsage.model_validate_json(usage.model_dump_json()) == usage


def test_a_tools_usage_is_its_own_json(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    tool_in_use(repositories)

    usage = instance.tools.usage(TOOL_ID)

    assert api.ToolUsage.model_validate_json(usage.model_dump_json()) == usage
