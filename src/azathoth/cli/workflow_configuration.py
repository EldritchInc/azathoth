"""Workflow configuration commands for the Azathoth CLI."""

import sys
from pathlib import Path
from uuid import UUID

from azathoth import api
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.service import history_line, identical_note, import_note, service_instance
from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    PromptSpecification,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowRepository,
    WorkflowResultReference,
    WorkflowSpecificationRevision,
    describe_value_reference,
    encode_workflow_document,
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
    *,
    revision: int | None = None,
) -> int:
    """Show one imported revision of a durable workflow, the latest by default.

    A workflow that declares an input or output schema shows it after its
    result (ADR 0118). Only durable state is read, so no provider
    credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    repository = repositories(configuration).workflows

    selected = _selected_revision(
        repository,
        workflow_id,
        revision,
    )

    if selected is None:
        return 1

    latest = repository.latest_revision(workflow_id)

    specification = selected.specification

    metadata = specification.metadata

    print(f"ID: {metadata.id}")

    print(f"Revision: {selected.number} of {latest.number if latest is not None else '?'}")

    print(f"Imported: {_render_imported_at(selected)}")

    print(f"Content Digest: {selected.content_digest}")

    print(f"Name: {metadata.name}")

    print(f"Version: {metadata.version}")

    print(f"Description: {metadata.description}")

    print(f"Result: {_render_result(specification.result)}")

    for label, schema in (
        ("Input Schema", specification.input_schema),
        ("Output Schema", specification.output_schema),
    ):
        if schema is not None:
            print(f"{label}:")
            print(render_json_value(schema))

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
            PROMPT_SPECIFICATIONS,
        ):
            print(f"Strategy: {step.specification.metadata.name}")

        elif isinstance(
            step.specification,
            ToolStepSpecification,
        ):
            print(f"Tool: {step.specification.requirement.name}")

            if step.specification.requirement.version is not None:
                print(f"Tool Version: {step.specification.requirement.version}")

        if step.message is not None:
            print(f"Message: {step.message}")

        if step.emit_values:
            print("Emits values: yes")

        if step.confidence is not None:
            print(f"Confidence Output: {step.confidence}")

        print(f"Dependencies: {len(step.depends_on)}")

        print(f"Inputs: {len(step.inputs)}")

        print(f"Outputs: {len(step.outputs)}")

        print(f"Conditions: {len(step.conditions)}")

    return 0


def export_workflow(
    workflow_id: UUID,
    *,
    revision: int | None = None,
) -> int:
    """Print one imported revision of a workflow as an importable JSON document.

    The document is exactly what `workflow import` accepts, so exporting a
    revision and importing it again appends a revision with identical
    content. Only durable state is read.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    selected = _selected_revision(
        repositories(configuration).workflows,
        workflow_id,
        revision,
    )

    if selected is None:
        return 1

    print(encode_workflow_document(selected.specification))

    return 0


def list_workflow_history(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List the imported revisions of one workflow, newest first.

    Each line contains the revision number, import time, the first twelve
    characters of the content digest, the declared version, and the name.
    A revision with the same content as an earlier one names the earliest
    such revision, so reverts are visible. Only durable state is read,
    through the service API (ADR 0120).
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        history = service_instance(configuration).workflows.history(workflow_id, limit=limit)
    except api.NotFoundError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    for entry in history:
        print(f"{history_line(entry)}  {entry.version}  {entry.name}{identical_note(entry)}")

    return 0


def _selected_revision(
    repository: WorkflowRepository,
    workflow_id: UUID,
    revision: int | None,
) -> WorkflowSpecificationRevision | None:
    """Return the requested revision, printing the failure when there is none."""

    if repository.latest_revision(workflow_id) is None:
        print(
            f"Workflow {workflow_id} is not configured.",
            file=sys.stderr,
        )

        return None

    if revision is None:
        return repository.latest_revision(workflow_id)

    selected = repository.revision(
        workflow_id,
        revision,
    )

    if selected is None:
        print(
            f"Workflow {workflow_id} has no revision {revision}.",
            file=sys.stderr,
        )

    return selected


def _render_imported_at(
    revision: WorkflowSpecificationRevision,
) -> str:
    """Render when one revision was imported, or that it is unknown."""

    if revision.imported_at is None:
        return "unknown"

    return revision.imported_at.isoformat()


def import_workflow(
    document_path: Path,
) -> int:
    """Import one durable workflow from a JSON document.

    Imported workflows must declare their result, the one value evaluation
    judges and production returns. Documents without one are rejected before
    anything is persisted.

    Importing never replaces anything: each import appends the next revision
    under the document's workflow ID. Re-importing earlier content, for
    example to revert a change, is reported as identical to the earliest
    revision with the same content.
    """

    try:
        document = document_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"Unable to read workflow document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        imported = service_instance(configuration).workflows.import_document(document)
    except api.InvalidDocumentError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        f"Imported workflow {imported.id} revision {imported.revision.number}"
        f"{import_note(imported)}."
    )

    return 0


def _step_type(
    specification: PromptSpecification | ToolStepSpecification,
) -> str:
    """Return the stable CLI name for one workflow step type."""

    if isinstance(
        specification,
        PROMPT_SPECIFICATIONS,
    ):
        return "prompt"

    return "tool"


def _render_result(
    result: WorkflowResultReference | None,
) -> str:
    """Render one workflow's declared result reference."""

    if result is None:
        return "undeclared"

    return describe_value_reference(result)
