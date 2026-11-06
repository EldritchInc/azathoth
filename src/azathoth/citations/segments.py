"""Segments, and the segmented text an extraction stores (ADR 0113).

A document tool divides content into segments: spans of the text it
extracted, each with an ID a model can cite, and, for a PDF, the page and
box it came from. Its whole output is a `SegmentedText`, stored in the
content store as canonical JSON, so its digest names exactly that output,
and an anchor naming the digest can be checked again from the store alone.
"""

import json
import re
import unicodedata
from typing import Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from azathoth.citations.anchors import Extraction
from azathoth.inputs import ContentStore, content_bytes_digest, validate_media_type
from azathoth.revisions import CONTENT_DIGEST_PATTERN

SEGMENT_ID: Final = re.compile(r"(?:p(?P<page>[1-9][0-9]*)\.)?s[1-9][0-9]*")
"""A segment's ID, matched whole: `s12`, or `p3.s12` for a segment on page 3."""

EXTRACTION_KEY: Final = "extraction"
"""The single key of an extraction handle's value (ADR 0114)."""


class ExtractionError(ValueError):
    """Raised when stored content is not the segmented text it is taken for."""


class BoundingBox(BaseModel):
    """Where a segment lies on its page, in points from the page's top-left corner."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    left: float = Field(ge=0, allow_inf_nan=False)
    top: float = Field(ge=0, allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class Segment(BaseModel):
    """One span of an extraction's text that a citation may name.

    `start` is included and `end` is not, in Unicode code points of the
    extraction's text. A segment on a page names the page in its ID, and may
    name its bounding box there.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    bbox: BoundingBox | None = None

    @field_validator("id")
    @classmethod
    def check_id(
        cls,
        segment_id: str,
    ) -> str:
        """Require `s<N>`, or `p<PAGE>.s<N>`, counting from 1."""

        if SEGMENT_ID.fullmatch(segment_id) is None:
            raise ValueError(
                "A segment's id is s<N>, or p<PAGE>.s<N> on a page, counting from 1; "
                f"got {segment_id!r}."
            )

        return segment_id

    @model_validator(mode="after")
    def require_consistency(
        self,
    ) -> "Segment":
        """Require a span, and the same page in the ID and the field."""

        if self.end <= self.start:
            raise ValueError(
                f"Segment {self.id} ends after it starts; "
                f"got start {self.start} and end {self.end}."
            )

        match = SEGMENT_ID.fullmatch(self.id)
        named = match.group("page") if match is not None else None

        if named is not None and self.page is None:
            raise ValueError(f"Segment {self.id} names page {named}, but has no page.")

        if named is None and self.page is not None:
            raise ValueError(f"Segment {self.id} names no page, but is on page {self.page}.")

        if named is not None and int(named) != self.page:
            raise ValueError(f"Segment {self.id} names page {named}, but is on page {self.page}.")

        if self.bbox is not None and self.page is None:
            raise ValueError(
                f"Segment {self.id} has a bounding box, which only a segment on a page has."
            )

        return self

    @model_serializer(mode="wrap")
    def omit_absent_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out a page and a bounding box the segment does not have."""

        data = cast(dict[str, JsonValue], handler(self))

        for name in ("page", "bbox"):
            if data.get(name) is None:
                data.pop(name, None)

        return data


class SourcePage(BaseModel):
    """One page of an extraction's source, as it is shown (ADR 0114).

    `width` and `height` are the page's, in points, as a reader sees it: its
    crop box, turned with the page. `has_text` says whether any segment is on
    it, so a page with none, such as a scan, is told apart from a page that
    is not there.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    page: int = Field(ge=1)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)
    has_text: bool = Field(strict=True)


