"""Resolving input references at the edge, before a run (ADR 0096, ADR 0112)."""

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, cast, runtime_checkable
from urllib.parse import urlsplit
from urllib.request import url2pathname

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.inputs.content import ContentRef
from azathoth.inputs.media import (
    InputContentError,
    check_binary_signature,
    decode_content,
    is_binary_media_type,
    is_text_media_type,
)
from azathoth.inputs.source import (
    InlineInput,
    InputOrigin,
    ReferenceInput,
)
from azathoth.inputs.store import ContentStore
from azathoth.revisions import CONTENT_DIGEST_PATTERN
from azathoth.sensitivity import Sensitivity

DEFAULT_MAX_INPUT_BYTES = 10 * 1024 * 1024

FILE_SCHEME = "file"

LOCAL_HOSTS = frozenset({"", "localhost"})

INLINE_INPUT_NAME: Final = "Inline input"
"""How refusals name an inline input, which has no URI."""


class InputResolutionError(ValueError):
    """Raised when a referenced input cannot be resolved into a value."""


@runtime_checkable
class InputResolver(Protocol):
    """Read the content one URI names, for one scheme."""

    def read(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> bytes:
        """Return the content, refusing any larger than `max_bytes`.

        Raises:
            InputResolutionError: The content is missing, unreadable, or
                larger than `max_bytes`.
        """
        ...


@dataclass(frozen=True)
class VersionedContent:
    """Content read from a store that versions it, with the version that held it.

    Either may be None when the store did not say: an unversioned S3 bucket
    gives an ETag but no version ID.
    """

    content: bytes
    version_id: str | None = None
    etag: str | None = None


@runtime_checkable
class VersionedInputResolver(InputResolver, Protocol):
    """A resolver that can also say which version of an object it read (ADR 0112)."""

    def read_versioned(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> VersionedContent:
        """Return the content and the version and ETag of the object that held it.

        Raises:
            InputResolutionError: The content is missing, unreadable, or
                larger than `max_bytes`.
        """
        ...


class FileInputResolver:
    """Read `file://` URIs that name an absolute path on the local host."""

    def read(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> bytes:
        """Return a local file's content, reading at most one byte past the cap.

        Raises:
            InputResolutionError: The URI is not a local, absolute `file://`
                URI, or the file is missing, not a file, unreadable, or larger
                than `max_bytes`.
        """

        path = file_path(uri)

        if not path.exists():
            raise InputResolutionError(f"Input {uri} does not exist.")

        if not path.is_file():
            raise InputResolutionError(f"Input {uri} is not a file.")

        try:
            with path.open("rb") as file:
                content = file.read(max_bytes + 1)
        except OSError as exc:
            raise InputResolutionError(f"Unable to read input {uri}: {exc}") from exc

        if len(content) > max_bytes:
            raise input_too_large(uri, max_bytes)

        return content


def file_uri(
    path: str | Path,
) -> str:
    """Return the `file://` URI of one path, made absolute."""

    return Path(path).absolute().as_uri()


def file_path(
    uri: str,
) -> Path:
    """Return the local path one `file://` URI names.

    Raises:
        InputResolutionError: The URI is not a `file://` URI, names another
            host, or does not name an absolute path.
    """

    parts = urlsplit(uri)

    if parts.scheme.lower() != FILE_SCHEME:
        raise InputResolutionError(f"Input {uri} is not a file:// URI.")

    if parts.netloc.lower() not in LOCAL_HOSTS:
        raise InputResolutionError(f"Input {uri} must name the local host.")

    path = Path(url2pathname(parts.path))

    if not path.is_absolute():
        raise InputResolutionError(f"Input {uri} must name an absolute path.")

    return path


@dataclass(frozen=True)
class InputPolicy:
    """What one entry point accepts as input.

    The resolvers name the accepted schemes, in lowercase. Resolved content is
    refused beyond `max_bytes`.
    """

    resolvers: Mapping[str, InputResolver] = field(default_factory=dict)
    max_bytes: int = DEFAULT_MAX_INPUT_BYTES

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("An input policy's max_bytes must be positive.")

    @property
    def accepted_schemes(
        self,
    ) -> tuple[str, ...]:
        """Return the accepted schemes, sorted."""

        return tuple(sorted(self.resolvers))


class InputProvenance(BaseModel):
    """Where a resolved input's content came from, and which content it was.

    A reference's provenance names the URI it was read from. An inline
    input's has no URI: it is marked `inline`, and names the origin its
    sender gave, if any (ADR 0112). Fields a provenance does not have are left
    out of its dump, so a reference's records exactly what it always has.
    """

    model_config = ConfigDict(frozen=True)

    uri: str | None = Field(default=None, min_length=1)
    inline: bool = False
    origin: InputOrigin | None = None
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)

    @model_validator(mode="after")
    def require_uri_for_references(
        self,
    ) -> "InputProvenance":
        """Require a URI exactly when the input was a reference."""

        if self.inline and self.uri is not None:
            raise ValueError("An inline input's provenance has no URI.")

        if not self.inline and self.uri is None:
            raise ValueError("A reference's provenance names its URI.")

        return self

    @model_serializer(mode="wrap")
    def omit_absent_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out the URI, `inline` and the origin when the provenance lacks them."""

        data = cast(dict[str, JsonValue], handler(self))

        if self.uri is None:
            data.pop("uri", None)

        if not self.inline:
            data.pop("inline", None)

        if self.origin is None:
            data.pop("origin", None)

        return data


class ResolvedInput(BaseModel):
    """The value a workflow receives, its provenance when it has one, and its label.

    A reference always has provenance. An inline input has it when it is
    binary or names an origin (ADR 0112). The sensitivity is the label its
    source named, or None for an unlabelled, internal input (ADR 0123).
    """

    model_config = ConfigDict(frozen=True)

    value: JsonValue
    media_type: str = Field(min_length=1)
    provenance: InputProvenance | None = None
    sensitivity: Sensitivity | None = None


def resolve_input(
    source: InlineInput | ReferenceInput,
    *,
    policy: InputPolicy,
    store: ContentStore,
) -> ResolvedInput:
    """Resolve one input source into the value a workflow receives.

    An inline JSON or text value is used as it is (see `resolve_inline_input`).
    A reference is read by the resolver for its scheme, within the policy's
    cap, decoded as its media type, and its content saved in the store before
    the resolved input is returned. A resolver that reads versions records
    the version and ETag it read as the reference's origin. Binary content is
    checked against its media type's signature instead of being decoded, and
    resolves to a content handle naming it (ADR 0112). Nothing is stored for
    content that is refused.

    Raises:
        InputResolutionError: The scheme is not accepted, or the content
            cannot be read, is too large, or does not decode.
    """

    if isinstance(source, InlineInput):
        return resolve_inline_input(
            source,
            policy=policy,
            store=store,
        )

    resolver = policy.resolvers.get(source.scheme)

    if resolver is None:
        accepted = ", ".join(policy.accepted_schemes) or None

        raise InputResolutionError(
            f"Input {source.uri} uses the {source.scheme!r} scheme, which is not accepted here; "
            + (f"accepted schemes: {accepted}." if accepted else "no schemes are accepted.")
        )

    origin: InputOrigin | None = None

    if isinstance(resolver, VersionedInputResolver):
        read = resolver.read_versioned(
            source.uri,
            max_bytes=policy.max_bytes,
        )
        content = read.content

        if read.version_id is not None or read.etag is not None:
            origin = InputOrigin(
                uri=source.uri,
                version_id=read.version_id,
                etag=read.etag,
            )
    else:
        content = resolver.read(
            source.uri,
            max_bytes=policy.max_bytes,
        )

    if len(content) > policy.max_bytes:
        raise input_too_large(source.uri, policy.max_bytes)

    binary = is_binary_media_type(source.media_type)

    try:
        if binary:
            check_binary_signature(content, source.media_type)
            value: JsonValue = None
        else:
            value = decode_content(content, source.media_type)
    except InputContentError as exc:
        raise InputResolutionError(f"Input {source.uri}: {exc}") from exc

    digest = store.put(content)

    if binary:
        value = ContentRef(
            digest=digest,
            media_type=source.media_type,
            size_bytes=len(content),
        ).to_value()

    return ResolvedInput(
        value=value,
        media_type=source.media_type,
        sensitivity=source.sensitivity,
        provenance=InputProvenance(
            uri=source.uri,
            origin=origin,
            media_type=source.media_type,
            size_bytes=len(content),
            digest=digest,
        ),
    )


def resolve_inline_input(
    source: InlineInput,
    *,
    policy: InputPolicy,
    store: ContentStore,
) -> ResolvedInput:
    """Resolve one inline input into the value a workflow receives (ADR 0112).

    A JSON or text value naming no origin is used as it is, with no
    provenance, exactly as before inline inputs could carry more.

    Binary content is base64: its encoded length is checked against the cap
    before it is decoded, four characters for every three bytes, and its
    decoded size after. It is checked against its media type's signature,
    stored, and resolves to a content handle.

    A JSON or text value naming an origin is stored too, as the bytes its
    origin holds would be compared with: text as UTF-8, and JSON in its
    canonical form, keys sorted and with no insignificant whitespace.

    Raises:
        InputResolutionError: Binary content is larger than the cap or does
            not carry its media type's signature.
    """

    binary = is_binary_media_type(source.media_type)

    if not binary and source.origin is None:
        return ResolvedInput(
            value=source.value,
            media_type=source.media_type,
            sensitivity=source.sensitivity,
        )

    if binary:
        content = _inline_binary_content(source, max_bytes=policy.max_bytes)
    else:
        content = _inline_value_content(source)

    digest = store.put(content)

    value = (
        ContentRef(
            digest=digest,
            media_type=source.media_type,
            size_bytes=len(content),
        ).to_value()
        if binary
        else source.value
    )

    return ResolvedInput(
        value=value,
        media_type=source.media_type,
        sensitivity=source.sensitivity,
        provenance=InputProvenance(
            inline=True,
            origin=source.origin,
            media_type=source.media_type,
            size_bytes=len(content),
            digest=digest,
        ),
    )


def input_too_large(
    uri: str,
    max_bytes: int,
) -> InputResolutionError:
    """Return the error for content beyond the cap, whatever its scheme."""

    return InputResolutionError(f"Input {uri} is larger than the limit of {max_bytes} bytes.")


def _inline_binary_content(
    source: InlineInput,
    *,
    max_bytes: int,
) -> bytes:
    """Return an inline binary input's decoded content, within the cap and signature-checked."""

    encoded = cast(str, source.value)

    if len(encoded) > 4 * -(-max_bytes // 3):
        raise _inline_too_large(max_bytes)

    #
    # The input already matched standard, padded base64 whole, so it decodes.
    #
    content = base64.b64decode(encoded, validate=True)

    if len(content) > max_bytes:
        raise _inline_too_large(max_bytes)

    try:
        check_binary_signature(content, source.media_type)
    except InputContentError as exc:
        raise InputResolutionError(f"{INLINE_INPUT_NAME}: {exc}") from exc

    return content


def _inline_value_content(
    source: InlineInput,
) -> bytes:
    """Return the bytes an inline JSON or text value stands for."""

    if isinstance(source.value, str) and is_text_media_type(source.media_type):
        return source.value.encode("utf-8")

    return json.dumps(
        source.value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _inline_too_large(
    max_bytes: int,
) -> InputResolutionError:
    """Return the error for inline content beyond the cap."""

    return InputResolutionError(
        f"{INLINE_INPUT_NAME} is larger than the limit of {max_bytes} bytes."
    )


__all__ = [
    "DEFAULT_MAX_INPUT_BYTES",
    "FILE_SCHEME",
    "FileInputResolver",
    "InputPolicy",
    "InputProvenance",
    "InputResolutionError",
    "InputResolver",
    "ResolvedInput",
    "VersionedContent",
    "VersionedInputResolver",
    "file_path",
    "file_uri",
    "input_too_large",
    "resolve_inline_input",
    "resolve_input",
]
