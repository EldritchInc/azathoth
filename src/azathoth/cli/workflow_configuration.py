"""Workflow configuration commands for the Azathoth CLI."""

import json
import sys
from pathlib import Path
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.service import (
    author_note,
    history_line,
    identical_note,
    import_note,
    revision_lineage_lines,
    service_instance,
)
from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    PromptSpecification,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowResultReference,
    decode_workflow_document,
    describe_value_reference,
)


def list_workflows() -> int:
    """List every imported workflow at its latest revision, through `workflows.list` (ADR 0140).

    Only durable state is read, so no provider is asked anything.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        workflows = service_instance(configuration).workflows.list()
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    for workflow in workflows:
        print(f"{workflow.id}  {workflow.version}  {workflow.name}")

    return 0


def show_workflow(
    workflow_id: UUID,
    *,
    revision: int | None = None,
) -> int:
    """Show one imported revision of a durable workflow, the latest by default.

    A workflow that declares an input or output schema shows it after its
    result (ADR 0118). Only durable state is read, through `workflows.get`
    (ADR 0140), so no provider credentials are needed.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        selected = service_instance(configuration).workflows.get(workflow_id, revision=revision)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    specification = decode_workflow_document(json.dumps(selected.document))

    metadata = specification.metadata

    print(f"ID: {metadata.id}")

    print(f"Revision: {selected.revision.number} of {selected.latest_number}")

    imported = selected.revision.imported_at

    print(f"Imported: {imported.isoformat() if imported is not None else 'unknown'}")

    print(f"Content Digest: {selected.revision.content_digest}")

    for line in revision_lineage_lines(selected.revision):
        print(line)

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

    The document is exactly what `workflow import` accepts. Importing the
    latest revision's export again appends nothing; importing an earlier
    one's reverts to it (ADR 0122). Only durable state is read, through
    `workflows.export` (ADR 0133).
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        exported = service_instance(configuration).workflows.export(workflow_id, revision=revision)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    sys.stdout.write(exported.text)

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
        print(
            f"{history_line(entry)}  {entry.version}  {entry.name}{identical_note(entry)}"
            f"{author_note(entry)}"
        )

    return 0


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
    except (api.InvalidDocumentError, api.InvalidAuthorError) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    workflow = imported.workflow

    if not imported.created:
        print(f"Workflow {workflow.id} is unchanged at revision {workflow.revision.number}.")

        return 0

    print(
        f"Imported workflow {workflow.id} revision {workflow.revision.number}"
        f"{import_note(workflow)}."
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
