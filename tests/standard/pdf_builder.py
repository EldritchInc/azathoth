"""Write small PDFs by hand, with text at known places, for the document tools' tests.

Each page sets its text in Helvetica, one of the standard fonts every PDF
reader has, so a document needs no embedded font. Bytes from 128 on name
the glyphs `GLYPH_CODES` gives, through the font's encoding differences,
and the rest are WinAnsi. A page may also stroke rectangles, which are
drawings, not text.

A document may be encrypted with the standard security handler, revision 2:
40-bit RC4, keyed from a user password. A reader opens one whose user
password is empty without asking, and asks for any other.
"""

import hashlib
import struct
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


PASSWORD_PADDING = bytes.fromhex("28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a")
"""The bytes a password is padded with to 32, from the PDF specification."""

OWNER_PASSWORD = "owner"
"""The owner password of an encrypted document."""

DOCUMENT_ID = hashlib.md5(b"azathoth test document").digest()
"""The first part of every document's ID, which an encryption key is made from."""

PERMISSIONS = -4
"""Every permission, as the security handler's signed `/P`."""


def _rc4(
    key: bytes,
    data: bytes,
) -> bytes:
    """Return data encrypted, or decrypted, with RC4 under one key."""

    state = list(range(256))
    j = 0

    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]

    i = j = 0
    output = bytearray()

    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        output.append(byte ^ state[(state[i] + state[j]) % 256])

    return bytes(output)


def _padded(
    password: str,
) -> bytes:
    """Return a password padded, or cut, to 32 bytes."""

    return (password.encode("latin-1") + PASSWORD_PADDING)[:32]


@dataclass(frozen=True)
class _Encryption:
    """The key and the `/O` and `/U` entries of revision 2, for one user password."""

    key: bytes
    owner: bytes
    user: bytes

    @classmethod
    def for_password(
        cls,
        password: str,
    ) -> "_Encryption":
        """Make the entries as Algorithms 3.2, 3.3 and 3.4 of the PDF specification do."""

        owner = _rc4(hashlib.md5(_padded(OWNER_PASSWORD)).digest()[:5], _padded(password))
        key = hashlib.md5(
            _padded(password) + owner + struct.pack("<i", PERMISSIONS) + DOCUMENT_ID
        ).digest()[:5]

        return cls(key=key, owner=owner, user=_rc4(key, PASSWORD_PADDING))

    def stream(
        self,
        number: int,
        data: bytes,
    ) -> bytes:
        """Return one object's stream encrypted under the object's own key."""

        object_key = hashlib.md5(self.key + number.to_bytes(3, "little") + b"\0\0").digest()

        return _rc4(object_key[:10], data)

    def trailer(
        self,
    ) -> str:
        """Return the trailer entries that name the encryption and the document's ID."""

        return (
            f"/Encrypt << /Filter /Standard /V 1 /R 2 /O <{self.owner.hex()}> "
            f"/U <{self.user.hex()}> /P {PERMISSIONS} >> "
            f"/ID [<{DOCUMENT_ID.hex()}> <{DOCUMENT_ID.hex()}>]"
        )


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
    *,
    user_password: str | None = None,
) -> bytes:
    """Return a PDF of the pages given, in order, encrypted when a user password is given."""

    encryption = None if user_password is None else _Encryption.for_password(user_password)

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

        if encryption is not None:
            contents = encryption.stream(number + 1, contents)

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

    trailer = f"/Size {len(objects) + 1} /Root 1 0 R"

    if encryption is not None:
        trailer = f"{trailer} {encryption.trailer()}"

    document.extend(f"trailer\n<< {trailer} >>\nstartxref\n{xref}\n%%EOF\n".encode())

    return bytes(document)
