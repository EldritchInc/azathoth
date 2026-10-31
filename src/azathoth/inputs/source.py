"""Value-or-reference sources of workflow input (ADR 0096)."""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    JsonValue,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)

from azathoth.inputs.media import (
    JSON_MEDIA_TYPE,
    is_text_media_type,
    validate_media_type,
)

INLINE_INPUT_KEY = "value"

REFERENCE_INPUT_KEY = "uri"

MEDIA_TYPE_KEY = "media_type"

EXCLUSIVE_KEYS_MESSAGE = "An input source holds exactly one of 'value' and 'uri'."


class InputSourceError(ValueError):
    """Raised when data does not describe one valid workflow input source."""


class InlineInput(BaseModel):
    """An input that holds its content: `{"value": <JSON>, "media_type": ...}`.

    The media type defaults to JSON. A text media type requires a string.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    value: JsonValue
    media_type: str = JSON_MEDIA_TYPE

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    @model_validator(mode="after")
    def validate_text_value(
        self,
    ) -> "InlineInput":
        """Require a text input to hold a string."""

        if is_text_media_type(self.media_type) and not isinstance(self.value, str):
            raise ValueError(f"An inline {self.media_type} input must hold a string.")

        return self


class ReferenceInput(BaseModel):
    """An input that names its content: `{"uri": <URI>, "media_type": ...}`.

    The media type is required, because nothing else says how to decode the
    content. Which schemes may be resolved is decided where the input is
    received, not here.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    uri: str
    media_type: str

    @field_validator("uri")
    @classmethod
    def validate_uri(
        cls,
        uri: str,
    ) -> str:
        """Require an absolute URI with a scheme.

        A one-letter scheme is a Windows drive letter, not a scheme.
        """

        if len(urlsplit(uri).scheme) < 2:
            raise ValueError(
                f"Input reference {uri!r} must be a URI with a scheme, "
                "such as file:///path/to/file."
            )

        return uri

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    @property
    def scheme(
        self,
    ) -> str:
        """Return the URI's scheme in lowercase."""

        return urlsplit(self.uri).scheme.lower()


def _require_one_kind(
    data: object,
) -> object:
    """Refuse data holding both or neither of `value` and `uri`.

    Checked before the union is validated, so the message names the rule
    rather than a failed union member.
    """

    if isinstance(data, dict) and (INLINE_INPUT_KEY in data) == (REFERENCE_INPUT_KEY in data):
        raise ValueError(EXCLUSIVE_KEYS_MESSAGE)

    return data


def _source_kind(
    data: object,
) -> str | None:
    """Return which kind of source data describes, by its key."""

    if isinstance(data, InlineInput):
        return "inline"

    if isinstance(data, ReferenceInput):
        return "reference"

    if isinstance(data, dict):
        return "inline" if INLINE_INPUT_KEY in data else "reference"

    return None


WorkflowInputSource = Annotated[
    Annotated[
        Annotated[InlineInput, Tag("inline")] | Annotated[ReferenceInput, Tag("reference")],
        Discriminator(_source_kind),
    ],
    BeforeValidator(_require_one_kind),
]
"""An external workflow input: an inline value or a reference, by its key."""


def decode_input_source(
    data: JsonValue,
) -> InlineInput | ReferenceInput:
    """Decode one input source from JSON data.

    Raises:
        InputSourceError: The data is not an object, holds both or neither of
            `value` and `uri`, holds another key, or describes an invalid
            source.
    """

    if not isinstance(data, dict):
        raise InputSourceError("An input source must be a JSON object.")

    inline = INLINE_INPUT_KEY in data
    reference = REFERENCE_INPUT_KEY in data

    if inline == reference:
        raise InputSourceError(EXCLUSIVE_KEYS_MESSAGE)

    allowed = {INLINE_INPUT_KEY if inline else REFERENCE_INPUT_KEY, MEDIA_TYPE_KEY}
    extra = sorted(key for key in data if key not in allowed)

    if extra:
        raise InputSourceError(
            "An input source holds only 'value' or 'uri', and 'media_type'; "
            f"got {', '.join(repr(key) for key in extra)}."
        )

    model = InlineInput if inline else ReferenceInput

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise InputSourceError(_validation_message(exc)) from exc


def _validation_message(
    error: ValidationError,
) -> str:
    """Return the messages of one validation error, without pydantic's prefixes."""

    messages: list[str] = []

    for detail in error.errors(include_url=False):
        message = str(detail["msg"]).removeprefix("Value error, ")

        if detail["type"] == "missing":
            field = ".".join(str(part) for part in detail["loc"])
            message = f"Input reference is missing {field!r}."

        messages.append(message)

    return " ".join(messages)


__all__ = [
    "EXCLUSIVE_KEYS_MESSAGE",
    "INLINE_INPUT_KEY",
    "MEDIA_TYPE_KEY",
    "REFERENCE_INPUT_KEY",
    "InlineInput",
    "InputSourceError",
    "ReferenceInput",
    "WorkflowInputSource",
    "decode_input_source",
]