class ExtractionHandle(BaseModel):
    """A stored extraction, by its digest, the tool that made it, and its source (ADR 0114).

    It names an extraction as a content handle names content: a step's output
    holds the handle, and the extraction's text and segments stay in the
    content store.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    tool: str = Field(min_length=1)
    version: str = Field(min_length=1)
    digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)
    source_digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)
    media_type: str

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    def to_value(
        self,
    ) -> dict[str, JsonValue]:
        """Return the value a step outputs: `{"extraction": {...}}`."""

        return {EXTRACTION_KEY: cast(JsonValue, self.model_dump(mode="json"))}

    def extraction(
        self,
    ) -> Extraction:
        """Return the extraction an anchor made from this one names."""

        return Extraction(
            tool=self.tool,
            version=self.version,
            digest=self.digest,
        )


def extraction_handle_from_value(
    value: JsonValue,
) -> ExtractionHandle | None:
    """Return the extraction handle one value is, or None when it is not exactly one."""

    if not isinstance(value, dict) or set(value) != {EXTRACTION_KEY}:
        return None

    try:
        return ExtractionHandle.model_validate(value[EXTRACTION_KEY])
    except ValidationError:
        return None


class SegmentedText(BaseModel):
    """An extraction's whole output: the text it took from a source, and its segments.

    The text is in Unicode normalization form NFC, as the Web Annotation
    model asks of the text positions count. Segments are in order, do not
    overlap, lie within the text, and are named once each. A source with no
    text, such as a scanned page with no text layer, has no segments.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    tool: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_digest: str = Field(pattern=CONTENT_DIGEST_PATTERN)
    media_type: str
    text: str
    segments: tuple[Segment, ...] = ()
    pages: tuple[SourcePage, ...] = ()

    @field_validator("media_type")
    @classmethod
    def check_media_type(
        cls,
        media_type: str,
    ) -> str:
        """Require a well-formed, supported media type."""

        return validate_media_type(media_type)

    @field_validator("text")
    @classmethod
    def require_nfc(
        cls,
        text: str,
    ) -> str:
        """Require text already in NFC, so positions count what a reader sees."""

        if unicodedata.normalize("NFC", text) != text:
            raise ValueError("An extraction's text is in Unicode normalization form NFC.")

        return text

    @model_validator(mode="after")
    def require_ordered_segments(
        self,
    ) -> "SegmentedText":
        """Require segments named once each, in order, without overlap, within the text."""

        seen: set[str] = set()
        previous: Segment | None = None

        for segment in self.segments:
            if segment.id in seen:
                raise ValueError(f"Segment {segment.id} is named more than once.")

            seen.add(segment.id)

            if previous is not None and segment.start < previous.end:
                raise ValueError(
                    f"Segment {segment.id} starts at {segment.start}, "
                    f"before segment {previous.id} ends at {previous.end}."
                )

            if segment.end > len(self.text):
                raise ValueError(
                    f"Segment {segment.id} ends at {segment.end}, "
                    f"past the end of the text at {len(self.text)}."
                )

            previous = segment

        return self

    @model_validator(mode="after")
    def require_listed_pages(
        self,
    ) -> "SegmentedText":
        """Require listed pages to run from 1, and to agree with the segments on them."""

        if not self.pages:
            return self

        for number, page in enumerate(self.pages, start=1):
            if page.page != number:
                raise ValueError(
                    f"Page {page.page} is listed as page {number}; "
                    "pages are listed in order, from 1."
                )

        on_pages: dict[int, str] = {}

        for segment in self.segments:
            if segment.page is None:
                raise ValueError(
                    f"Segment {segment.id} names no page, but the extraction lists its pages."
                )

            if segment.page > len(self.pages):
                raise ValueError(
                    f"Segment {segment.id} is on page {segment.page}, "
                    f"but the extraction lists {len(self.pages)} pages."
                )

            on_pages.setdefault(segment.page, segment.id)

        for page in self.pages:
            if page.has_text and page.page not in on_pages:
                raise ValueError(f"Page {page.page} has text, but no segment is on it.")

            if not page.has_text and page.page in on_pages:
                raise ValueError(
                    f"Page {page.page} has no text, but segment {on_pages[page.page]} is on it."
                )

        return self

    @model_serializer(mode="wrap")
    def omit_absent_pages(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out pages the extraction does not list, so its digest is unchanged."""

        data = cast(dict[str, JsonValue], handler(self))

        if not data.get("pages"):
            data.pop("pages", None)

        return data

    def page(
        self,
        number: int,
    ) -> SourcePage | None:
        """Return one listed page by its number, or None when it is not listed."""

        if 1 <= number <= len(self.pages):
            return self.pages[number - 1]

        return None

    def segment(
        self,
        segment_id: str,
    ) -> Segment | None:
        """Return the segment with one ID, or None when there is none."""

        for segment in self.segments:
            if segment.id == segment_id:
                return segment

        return None

    def segment_text(
        self,
        segment: Segment,
    ) -> str:
        """Return the text one segment spans."""

        return self.text[segment.start : segment.end]

    def canonical_bytes(
        self,
    ) -> bytes:
        """Return the canonical JSON the content store keeps: sorted keys, no padding."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")

    def digest(
        self,
    ) -> str:
        """Return the digest of the canonical JSON, which names this extraction."""

        return content_bytes_digest(self.canonical_bytes())

    def extraction(
        self,
    ) -> Extraction:
        """Return the extraction a source anchor made from this text names."""

        return Extraction(
            tool=self.tool,
            version=self.version,
            digest=self.digest(),
        )

    def handle(
        self,
    ) -> ExtractionHandle:
        """Return the handle a step outputs in place of this text."""

        return ExtractionHandle(
            tool=self.tool,
            version=self.version,
            digest=self.digest(),
            source_digest=self.source_digest,
            media_type=self.media_type,
        )

    def store(
        self,
        store: ContentStore,
    ) -> str:
        """Keep the canonical JSON in a content store, and return its digest."""

        return store.put(self.canonical_bytes())

    @classmethod
    def load(
        cls,
        store: ContentStore,
        digest: str,
    ) -> "SegmentedText | None":
        """Return the segmented text a content store keeps by one digest, or None.

        Raises:
            ExtractionError: The content under the digest is not a segmented
                text.
        """

        content = store.get(digest)

        if content is None:
            return None

        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionError(
                f"Content {digest} is not a segmented text: it is not UTF-8 JSON."
            ) from exc

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ExtractionError(f"Content {digest} is not a segmented text: {exc}") from exc


__all__ = [
    "EXTRACTION_KEY",
    "SEGMENT_ID",
    "BoundingBox",
    "ExtractionError",
    "ExtractionHandle",
    "Segment",
    "SegmentedText",
    "SourcePage",
    "extraction_handle_from_value",
]
