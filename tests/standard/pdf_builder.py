"""Write small PDFs by hand, with text at known places, for the document tools' tests.

Each page sets its text in Helvetica, one of the standard fonts every PDF
reader has, so a document needs no embedded font. Bytes from 128 on name
the glyphs `GLYPH_CODES` gives, through the font's encoding differences,
and the rest are WinAnsi. A page may also stroke rectangles, which are
drawings, not text.
"""

from collections.abc import Sequence
from dataclasses import dataclass

Box = tuple[float, float, float, float]

LETTER: Box = (0.0, 0.0, 612.0, 792.0)
"""A US Letter page, in points."""

GLYPH_CODES = {"\ufb01": 128, "\ufb02": 129, "\u0301": 130}
"""The byte each character WinAnsi lacks is set as: two ligatures and a combining acute."""

GLYPH_NAMES = "/fi /fl /acutecomb"
"""The glyph names of `GLYPH_CODES`, in order from 128."""


@dataclass(frozen=True)
class Text:
    """One run of text, set at a baseline in points from the media box's lower-left corner."""

    x: float
    y: float
    text: str
    size: float = 12.0


@dataclass(frozen=True)
class Page:
    """One page: its boxes, its rotation, its text, and the rectangles it strokes."""

    texts: Sequence[Text] = ()
    rectangles: Sequence[Box] = ()
    media_box: Box = LETTER
    crop_box: Box | None = None
    rotate: int = 0


def _number(value: float) -> str:
    """Return a number as PDF writes it."""

    return f"{value:g}"


def _box(box: Box) -> str:
    """Return a rectangle as a PDF array."""

    return "[" + " ".join(_number(value) for value in box) + "]"


def _string(text: str) -> bytes:
    """Return text as a PDF literal string in the font's encoding."""

    encoded = bytearray()

    for character in text:
        code = GLYPH_CODES.get(character)
        encoded.extend(bytes([code]) if code is not None else character.encode("cp1252"))

    escaped = bytes(encoded).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")

    return b"(" + escaped + b")"


def _contents(page: Page) -> bytes:
    """Return the content stream that sets a page's text and strokes its rectangles."""

    rectangles = b"".join(
        " ".join(_number(value) for value in rectangle).encode() + b" re S\n"
        for rectangle in page.rectangles
    )

    return rectangles + b"".join(
        b"BT /F1 "
        + _number(text.size).encode()
        + b" Tf "
        + f"{_number(text.x)} {_number(text.y)}".encode()
        + b" Td "
        + _string(text.text)
        + b" Tj ET\n"
        for text in page.texts
    )


def pdf_document(
    pages: Sequence[Page],
) -> bytes:
    """Return a PDF of the pages given, in order."""

    font = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding "
        b"<< /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [128 "
        + GLYPH_NAMES.encode()
        + b"] >> >>"
    )
    first_page = 4
    kids = " ".join(f"{first_page + 2 * index} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        font,
    ]

    for index, page in enumerate(pages):
        number = first_page + 2 * index
        attributes = [
            "/Type /Page",
            "/Parent 2 0 R",
            f"/MediaBox {_box(page.media_box)}",
            "/Resources << /Font << /F1 3 0 R >> >>",
            f"/Contents {number + 1} 0 R",
        ]

        if page.crop_box is not None:
            attributes.append(f"/CropBox {_box(page.crop_box)}")

        if page.rotate:
            attributes.append(f"/Rotate {page.rotate}")

        contents = _contents(page)
        objects.append(("<< " + " ".join(attributes) + " >>").encode())
        objects.append(
            f"<< /Length {len(contents)} >>\nstream\n".encode() + contents + b"endstream"
        )

    document = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")

    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())

    for offset in offsets:
        document.extend(f"{offset:010d} 00000 n \n".encode())

    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )

    return bytes(document)
