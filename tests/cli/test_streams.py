"""Tests that the CLI writes its output as UTF-8 on every platform."""

import io
import sys

import pytest

from azathoth.cli import main
from azathoth.cli.streams import use_utf8_streams

TEXT = "café — 世界 → ✓"


def legacy_stream() -> io.TextIOWrapper:
    """Return a stream using a Windows ANSI code page, as redirected output does."""

    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def written_bytes(
    stream: io.TextIOWrapper,
) -> bytes:
    """Return the bytes a stream has written so far."""

    stream.flush()

    buffer = stream.buffer

    assert isinstance(buffer, io.BytesIO)

    return buffer.getvalue()


def test_a_legacy_code_page_cannot_write_every_character() -> None:
    with pytest.raises(UnicodeEncodeError):
        legacy_stream().write(TEXT)


def test_legacy_streams_are_switched_to_utf8() -> None:
    stream = legacy_stream()

    use_utf8_streams(stream)

    stream.write(TEXT)

    assert stream.encoding == "utf-8"
    assert written_bytes(stream) == TEXT.encode("utf-8")


def test_utf8_streams_are_left_as_they_are() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="UTF-8")

    use_utf8_streams(stream)

    assert stream.encoding == "UTF-8"


def test_streams_without_an_encoding_to_change_are_ignored() -> None:
    stream = io.StringIO()

    use_utf8_streams(stream)

    stream.write(TEXT)

    assert stream.getvalue() == TEXT


def test_main_writes_utf8_to_standard_output_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = legacy_stream()
    stderr = legacy_stream()

    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    assert main(()) == 0

    assert stdout.encoding == "utf-8"
    assert stderr.encoding == "utf-8"
