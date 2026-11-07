"""JSON document serialization for durable workflow specifications."""

from pydantic import ValidationError

from azathoth.workflows.models import WorkflowSpecification


class WorkflowDocumentError(ValueError):
    """Raised when a workflow document cannot be reconstructed."""


def encode_workflow_document(
    specification: WorkflowSpecification,
) -> str:
    """Serialize one workflow specification as a readable JSON document."""

    return specification.model_dump_json(indent=2)


def decode_workflow_document(
    document: str,
) -> WorkflowSpecification:
    """Reconstruct one workflow specification from a JSON document.

    A document refused for a reason the workflow states, such as a schema
    that is not a JSON Schema (ADR 0118), names that reason.

    Raises:
        WorkflowDocumentError: The document is not a valid workflow.
    """

    try:
        return WorkflowSpecification.model_validate_json(document)
    except ValidationError as exc:
        stated = next(
            (
                str(error["msg"]).removeprefix("Value error, ")
                for error in exc.errors()
                if error["type"] == "value_error"
            ),
            None,
        )

        raise WorkflowDocumentError(
            "Workflow document is not a valid WorkflowSpecification."
            + (f" {stated}" if stated is not None else "")
        ) from exc
