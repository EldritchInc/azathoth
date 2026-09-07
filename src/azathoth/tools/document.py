"""Portable JSON documents for durable tool artifacts."""

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    model_validator,
)

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.testing import ToolTestCase


class ToolDocumentError(ValueError):
    """Raised when a portable tool document cannot be reconstructed."""


class ToolDocument(BaseModel):
    """Bundle one exact tool definition with its durable supporting artifacts."""

    model_config = ConfigDict(frozen=True)

    definition: ToolDefinition
    implementations: tuple[ToolImplementation, ...] = ()
    test_cases: tuple[ToolTestCase, ...] = ()

    @model_validator(mode="after")
    def validate_artifact_relationships(self) -> "ToolDocument":
        """Require bundled artifacts to belong to the bundled definition."""

        for implementation in self.implementations:
            if implementation.tool_id != self.definition.id:
                raise ValueError(
                    "Tool document implementation "
                    f"{implementation.id} belongs to tool "
                    f"{implementation.tool_id}, not "
                    f"{self.definition.id}."
                )

            if implementation.tool_version != self.definition.version:
                raise ValueError(
                    "Tool document implementation "
                    f"{implementation.id} targets tool version "
                    f"{implementation.tool_version}, not "
                    f"{self.definition.version}."
                )

        for test_case in self.test_cases:
            if test_case.tool_id != self.definition.id:
                raise ValueError(
                    "Tool document test case "
                    f"{test_case.id} belongs to tool "
                    f"{test_case.tool_id}, not "
                    f"{self.definition.id}."
                )

        return self


def encode_tool_document(
    document: ToolDocument,
) -> str:
    """Serialize one portable tool document as readable JSON."""

    return document.model_dump_json(
        indent=2,
    )


def decode_tool_document(
    document: str,
) -> ToolDocument:
    """Reconstruct one portable tool document from JSON."""

    try:
        return ToolDocument.model_validate_json(
            document,
        )
    except ValidationError as exc:
        raise ToolDocumentError("Tool document is not valid.") from exc
