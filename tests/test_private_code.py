"""Tests that this public repository never names Eldritch's private code (ADR 0120).

The private distributions live in private repositories and are never
imported, depended on or mentioned here. This test is the guard `make check`
runs: it fails if any file of the repository, or any file's path, names one.
"""

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]

PRIVATE_NAMES = re.compile(
    r"azathoth[_-]team|eldritch[_-]licensing|cthulhu",
    re.IGNORECASE,
)
"""The names of the private distributions, as packages, modules or repositories."""

SKIPPED_DIRECTORIES = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)
"""Directories that hold what tools made, not what the repository keeps."""

KEPT_HIDDEN_DIRECTORIES = frozenset({".github"})
"""Hidden directories the repository keeps: CI could depend on a private registry."""

THIS_FILE = Path(__file__).resolve()


def kept_files(
    root: Path,
) -> tuple[Path, ...]:
    """Return every file below one root the repository keeps, sorted.

    Hidden directories other than `.github` (`.git`, `.venv`, tool caches),
    build output and egg-info are skipped without being walked. This test itself names the
    private distributions, so it is skipped too.
    """

    files: list[Path] = []

    for directory, directories, names in os.walk(root):
        directories[:] = [
            name
            for name in directories
            if not (
                (name.startswith(".") and name not in KEPT_HIDDEN_DIRECTORIES)
                or name in SKIPPED_DIRECTORIES
                or name.endswith(".egg-info")
            )
        ]

        files.extend(
            path for name in names if (path := Path(directory) / name).resolve() != THIS_FILE
        )

    return tuple(sorted(files))


def private_mentions(
    root: Path,
) -> tuple[str, ...]:
    """Return each kept file below one root whose path or text names a private distribution."""

    mentions: list[str] = []

    for path in kept_files(root):
        relative = path.relative_to(root).as_posix()

        if PRIVATE_NAMES.search(relative):
            mentions.append(relative)
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if PRIVATE_NAMES.search(text):
            mentions.append(relative)

    return tuple(mentions)


def test_the_repository_names_no_private_distribution() -> None:
    assert private_mentions(PROJECT_ROOT) == ()


def test_an_import_of_a_private_package_is_found(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "plugin.py").write_text("import azathoth_team\n", encoding="utf-8")

    assert private_mentions(tmp_path) == ("src/plugin.py",)


def test_a_dependency_on_a_private_distribution_is_found_whatever_its_case(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["Azathoth-Team>=1"]\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("Install Cthulhu.\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("pip install eldritch_licensing\n", encoding="utf-8")

    assert private_mentions(tmp_path) == ("Makefile", "README.md", "pyproject.toml")


def test_a_private_name_in_a_path_is_found(
    tmp_path: Path,
) -> None:
    (tmp_path / "cthulhu").mkdir()
    (tmp_path / "cthulhu" / "notes.txt").write_text("nothing here\n", encoding="utf-8")

    assert private_mentions(tmp_path) == ("cthulhu/notes.txt",)


def test_what_tools_made_is_not_searched(
    tmp_path: Path,
) -> None:
    for directory in (".venv", "__pycache__", "build", "azathoth_ai.egg-info"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "record.txt").write_text("azathoth_team\n", encoding="utf-8")

    assert private_mentions(tmp_path) == ()


def test_the_ci_workflows_are_searched(
    tmp_path: Path,
) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "run: pip install --index-url https://private.example/simple azathoth-team\n",
        encoding="utf-8",
    )

    assert private_mentions(tmp_path) == (".github/workflows/ci.yml",)


def test_binary_files_are_not_read_as_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\xff\xfe azathoth_team")

    assert private_mentions(tmp_path) == ()
