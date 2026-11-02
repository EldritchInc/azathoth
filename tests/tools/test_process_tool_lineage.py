"""Tests that a process tool receives its step's lineage, and only from the engine (ADR 0104)."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import (
    Context,
    LineageRun,
    LineageStep,
    StepLineage,
    decode_step_lineage,
    encode_step_lineage,
    running_step,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.tools import (
    LINEAGE_ENVIRONMENT_VARIABLE,
    MANAGED_ENVIRONMENT_VARIABLES,
    ProcessToolExecutor,
    ToolImplementation,
    process_tool_environment,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRunner,
)
from tests.tools.test_process_tool_environment import (
    POSIX_BASE,
    POSIX_ENVIRONMENT,
    WINDOWS_ENVIRONMENT,
    create_implementation,
    posix,
    windows,
)

WORKFLOW_ID = UUID("80000000-0000-4000-8000-000000000001")
STEP_ID = UUID("80000000-0000-4000-8000-000000000011")
STRATEGY_ID = UUID("80000000-0000-4000-8000-000000000021")

STEP = StepLineage(
    step=LineageStep(
        workflow_id=WORKFLOW_ID,
        run_id=UUID("80000000-0000-4000-8000-000000000002"),
        step_id=STEP_ID,
        attempt=1,
    ),
    depth=1,
    root=LineageRun(
        workflow_id=UUID("90000000-0000-4000-8000-000000000001"),
        run_id=UUID("90000000-0000-4000-8000-000000000002"),
    ),
)

ECHO_LINEAGE_SOURCE = """import json
import os

print(json.dumps({"lineage": os.environ.get("AZATHOTH_LINEAGE")}))
"""

STALE_LINEAGE = "a stale value from Azathoth's own environment"


def test_lineage_is_a_managed_variable() -> None:
    assert LINEAGE_ENVIRONMENT_VARIABLE == "AZATHOTH_LINEAGE"
    assert LINEAGE_ENVIRONMENT_VARIABLE in MANAGED_ENVIRONMENT_VARIABLES


def test_a_process_outside_a_step_sees_no_lineage() -> None:
    assert posix(create_implementation()) == POSIX_BASE


def test_a_process_sees_the_lineage_it_is_given() -> None:
    environment = process_tool_environment(
        create_implementation(),
        POSIX_ENVIRONMENT,
        windows=False,
        lineage=STEP,
    )

    assert environment == {**POSIX_BASE, LINEAGE_ENVIRONMENT_VARIABLE: encode_step_lineage(STEP)}
    assert decode_step_lineage(environment[LINEAGE_ENVIRONMENT_VARIABLE]) == STEP


def test_a_process_in_a_running_step_sees_that_steps_lineage() -> None:
    with running_step(STEP):
        environment = posix(create_implementation())

    assert decode_step_lineage(environment[LINEAGE_ENVIRONMENT_VARIABLE]) == STEP


def test_lineage_in_azathoths_own_environment_never_reaches_a_tool() -> None:
    environ = {**POSIX_ENVIRONMENT, LINEAGE_ENVIRONMENT_VARIABLE: STALE_LINEAGE}

    assert LINEAGE_ENVIRONMENT_VARIABLE not in posix(create_implementation(), environ)
    assert LINEAGE_ENVIRONMENT_VARIABLE not in posix(
        create_implementation(environment=("AZATHOTH_*",)),
        environ,
    )


def test_a_running_step_replaces_the_lineage_azathoth_was_started_with() -> None:
    environ = {**POSIX_ENVIRONMENT, LINEAGE_ENVIRONMENT_VARIABLE: STALE_LINEAGE}

    with running_step(STEP):
        environment = posix(create_implementation(environment=("AZATHOTH_*",)), environ)

    assert environment[LINEAGE_ENVIRONMENT_VARIABLE] == encode_step_lineage(STEP)


def test_lineage_in_any_case_never_reaches_a_tool_on_windows() -> None:
    environ = {**WINDOWS_ENVIRONMENT, "Azathoth_Lineage": STALE_LINEAGE}

    environment = windows(create_implementation(environment=("AZATHOTH_*",)), environ)

    assert not any(name.upper() == LINEAGE_ENVIRONMENT_VARIABLE for name in environment)


GRANT_REFUSAL = "AZATHOTH_LINEAGE is set by the engine from the running step and cannot be granted."

TOOLS_README = Path(__file__).parents[2] / "src" / "azathoth" / "tools" / "README.md"


def test_lineage_cannot_be_granted() -> None:
    with pytest.raises(ValidationError) as error:
        create_implementation(environment=(LINEAGE_ENVIRONMENT_VARIABLE,))

    assert GRANT_REFUSAL in str(error.value)


def test_the_tools_readme_quotes_the_real_grant_refusal() -> None:
    assert f"```text\n{GRANT_REFUSAL}\n```" in TOOLS_README.read_text(encoding="utf-8")


def run_echo(
    implementation: ToolImplementation,
) -> StepLineage | None:
    """Run the echo implementation and return the lineage the process saw."""

    output = asyncio.run(ProcessToolExecutor().execute(implementation, {}))
    value = output["lineage"]

    if value is None:
        return None

    assert isinstance(value, str)

    return decode_step_lineage(value)


def test_a_real_process_outside_a_step_sees_no_lineage() -> None:
    assert run_echo(create_implementation(source=ECHO_LINEAGE_SOURCE)) is None


def test_a_real_process_in_a_running_step_sees_its_lineage() -> None:
    async def execute() -> dict[str, object]:
        with running_step(STEP):
            return dict(
                await ProcessToolExecutor().execute(
                    create_implementation(source=ECHO_LINEAGE_SOURCE),
                    {},
                )
            )

    output = asyncio.run(execute())
    value = output["lineage"]

    assert isinstance(value, str)
    assert decode_step_lineage(value) == STEP


class ProcessToolStep:
    """A step that runs the echo process tool and outputs the lineage it saw."""

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return StrategyMetadata(
            id=STRATEGY_ID,
            name="Echo lineage",
            description="Run a process tool that reports its lineage.",
            version="1.0.0",
        )

    async def run(self, context: Context) -> StrategyOutcome:
        """Run the tool inside the step."""

        output = await ProcessToolExecutor().execute(
            create_implementation(source=ECHO_LINEAGE_SOURCE),
            {},
        )

        return StrategyOutcome(output=json.dumps(output))


def test_a_process_tool_run_by_a_workflow_step_sees_that_step_of_that_run() -> None:
    run = asyncio.run(
        WorkflowRunner().run(
            workflow=WorkflowCandidate(
                metadata=WorkflowMetadata(
                    id=WORKFLOW_ID,
                    name="Echo lineage",
                    description="Run one process tool.",
                    version="1.0.0",
                ),
                steps=(WorkflowCandidateStep(id=STEP_ID, strategy=ProcessToolStep()),),
            ),
            context=Context(),
        )
    )

    execution = run.steps[0].execution

    assert execution is not None
    assert isinstance(execution.output, str)

    value = json.loads(execution.output)["lineage"]

    assert decode_step_lineage(value) == StepLineage(
        step=LineageStep(workflow_id=WORKFLOW_ID, run_id=run.id, step_id=STEP_ID, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=run.id),
    )
