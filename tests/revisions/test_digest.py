"""Tests for stable content digests of durable documents."""

import hashlib
import re

from pydantic import BaseModel

from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
)


class Document(BaseModel):
    """A small document with nested, order-sensitive JSON."""

    name: str
    settings: dict[str, int]


PINNED_DIGEST = "78e977548eac0fefd522ae55ac33c668cab829cd052de7e4c8aa44e8426f2f53"


def test_digest_is_the_sha256_of_canonical_json() -> None:
    document = Document(
        name="alpha",
        settings={
            "b": 2,
            "a": 1,
        },
    )

    expected = hashlib.sha256(b'{"name":"alpha","settings":{"a":1,"b":2}}').hexdigest()

    assert content_digest(document) == expected


def test_digest_is_pinned_across_processes_and_platforms() -> None:
    document = Document(
        name="alpha",
        settings={
            "a": 1,
            "b": 2,
        },
    )

    assert content_digest(document) == PINNED_DIGEST


def test_digest_ignores_key_order_and_formatting_of_the_source() -> None:
    compact = Document.model_validate_json('{"settings":{"b":2,"a":1},"name":"alpha"}')

    spaced = Document.model_validate_json(
        '{\n  "name": "alpha",\n  "settings": {\n    "a": 1,\n    "b": 2\n  }\n}\n'
    )

    assert content_digest(compact) == content_digest(spaced) == PINNED_DIGEST


def test_digest_changes_with_content() -> None:
    first = Document(
        name="alpha",
        settings={"a": 1},
    )

    second = Document(
        name="alpha",
        settings={"a": 2},
    )

    assert content_digest(first) != content_digest(second)


def test_digest_keeps_non_ascii_text_verbatim() -> None:
    document = Document(
        name="señal",
        settings={},
    )

    expected = hashlib.sha256('{"name":"señal","settings":{}}'.encode()).hexdigest()

    assert content_digest(document) == expected


def test_digest_matches_the_published_pattern() -> None:
    assert re.fullmatch(
        CONTENT_DIGEST_PATTERN,
        content_digest(
            Document(
                name="alpha",
                settings={},
            )
        ),
    )
