"""Workflow commands for the Azathoth command-line application."""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.execution import execute_configured_workflow
from azathoth.cli.optimization import optimize_configured_workflow
from azathoth.cli.rendering import (
    render_workflow_optimization_session,
    render_workflow_run,
)
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import PromptStrategySpec
from azathoth.runtime import WorkflowNotConfiguredError
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowDocumentError,
    WorkflowGenerationError,
    WorkflowScoringPolicy,
    decode_workflow_document,
)


def list_workflows() -> int:
    """List configured durable workflows."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    for specification in runtime.workflows.specifications:
        metadata = specification.metadata

        print(f"{metadata.id}  {metadata.version}  {metadata.name}")

    return 0


def show_workflow(
    workflow_id: UUID,
) -> int:
    """Show one configured durable workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    specification = runtime.workflows.get(workflow_id)

    if specification is None:
        print(
            f"Workflow {workflow_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    metadata = specification.metadata

    print(f"ID: {metadata.id}")

    print(f"Name: {metadata.name}")

    print(f"Version: {metadata.version}")

    print(f"Description: {metadata.description}")

    print(f"Steps: {len(specification.steps)}")

    for index, step in enumerate(
        specification.steps,
        start=1,
    ):
        print()
        print(f"Step {index}")
        print(f"ID: {step.id}")
        print(f"Type: {_step_type(step.specification)}")

        if isinstance(
            step.specification,
            PromptStrategySpec,
        ):
            print(f"Strategy: {step.specification.metadata.name}")

        elif isinstance(
            step.specification,
            ToolStepSpecification,
        ):
            print(f"Tool: {step.specification.requirement.name}")

            if step.specification.requirement.version is not None:
                print(f"Tool Version: {step.specification.requirement.version}")

        print(f"Dependencies: {len(step.depends_on)}")

        print(f"Inputs: {len(step.inputs)}")

        print(f"Outputs: {len(step.outputs)}")

        print(f"Conditions: {len(step.conditions)}")

    return 0


def import_workflow(
    document_path: Path,
) -> int:
    """Import one durable workflow from a JSON document."""

    try:
        document = document_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"Unable to read workflow document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    try:
        specification = decode_workflow_document(document)
    except WorkflowDocumentError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteWorkflowRepository(configuration.database)

    try:
        repository.save(specification)
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Imported workflow {specification.metadata.id}.")

    return 0


def run_workflow(
    workflow_id: UUID,
) -> int:
    """Execute one configured workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    try:
        run = asyncio.run(
            execute_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(render_workflow_run(run))

    return 0 if run.succeeded else 1


def optimize_workflow(
    *,
    workflow_id: UUID,
    expected_value: JsonValue,
    target_latency_seconds: float,
    target_cost_usd: float,
    generations: int,
) -> int:
    """Empirically optimize one configured workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    try:
        session = asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                expected_outcome=ExpectedOutcome(
                    description="Match the operator-supplied expected value.",
                    value=expected_value,
                    comparison=OutcomeComparison.EXACT,
                ),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=target_latency_seconds,
                    target_cost_usd=target_cost_usd,
                ),
                max_generations=generations,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        ValueError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_optimization_session(
            session,
        )
    )

    return 0


def _step_type(
    specification: PromptStrategySpec | ToolStepSpecification,
) -> str:
    """Return the stable CLI name for one workflow step type."""

    if isinstance(
        specification,
        PromptStrategySpec,
    ):
        return "prompt"

    return "tool"
