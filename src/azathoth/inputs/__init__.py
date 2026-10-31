"""External workflow inputs: inline values or references, with media types."""

from azathoth.inputs.media import (
    JSON_MEDIA_TYPE,
    MEDIA_TYPES_BY_EXTENSION,
    InputContentError,
    decode_content,
    infer_media_type,
    is_supported_media_type,
    is_text_media_type,
    validate_media_type,
)
from azathoth.inputs.source import (
    InlineInput,
    InputSourceError,
    ReferenceInput,
    WorkflowInputSource,
    decode_input_source,
)

__all__ = [
    "JSON_MEDIA_TYPE",
    "MEDIA_TYPES_BY_EXTENSION",
    "InlineInput",
    "InputContentError",
    "InputSourceError",
    "ReferenceInput",
    "WorkflowInputSource",
    "decode_content",
    "decode_input_source",
    "infer_media_type",
    "is_supported_media_type",
    "is_text_media_type",
    "validate_media_type",
]
