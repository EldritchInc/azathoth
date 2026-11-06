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
    "SEGMENT_ID",
    "BoundingBox",
    "ExtractionError",
    "Segment",
    "SegmentedText",
]
