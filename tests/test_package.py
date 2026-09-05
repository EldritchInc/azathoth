"""Tests for installed Azathoth distribution metadata."""

from importlib.metadata import (
    entry_points,
    metadata,
    requires,
    version,
)

from azathoth import __version__

DISTRIBUTION_NAME = "azathoth-ai"
CONSOLE_SCRIPT = "azathoth"


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
