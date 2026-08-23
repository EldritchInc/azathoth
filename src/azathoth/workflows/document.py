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
    """Reconstruct one workflow specification from a JSON document."""

    try:
        return WorkflowSpecification.model_validate_json(document)
    except ValidationError as exc:
        raise WorkflowDocumentError(
            "Workflow document is not a valid WorkflowSpecification."
        ) from exc
