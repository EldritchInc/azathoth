"""Tests that every checked-in path can be checked out on every platform."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]

CHECKED_DIRECTORIES = (
    "docs",
    "examples",
    "src",
    "tests",
)

IGNORED_DIRECTORIES = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

WINDOWS_FORBIDDEN_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)

ADR_FILENAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")


def checked_paths() -> tuple[Path, ...]:
    """Return every file and directory below the checked directories."""

    paths: list[Path] = []

    for directory in CHECKED_DIRECTORIES:
        for path in sorted((PROJECT_ROOT / directory).rglob("*")):
            relative = path.relative_to(PROJECT_ROOT)

            if IGNORED_DIRECTORIES.isdisjoint(relative.parts):
                paths.append(relative)

    return tuple(paths)


def is_portable(
    name: str,
) -> bool:
    """Report whether one path component is valid on Windows, macOS and Linux."""

    return (
        name.isascii()
        and WINDOWS_FORBIDDEN_CHARACTERS.search(name) is None
        and name.split(".")[0].upper() not in WINDOWS_RESERVED_NAMES
        and not name.endswith((".", " "))
    )


def test_portability_check_rejects_windows_hostile_names() -> None:
    assert is_portable("0043-persist-workflow-specifications.md")
    assert not is_portable("0043: persist-workflow-specifications.md")
    assert not is_portable("0004–make-evaluation.md")
    assert not is_portable("aux.md")
    assert not is_portable("trailing.")


def test_every_checked_in_path_is_portable() -> None:
    paths = checked_paths()

    assert len(paths) > 0

    non_portable = tuple(
        str(path) for path in paths if not all(is_portable(part) for part in path.parts)
    )

    assert non_portable == ()


def test_adr_filenames_follow_the_numbered_slug_format() -> None:
    names = tuple(
        path.name
        for path in sorted((PROJECT_ROOT / "docs" / "adrs").glob("*.md"))
        if path.name != "README.md"
    )

    assert len(names) > 0

    malformed = tuple(name for name in names if ADR_FILENAME.match(name) is None)

    assert malformed == ()
