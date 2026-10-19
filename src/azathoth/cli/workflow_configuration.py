"""Workflow configuration commands for the Azathoth CLI."""

import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.prompting import (
    ContextPromptStrategySpec,
    PromptStrategySpec,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowDocumentError,
    WorkflowValueReference,
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

    print(f"Result: {_render_result(specification.result)}")

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
            (
                PromptStrategySpec,
                ContextPromptStrategySpec,
            ),
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
    """Import one durable workflow from a JSON document.

    Imported workflows must declare their result, the one value evaluation
    judges and production returns. Documents without one are rejected before
    anything is persisted.
    """

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

    if specification.result is None:
        print(
            "Workflow document must declare a result.",
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


def _step_type(
    specification: (PromptStrategySpec | ContextPromptStrategySpec | ToolStepSpecification),
) -> str:
    """Return the stable CLI name for one workflow step type."""

    if isinstance(
        specification,
        (
            PromptStrategySpec,
            ContextPromptStrategySpec,
        ),
    ):
        return "prompt"

    return "tool"


def _render_result(
    result: WorkflowValueReference | None,
) -> str:
    """Render one workflow's declared result reference."""

    if result is None:
        return "undeclared"

    return f"step {result.producer_step_id} output {result.name}"
