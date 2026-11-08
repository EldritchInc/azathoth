"""Write `claim.pdf`, the two-page insurance claim the document examples read.

The PDF is written by hand, so it is the same bytes on every machine and
needs nothing installed: each page sets its text in Helvetica, one of the
standard fonts every PDF reader has, at known places. Run it from the
repository's root to write the PDF again:

    python examples/documents/make_claim_pdf.py
"""

from dataclasses import dataclass
from pathlib import Path

PDF = Path(__file__).with_name("claim.pdf")


@dataclass(frozen=True)
class Line:
    """One line of text, set at a baseline in points from the page's lower-left corner."""

    x: int
    y: int
    text: str
    size: int = 12


PAGES = (
    (
        Line(72, 720, "Claim 0412", size=18),
        Line(72, 690, "Filed by Ada Marsh, the insured,"),
        Line(72, 676, "on behalf of Marsh Bakery."),
        Line(72, 600, "The claim was received on December 14."),
    ),
    (
        Line(72, 720, "The adjuster inspected the oven on December 19"),
        Line(72, 706, "and found its door hinge cracked."),
        Line(72, 600, "Repair is approved up to $1,200."),
    ),
)
"""Each page's lines: lines set close together read as one text box, and so one segment."""


def _string(
    text: str,
) -> bytes:
    """Return text as a PDF literal string."""

    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    return f"({escaped})".encode("cp1252")


def _contents(
    lines: tuple[Line, ...],
) -> bytes:
    """Return the content stream that sets one page's lines."""

    return b"".join(
        f"BT /F1 {line.size} Tf {line.x} {line.y} Td ".encode() + _string(line.text) + b" Tj ET\n"
        for line in lines
    )


def claim_pdf() -> bytes:
    """Return the claim's PDF."""

    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(len(PAGES)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(PAGES)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

    for index, lines in enumerate(PAGES):
        contents = _contents(lines)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>"
            ).encode()
        )
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


if __name__ == "__main__":
    PDF.write_bytes(claim_pdf())
