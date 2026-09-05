"""Tests for installed Azathoth distribution metadata."""

from importlib.metadata import (
    PackageNotFoundError,
    distribution,
    entry_points,
    metadata,
    requires,
    version,
)
from pathlib import Path

import pytest

from azathoth import __version__

DISTRIBUTION_NAME = "azathoth-ai"
PACKAGE_NAME = "azathoth"
CONSOLE_SCRIPT = "azathoth"


def installed_distribution():
    """Return the installed Azathoth distribution."""

    try:
        return distribution(
            DISTRIBUTION_NAME,
        )
    except PackageNotFoundError:
        pytest.fail(f"Installed distribution {DISTRIBUTION_NAME!r} was not found.")


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"


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

    description = package_metadata.get_payload()

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


def test_distribution_contains_typed_package_marker() -> None:
    installed = installed_distribution()

    files = installed.files

    assert files is not None

    assert any(
        Path(file)
        .as_posix()
        .endswith(
            f"{PACKAGE_NAME}/py.typed",
        )
        for file in files
    )
