"""Workflow commands for the Azathoth command-line application."""

import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.prompting import PromptStrategySpec
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowDocumentError,
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
