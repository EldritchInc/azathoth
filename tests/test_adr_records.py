"""Tests that every architecture decision record shares one header and is indexed."""

import re
from pathlib import Path

ADR_DIRECTORY = Path(__file__).parents[1] / "docs" / "adrs"

INDEX = ADR_DIRECTORY / "README.md"

HEADING = re.compile(r"^# ADR (\d{4}): (\S.*)$")

STATUS = re.compile(
    r"^- Status: (Accepted|Proposed|Deprecated)(; amended by ADR \d{4}(, ADR \d{4})*)?$"
)

DATE = re.compile(r"^- Date: \d{4}-\d{2}-\d{2}$")

INDEX_ENTRY = re.compile(r"^- \[ADR (\d{4}): (.+)\]\((\S+\.md)\)$")


def record_paths() -> tuple[Path, ...]:
    """Return every numbered decision record, in number order."""

    return tuple(sorted(ADR_DIRECTORY.glob("[0-9][0-9][0-9][0-9]-*.md")))


def header_lines(
    path: Path,
) -> tuple[str, ...]:
    """Return the first four lines of one record."""

    return tuple(path.read_text(encoding="utf-8").split("\n")[:4])


def record_title(
    path: Path,
) -> str:
    """Return the title from one record's heading."""

    matched = HEADING.match(header_lines(path)[0])

    assert matched is not None, path.name

    return matched.group(2)


def test_records_are_numbered_without_gaps() -> None:
    numbers = tuple(int(path.name[:4]) for path in record_paths())

    assert len(numbers) > 0
    assert numbers == tuple(range(1, len(numbers) + 1))


def test_every_heading_carries_its_own_record_number() -> None:
    mismatched = tuple(
        path.name
        for path in record_paths()
        if (matched := HEADING.match(header_lines(path)[0])) is None
        or matched.group(1) != path.name[:4]
    )

    assert mismatched == ()


def test_every_record_declares_status_and_date_after_its_heading() -> None:
    malformed = tuple(
        path.name
        for path in record_paths()
        if not (
            header_lines(path)[1] == ""
            and STATUS.match(header_lines(path)[2]) is not None
            and DATE.match(header_lines(path)[3]) is not None
        )
    )

    assert malformed == ()


def test_index_lists_every_record_in_order_with_its_title() -> None:
    entries = tuple(
        matched.groups()
        for line in INDEX.read_text(encoding="utf-8").split("\n")
        if (matched := INDEX_ENTRY.match(line)) is not None
    )

    expected = tuple((path.name[:4], record_title(path), path.name) for path in record_paths())

    assert entries == expected
