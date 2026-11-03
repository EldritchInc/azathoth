"""Tests for installed Azathoth distribution metadata."""

import re
from importlib.metadata import (
    entry_points,
    metadata,
    requires,
    version,
)
from pathlib import Path

import pytest

from azathoth import __version__

PROJECT_ROOT = Path(__file__).parents[1]

DISTRIBUTION_NAME = "azathoth-ai"
CONSOLE_SCRIPT = "azathoth"

PROJECT_URLS = (
    "Homepage, https://github.com/EldritchInc/azathoth",
    "Repository, https://github.com/EldritchInc/azathoth",
    "Issues, https://github.com/EldritchInc/azathoth/issues",
    "Funding, https://patreon.com/ErisDiscordiaM",
)


def requirement_name(
    requirement: str,
) -> str:
    """Return the distribution name at the start of one requirement string."""

    matched = re.match(
        r"[A-Za-z0-9._-]+",
        requirement,
    )

    assert matched is not None

    return matched.group()


def is_development_requirement(
    requirement: str,
) -> bool:
    """Report whether one requirement belongs to the dev extra.

    Setuptools versions differ in how they quote the marker, so both quote
    styles are accepted.
    """

    _, _, marker = requirement.partition(";")

    return marker.replace("'", '"').split() == ["extra", "==", '"dev"']


#
# Every way the documents show this Azathoth's own version: what
# `--version` prints, the image's tag, and the release's git tag.
#
SHOWN_VERSIONS = (
    re.compile(r"azathoth (\d+\.\d+\.\d+)"),
    re.compile(r"ghcr\.io/eldritchinc/azathoth:(\d+\.\d+\.\d+)"),
    re.compile(r"\$REGISTRY/azathoth:(\d+\.\d+\.\d+)"),
    re.compile(r"refs/tags/v(\d+\.\d+\.\d+)"),
    re.compile(r"git tag -a v(\d+\.\d+\.\d+)"),
    re.compile(r"git push origin v(\d+\.\d+\.\d+)"),
)


def current_documents() -> list[Path]:
    """Return the documents that describe this release, not past ones.

    The decision records and the changelog record history, so they are left
    out.
    """

    return [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "RELEASING.md",
        PROJECT_ROOT / "CONTRIBUTING.md",
        PROJECT_ROOT / "deploy" / "aws" / "azathoth.yaml",
        *sorted((PROJECT_ROOT / "docs").glob("*.md")),
        *sorted((PROJECT_ROOT / "src").rglob("README.md")),
    ]


def test_package_exposes_version() -> None:
    assert __version__ == "1.1.0"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(path, id=path.relative_to(PROJECT_ROOT).as_posix())
        for path in current_documents()
    ],
)
def test_every_version_the_documents_show_is_this_one(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    shown = {found for pattern in SHOWN_VERSIONS for found in pattern.findall(text)}

    assert shown <= {__version__}, shown


def test_distribution_name_is_public_package_name() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    assert package_metadata["Name"] == DISTRIBUTION_NAME


def test_distribution_version_matches_package_version() -> None:
    assert (
        version(
            DISTRIBUTION_NAME,
        )
        == __version__
    )


def test_distribution_requires_supported_python() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    assert package_metadata["Requires-Python"] == ">=3.11"


def test_distribution_declares_runtime_dependencies() -> None:
    requirements = requires(
        DISTRIBUTION_NAME,
    )

    assert requirements is not None

    runtime_requirements = tuple(
        requirement for requirement in requirements if "extra ==" not in requirement
    )

    assert runtime_requirements == (
        "httpx<1,>=0.28",
        "jsonschema<5,>=4.18",
        "pydantic>=2",
    )


def test_distribution_declares_mit_license() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    assert package_metadata["License"] == "MIT"


def test_distribution_uses_project_readme() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    description = package_metadata["Description"]

    assert description is not None
    assert description.startswith(
        "# Azathoth",
    )


def test_distribution_exposes_azathoth_console_script() -> None:
    scripts = tuple(
        entry_point
        for entry_point in entry_points(
            group="console_scripts",
        )
        if entry_point.name == CONSOLE_SCRIPT
    )

    assert (
        len(
            scripts,
        )
        == 1
    )

    script = scripts[0]

    assert script.value == "azathoth.cli:main"


def test_distribution_declares_stable_development_status() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    statuses = tuple(
        classifier
        for classifier in package_metadata.get_all("Classifier") or ()
        if classifier.startswith("Development Status ::")
    )

    assert statuses == ("Development Status :: 5 - Production/Stable",)


def test_distribution_declares_project_urls() -> None:
    package_metadata = metadata(
        DISTRIBUTION_NAME,
    )

    assert tuple(package_metadata.get_all("Project-URL") or ()) == PROJECT_URLS


def test_distribution_development_extra_can_build_releases() -> None:
    requirements = requires(
        DISTRIBUTION_NAME,
    )

    assert requirements is not None

    development_requirements = tuple(
        requirement_name(requirement)
        for requirement in requirements
        if is_development_requirement(requirement)
    )

    assert "build" in development_requirements
