"""Source anchors: where in exactly which content something is (ADR 0113)."""

from typing import TypeVar, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from azathoth.citations.selectors import (
    MEDIA_FRAGMENT_SPECIFICATION,
    PDF_FRAGMENT_SPECIFICATION,
    FragmentSelector,
    Selector,
    TextPositionSelector,
    TextQuoteSelector,
)
from azathoth.inputs import PDF_MEDIA_TYPE, InputOrigin, validate_media_type
from azathoth.revisions import CONTENT_DIGEST_PATTERN

IMAGE_MEDIA_TYPE_PREFIX = "image/"

SelectorType = TypeVar(
    "SelectorType",
    TextQuoteSelector,
    TextPositionSelector,
    FragmentSelector,
)


class Extraction(BaseModel):
    """The tool that produced the text a source anchor's text selectors count.

    The digest names the tool's whole output in the content store, so an
    anchor can be checked again against exactly the text it was made from.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    tool: str = Field(min_length=1)
    version: str = Field(min_length=1)
    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)


class SourceAnchor(BaseModel):
    """A place in one exact piece of content, as W3C Web Annotation selectors say.

    The digest names the content's bytes, as the content store keeps them.
    The origin is where those bytes durably live, when it is known. Text
    selectors count the text of an extraction, which the anchor names; a
    fragment selector locates a page or a region of the content itself.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)
    media_type: str
    origin: InputOrigin | None = None
    selectors: tuple[Selector, ...]
    extraction: Extraction | None = None

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    @model_validator(mode="after")
    def require_consistent_selectors(
        self,
    ) -> "SourceAnchor":
        """Require one to three selectors of different kinds, each fit for the content."""

        if not self.selectors:
            raise ValueError("A source anchor holds at least one selector.")

        for kind in (TextQuoteSelector, TextPositionSelector, FragmentSelector):
            if sum(isinstance(selector, kind) for selector in self.selectors) > 1:
                raise ValueError(f"A source anchor holds at most one {kind.__name__}.")

        quote = self._selector(TextQuoteSelector)
        position = self._selector(TextPositionSelector)
        fragment = self._selector(FragmentSelector)

        if quote is not None and position is not None:
            span = position.end - position.start

            if span != len(quote.exact):
                raise ValueError(
                    f"A source anchor's quote is {len(quote.exact)} characters long, "
                    f"but its position spans {span}."
                )

        if (quote is not None or position is not None) and self.extraction is None:
            raise ValueError(
                "A source anchor's text selectors count the text of an extraction, "
                "so the anchor names its extraction."
            )

        if fragment is not None and not _locates(fragment.conformsTo, self.media_type):
            raise ValueError(
                f"A FragmentSelector conforming to {fragment.conformsTo} "
                f"cannot locate {self.media_type} content."
            )

        return self

    @model_serializer(mode="wrap")
    def omit_absent_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out an origin and an extraction the anchor does not have."""

        data = cast(dict[str, JsonValue], handler(self))

        for name in ("origin", "extraction"):
            if data.get(name) is None:
                data.pop(name, None)

        return data

    def _selector(
        self,
        kind: type[SelectorType],
    ) -> SelectorType | None:
        """Return the anchor's selector of one kind, if it has one."""

        for selector in self.selectors:
            if isinstance(selector, kind):
                return selector

        return None


def _locates(
    specification: str,
    media_type: str,
) -> bool:
    """Return whether a fragment specification can locate content of one media type."""

    if specification == PDF_FRAGMENT_SPECIFICATION:
        return media_type == PDF_MEDIA_TYPE

    if specification == MEDIA_FRAGMENT_SPECIFICATION:
        return media_type.startswith(IMAGE_MEDIA_TYPE_PREFIX)

    return False


__all__ = [
    "Extraction",
    "SourceAnchor",
]
