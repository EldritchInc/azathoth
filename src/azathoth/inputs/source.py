"""Value-or-reference sources of workflow input (ADR 0096, ADR 0112)."""

import re
from typing import Annotated, Final, cast
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    Tag,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from azathoth.inputs.media import (
    JSON_MEDIA_TYPE,
    is_binary_media_type,
    is_text_media_type,
    validate_media_type,
)

INLINE_INPUT_KEY = "value"

REFERENCE_INPUT_KEY = "uri"

MEDIA_TYPE_KEY = "media_type"

ORIGIN_KEY = "origin"

EXCLUSIVE_KEYS_MESSAGE = "An input source holds exactly one of 'value' and 'uri'."

ORIGIN_ON_REFERENCE_MESSAGE: Final = (
    "A reference is its own origin; 'origin' is given only with an inline 'value'."
)
"""What a reference that also names an origin is refused with."""

MAX_ORIGIN_URI_LENGTH: Final = 2048
"""The longest URI an origin may hold."""

S3_ORIGIN_SCHEME: Final = "s3"
"""The one scheme whose origins may name an object version and ETag."""

STANDARD_BASE64: Final = re.compile(
    r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?",
)
"""Standard base64 (RFC 4648), padded, with no whitespace; matched whole."""


class InputSourceError(ValueError):
    """Raised when data does not describe one valid workflow input source."""


class InputOrigin(BaseModel):
    """Where an inline input's content durably lives, as its sender names it.

    The URI is recorded as given and never read. Only an `s3://` origin may
    name the object version and ETag the content was taken from.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    uri: str
    version_id: str | None = Field(default=None, min_length=1)
    etag: str | None = Field(default=None, min_length=1)

    @field_validator("uri")
    @classmethod
    def validate_uri(
        cls,
        uri: str,
    ) -> str:
        """Require an absolute URI with a scheme, no fragment, and a bounded length.

        A one-letter scheme is a Windows drive letter, not a scheme.
        """

        if len(uri) > MAX_ORIGIN_URI_LENGTH:
            raise ValueError(
                f"An origin URI holds at most {MAX_ORIGIN_URI_LENGTH} characters; got {len(uri)}."
            )

        parts = urlsplit(uri)

        if len(parts.scheme) < 2:
            raise ValueError(
                f"An origin {uri!r} must be a URI with a scheme, such as s3://bucket/key."
            )

        if parts.fragment or "#" in uri:
            raise ValueError(f"An origin {uri!r} names a whole object, with no fragment.")

        return uri

    @model_validator(mode="after")
    def validate_version(
        self,
    ) -> "InputOrigin":
        """Allow a version ID and an ETag only on an `s3://` origin."""

        versioned = self.version_id is not None or self.etag is not None

        if versioned and urlsplit(self.uri).scheme.lower() != S3_ORIGIN_SCHEME:
            raise ValueError(
                "An origin's version_id and etag name an S3 object version; "
                f"{self.uri!r} is not an s3:// URI."
            )

        return self

    @model_serializer(mode="wrap")
    def omit_absent_version(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out a version ID and an ETag the origin does not name."""

        data = cast(dict[str, JsonValue], handler(self))

        return {key: value for key, value in data.items() if value is not None}


class InlineInput(BaseModel):
    """An input that holds its content: `{"value": <JSON>, "media_type": ...}`.

    The media type defaults to JSON. A text media type requires a string. A
    binary media type requires its content as a standard, padded base64
    string, decoded only when the input is resolved, within its policy's
    cap. Any inline input may name its `origin` (ADR 0112).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    value: JsonValue
    media_type: str = JSON_MEDIA_TYPE
    origin: InputOrigin | None = None

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    @model_validator(mode="after")
    def validate_value(
        self,
    ) -> "InlineInput":
        """Require a text input to hold a string, and a binary one base64."""

        if is_binary_media_type(self.media_type):
            if not isinstance(self.value, str):
                raise ValueError(
                    f"An inline {self.media_type} input must hold its content as a base64 string."
                )

            if STANDARD_BASE64.fullmatch(self.value) is None:
                raise ValueError(
                    f"An inline {self.media_type} input must hold standard base64, padded, "
                    "with no whitespace."
                )

        elif is_text_media_type(self.media_type) and not isinstance(self.value, str):
            raise ValueError(f"An inline {self.media_type} input must hold a string.")

        return self

    @model_serializer(mode="wrap")
    def omit_absent_origin(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out an origin the input does not name.

        A request without an origin then dumps, and digests (ADR 0097), exactly
        as it did before inputs could name one.
        """

        data = cast(dict[str, JsonValue], handler(self))

        if self.origin is None:
            data.pop(ORIGIN_KEY, None)

        return data


class ReferenceInput(BaseModel):
    """An input that names its content: `{"uri": <URI>, "media_type": ...}`.

    The media type is required, because nothing else says how to decode the
    content. Which schemes may be resolved is decided where the input is
    received, not here. A reference is its own origin, so it names none.
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
    """Refuse data holding both or neither of `value` and `uri`, or a reference's origin.

    Checked before the union is validated, so the message names the rule
    rather than a failed union member.
    """

    if isinstance(data, dict):
        if (INLINE_INPUT_KEY in data) == (REFERENCE_INPUT_KEY in data):
            raise ValueError(EXCLUSIVE_KEYS_MESSAGE)

        if REFERENCE_INPUT_KEY in data and ORIGIN_KEY in data:
            raise ValueError(ORIGIN_ON_REFERENCE_MESSAGE)

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
            `value` and `uri`, is a reference naming an origin, holds another
            key, or describes an invalid source.
    """

    if not isinstance(data, dict):
        raise InputSourceError("An input source must be a JSON object.")

    inline = INLINE_INPUT_KEY in data
    reference = REFERENCE_INPUT_KEY in data

    if inline == reference:
        raise InputSourceError(EXCLUSIVE_KEYS_MESSAGE)

    if reference and ORIGIN_KEY in data:
        raise InputSourceError(ORIGIN_ON_REFERENCE_MESSAGE)

    allowed = (
        {INLINE_INPUT_KEY, MEDIA_TYPE_KEY, ORIGIN_KEY}
        if inline
        else {REFERENCE_INPUT_KEY, MEDIA_TYPE_KEY}
    )
    extra = sorted(key for key in data if key not in allowed)

    if extra:
        raise InputSourceError(
            "An input source holds only 'value', 'media_type' and 'origin', or 'uri' and "
            f"'media_type'; got {', '.join(repr(key) for key in extra)}."
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
    "MAX_ORIGIN_URI_LENGTH",
    "MEDIA_TYPE_KEY",
    "ORIGIN_KEY",
    "ORIGIN_ON_REFERENCE_MESSAGE",
    "REFERENCE_INPUT_KEY",
    "STANDARD_BASE64",
    "InlineInput",
    "InputOrigin",
    "InputSourceError",
    "ReferenceInput",
    "WorkflowInputSource",
    "decode_input_source",
]
