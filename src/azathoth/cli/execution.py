"""Application services for executing configured workflows."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.inputs import (
    JSON_MEDIA_TYPE,
    InputProvenance,
    ResolvedInput,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunner,
    create_workflow_input_events,
)

CONFIGURED_RUN_PRODUCER = "azathoth.configured"


@dataclass(frozen=True)
class WorkflowRunInput:
    """The external input an operator supplied to one configured run.

    Wrapping the payload keeps a supplied JSON null distinct from no input at
    all: a run given null still receives a workflow input event. An input
    resolved from a reference keeps its provenance (ADR 0096).
    """

    payload: JsonValue
    provenance: InputProvenance | None = None

    @classmethod
    def from_resolved(
        cls,
        resolved: ResolvedInput,
    ) -> "WorkflowRunInput":
        """Return the run input of one resolved input."""

        return cls(
            payload=resolved.value,
            provenance=resolved.provenance,
        )


def configured_run_context(
    workflow_input: WorkflowRunInput | None,
) -> Context:
    """Return the initial context of one configured run.

    A run given input starts with one canonical workflow input event, exactly
    as benchmark cases and production invocations do, followed by its
    provenance when it was resolved from a reference. A run given no input
    starts with an empty context.
    """

    if workflow_input is None:
        return Context()

    provenance = workflow_input.provenance

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value=workflow_input.payload,
                media_type=provenance.media_type if provenance is not None else JSON_MEDIA_TYPE,
                provenance=provenance,
            ),
            producer=CONFIGURED_RUN_PRODUCER,
        )
    )


async def execute_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    context: Context | None = None,
    runner: WorkflowRunner | None = None,
) -> WorkflowRun:
    """Generate and execute one configured workflow.

    A step failure never escapes as an exception: the completed run is
    returned whether it succeeded or failed, so the caller can persist and
    render it as evidence.

    Raises:
        WorkflowNotConfiguredError: The workflow is not configured.
        WorkflowGenerationError: No executable candidate could be generated.
    """

    candidate = runtime.generate_workflow_candidate(workflow_id)

    workflow_runner = runner if runner is not None else WorkflowRunner()

    execution_context = context if context is not None else Context()

    return await workflow_runner.run_recording_failures(
        candidate,
        execution_context,
    )
