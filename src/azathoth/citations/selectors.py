"""W3C Web Annotation selectors: how a source anchor says where (ADR 0113).

The selectors keep the Web Annotation Data Model's own names, `conformsTo`
included, so an anchor's selectors are standard selectors as they stand.
Positions count Unicode code points, as the model says: `start` is included
and `end` is not.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TEXT_QUOTE_SELECTOR: Final = "TextQuoteSelector"

TEXT_POSITION_SELECTOR: Final = "TextPositionSelector"

FRAGMENT_SELECTOR: Final = "FragmentSelector"

PDF_FRAGMENT_SPECIFICATION: Final = "http://tools.ietf.org/rfc/rfc3778"
"""The PDF fragment specification, by the IRI the Web Annotation model lists.

RFC 8118 replaced RFC 3778 and keeps its `page` and `viewrect` parameters;
the model's table names RFC 3778, which is the IRI annotation tools match.
"""

MEDIA_FRAGMENT_SPECIFICATION: Final = "http://www.w3.org/TR/media-frags/"
"""The W3C Media Fragments specification, for regions of an image (`xywh=`)."""

FRAGMENT_SPECIFICATIONS: Final = frozenset(
    {
        PDF_FRAGMENT_SPECIFICATION,
        MEDIA_FRAGMENT_SPECIFICATION,
    }
)
"""The fragment specifications a FragmentSelector may conform to."""


class TextQuoteSelector(BaseModel):
    """The exact text cited, with the text just before and after it."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    type: Literal["TextQuoteSelector"] = TEXT_QUOTE_SELECTOR
    exact: str
    prefix: str = ""
    suffix: str = ""

    @field_validator("exact")
    @classmethod
    def require_exact_text(
        cls,
        exact: str,
    ) -> str:
        """Refuse an empty quote."""

        if not exact:
            raise ValueError("A TextQuoteSelector's exact text is never empty.")

        return exact


class TextPositionSelector(BaseModel):
    """A span of text, by code point: `start` is included and `end` is not."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    type: Literal["TextPositionSelector"] = TEXT_POSITION_SELECTOR
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_a_span(
        self,
    ) -> "TextPositionSelector":
        """Require the span to hold at least one code point."""

        if self.end <= self.start:
            raise ValueError(
                "A TextPositionSelector's end comes after its start; "
                f"got start {self.start} and end {self.end}."
            )

        return self


class FragmentSelector(BaseModel):
    """A fragment of a document, as its media type's fragment specification writes it."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    type: Literal["FragmentSelector"] = FRAGMENT_SELECTOR
    value: str
    conformsTo: str

    @field_validator("value")
    @classmethod
    def require_a_bare_fragment(
        cls,
        value: str,
    ) -> str:
        """Require a fragment, without the `#` that introduces it in a URI."""

        if not value or value.startswith("#"):
            raise ValueError(
                f"A FragmentSelector's value is a fragment without its '#'; got {value!r}."
            )

        return value

    @field_validator("conformsTo")
    @classmethod
    def require_a_known_specification(
        cls,
        specification: str,
    ) -> str:
        """Require one of the fragment specifications Azathoth locates content by."""

        if specification not in FRAGMENT_SPECIFICATIONS:
            raise ValueError(
                f"A FragmentSelector conforms to {PDF_FRAGMENT_SPECIFICATION} or "
                f"{MEDIA_FRAGMENT_SPECIFICATION}; got {specification!r}."
            )

        return specification


Selector = Annotated[
    TextQuoteSelector | TextPositionSelector | FragmentSelector,
    Field(discriminator="type"),
]
"""Any selector a source anchor holds, read by its `type`."""


__all__ = [
    "FRAGMENT_SELECTOR",
    "FRAGMENT_SPECIFICATIONS",
    "MEDIA_FRAGMENT_SPECIFICATION",
    "PDF_FRAGMENT_SPECIFICATION",
    "TEXT_POSITION_SELECTOR",
    "TEXT_QUOTE_SELECTOR",
    "FragmentSelector",
    "Selector",
    "TextPositionSelector",
    "TextQuoteSelector",
]
