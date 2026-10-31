"""Resolving input references at the edge, before a run (ADR 0096)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit
from urllib.request import url2pathname

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from azathoth.inputs.media import (
    InputContentError,
    decode_content,
)
from azathoth.inputs.source import (
    InlineInput,
    ReferenceInput,
)
from azathoth.inputs.store import ContentStore
from azathoth.revisions import CONTENT_DIGEST_PATTERN

DEFAULT_MAX_INPUT_BYTES = 10 * 1024 * 1024

FILE_SCHEME = "file"

LOCAL_HOSTS = frozenset({"", "localhost"})


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
            raise _too_large(uri, max_bytes)

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
    """Where a resolved input's content came from, and which content it was."""

    model_config = ConfigDict(frozen=True)

    uri: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)


class ResolvedInput(BaseModel):
    """The value a workflow receives, and its provenance when it was a reference."""

    model_config = ConfigDict(frozen=True)

    value: JsonValue
    media_type: str = Field(min_length=1)
    provenance: InputProvenance | None = None


def resolve_input(
    source: InlineInput | ReferenceInput,
    *,
    policy: InputPolicy,
    store: ContentStore,
) -> ResolvedInput:
    """Resolve one input source into the value a workflow receives.

    An inline value is used as it is. A reference is read by the resolver for
    its scheme, within the policy's cap, decoded as its media type, and its
    content saved in the store before the resolved input is returned.
    Nothing is stored for content that is refused.

    Raises:
        InputResolutionError: The scheme is not accepted, or the content
            cannot be read, is too large, or does not decode.
    """

    if isinstance(source, InlineInput):
        return ResolvedInput(
            value=source.value,
            media_type=source.media_type,
        )

    resolver = policy.resolvers.get(source.scheme)

    if resolver is None:
        accepted = ", ".join(policy.accepted_schemes) or None

        raise InputResolutionError(
            f"Input {source.uri} uses the {source.scheme!r} scheme, which is not accepted here; "
            + (f"accepted schemes: {accepted}." if accepted else "no schemes are accepted.")
        )

    content = resolver.read(
        source.uri,
        max_bytes=policy.max_bytes,
    )

    if len(content) > policy.max_bytes:
        raise _too_large(source.uri, policy.max_bytes)

    try:
        value = decode_content(content, source.media_type)
    except InputContentError as exc:
        raise InputResolutionError(f"Input {source.uri}: {exc}") from exc

    digest = store.put(content)

    return ResolvedInput(
        value=value,
        media_type=source.media_type,
        provenance=InputProvenance(
            uri=source.uri,
            media_type=source.media_type,
            size_bytes=len(content),
            digest=digest,
        ),
    )


def _too_large(
    uri: str,
    max_bytes: int,
) -> InputResolutionError:
    """Return the error for content beyond the cap."""

    return InputResolutionError(f"Input {uri} is larger than the limit of {max_bytes} bytes.")


__all__ = [
    "DEFAULT_MAX_INPUT_BYTES",
    "FILE_SCHEME",
    "FileInputResolver",
    "InputPolicy",
    "InputProvenance",
    "InputResolutionError",
    "InputResolver",
    "ResolvedInput",
    "file_path",
    "file_uri",
    "resolve_input",
]
