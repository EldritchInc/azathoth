#!/usr/bin/env python3
"""
Generate a complete Azathoth source snapshot suitable for pasting into ChatGPT.

Outputs:
    project_snapshot.txt

Includes:
    - src/azathoth/** (excluding ui/)
    - docs/adr/**

Excludes:
    - __pycache__
    - *.pyc
    - .DS_Store
    - ui/
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

OUTPUT_FILE = PROJECT_ROOT / "project_snapshot.txt"

SOURCE_ROOT = PROJECT_ROOT / "src" / "azathoth"
ADR_ROOT = PROJECT_ROOT / "docs" / "adr"

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
    return "\n" + "=" * 100 + "\n" + str(path.relative_to(PROJECT_ROOT)) + "\n" + "=" * 100 + "\n\n"


def iter_files(
    root: Path,
) -> list[Path]:
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
    output,
    files: list[Path],
) -> None:
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


def main() -> None:
    source_files = iter_files(
        SOURCE_ROOT,
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

        output.write(f"ADR files: {len(adr_files)}\n\n")

        output.write("#" * 100 + "\n" + "SOURCE\n" + "#" * 100 + "\n")

        write_section(
            output,
            source_files,
        )

        output.write("\n" + "#" * 100 + "\n" + "ADRS\n" + "#" * 100 + "\n")

        write_section(
            output,
            adr_files,
        )

    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
