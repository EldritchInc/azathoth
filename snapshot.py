#!/usr/bin/env python3
"""
Generate a complete Azathoth project snapshot suitable for pasting into ChatGPT.

Outputs:
    project_snapshot.txt

Includes:
    - src/azathoth/** (excluding ui/)
    - tests/**
    - docs/adrs/**

Excludes:
    - __pycache__
    - *.pyc
    - .DS_Store
    - ui/
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

PROJECT_ROOT = Path(__file__).resolve().parent

OUTPUT_FILE = PROJECT_ROOT / "project_snapshot.txt"

SOURCE_ROOT = PROJECT_ROOT / "src" / "azathoth"
TEST_ROOT = PROJECT_ROOT / "tests"
ADR_ROOT = PROJECT_ROOT / "docs" / "adrs"

EXCLUDED_DIRS = {
    "__pycache__",
    "ui",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
}

EXCLUDED_FILES = {
    ".DS_Store",
}


def separator(
    path: Path,
) -> str:
    """Return a deterministic file separator for the snapshot."""

    relative_path = path.relative_to(PROJECT_ROOT)

    return "\n" + "=" * 100 + "\n" + str(relative_path) + "\n" + "=" * 100 + "\n\n"


def iter_files(
    root: Path,
) -> list[Path]:
    """Return included files beneath one snapshot root."""

    files: list[Path] = []

    if not root.exists():
        return files

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue

        if path.name in EXCLUDED_FILES:
            continue

        if path.suffix in EXCLUDED_SUFFIXES:
            continue

        files.append(path)

    return files


def write_section(
    output: TextIO,
    files: list[Path],
) -> None:
    """Write one collection of files to the snapshot."""

    for path in files:
        output.write(separator(path))

        try:
            text = path.read_text(
                encoding="utf-8",
            )
        except UnicodeDecodeError:
            output.write("<< UNABLE TO READ AS UTF-8 >>\n")
            continue

        output.write(text)

        if not text.endswith("\n"):
            output.write("\n")


def write_heading(
    output: TextIO,
    heading: str,
) -> None:
    """Write one top-level snapshot section heading."""

    output.write("\n" + "#" * 100 + "\n" + heading + "\n" + "#" * 100 + "\n")


def main() -> None:
    """Generate the complete project snapshot."""

    source_files = iter_files(
        SOURCE_ROOT,
    )

    test_files = iter_files(
        TEST_ROOT,
    )

    adr_files = iter_files(
        ADR_ROOT,
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as output:
        output.write("# AZATHOTH PROJECT SNAPSHOT\n\n")

        output.write(f"Project root: {PROJECT_ROOT}\n\n")

        output.write(f"Source files: {len(source_files)}\n")

        output.write(f"Test files: {len(test_files)}\n")

        output.write(f"ADR files: {len(adr_files)}\n\n")

        write_heading(
            output,
            "SOURCE",
        )

        write_section(
            output,
            source_files,
        )

        write_heading(
            output,
            "TESTS",
        )

        write_section(
            output,
            test_files,
        )

        write_heading(
            output,
            "ADRS",
        )

        write_section(
            output,
            adr_files,
        )

    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
