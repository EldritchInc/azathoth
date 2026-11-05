"""Content handles: how a workflow names binary input content (ADR 0112).

A workflow never receives binary content itself. Its bytes are kept in the
content store, and the workflow receives `{"content": {...}}`, naming their
digest, media type and size. A handle names content; it does not grant it:
whoever reads content through a handle checks that its run received it.
"""

from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
)

from azathoth.inputs.media import is_binary_media_type
from azathoth.revisions import CONTENT_DIGEST_PATTERN

CONTENT_REF_KEY: Final = "content"
"""The single key of a content handle's value."""


class ContentRef(BaseModel):
    """Binary content in the content store, by its digest, media type and size."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)
    media_type: str
    size_bytes: int = Field(ge=0)

    @field_validator("media_type")
    @classmethod
    def require_binary_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require one of the binary media types."""

        if not is_binary_media_type(media_type):
            raise ValueError(
                f"A content handle names binary content; {media_type!r} is not a binary media type."
            )

        return media_type

    def to_value(
        self,
    ) -> dict[str, JsonValue]:
        """Return the value a workflow receives: `{"content": {...}}`."""

        return {
            CONTENT_REF_KEY: {
                "digest": self.digest,
                "media_type": self.media_type,
                "size_bytes": self.size_bytes,
            }
        }


def content_ref_from_value(
    value: JsonValue,
) -> ContentRef | None:
    """Return the handle one value is, or None when it is not exactly a handle.

    A handle is an object with the single key `content`, holding exactly a
    valid digest, a binary media type and a size. Being a handle says nothing
    about whether a run may read the content it names.
    """

    if not isinstance(value, dict) or set(value) != {CONTENT_REF_KEY}:
        return None

    try:
        return ContentRef.model_validate(value[CONTENT_REF_KEY])
    except ValidationError:
        return None


__all__ = [
    "CONTENT_REF_KEY",
    "ContentRef",
    "content_ref_from_value",
]
