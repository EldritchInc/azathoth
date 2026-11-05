"""Tests that `azathoth-mcp` is released in lockstep with `azathoth-ai` (ADR 0111)."""

import re
import tomllib
from importlib.metadata import metadata, requires, version
from pathlib import Path

import azathoth
import azathoth_mcp

PROJECT_ROOT = Path(__file__).parents[2]

PACKAGE_ROOT = PROJECT_ROOT / "packages" / "azathoth-mcp"

DISTRIBUTION_NAME = "azathoth-mcp"

SOURCE_PATH = "packages/azathoth-mcp/src/azathoth_mcp"

EDITABLE_INSTALL = '-e ".[dev]" -e packages/azathoth-mcp'

LINK = re.compile(r"\]\(([^)\s]+)\)")


def project(
    root: Path,
) -> dict[str, object]:
    """Return the `[project]` table of the pyproject.toml in one directory."""

    table = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert isinstance(table, dict)

    return table


def minor_release(
    full_version: str,
) -> str:
    """Return the `X.Y` of an `X.Y.Z` version."""

    matched = re.fullmatch(r"(\d+\.\d+)\.\d+", full_version)

    assert matched is not None, full_version

    return matched.group(1)


def runtime_requirements() -> tuple[str, ...]:
    """Return the installed distribution's requirements outside any extra."""

    requirements = requires(DISTRIBUTION_NAME)

    assert requirements is not None

    return tuple(requirement for requirement in requirements if "extra ==" not in requirement)


def test_both_projects_declare_one_version() -> None:
    assert project(PACKAGE_ROOT)["version"] == project(PROJECT_ROOT)["version"]


def test_the_package_reports_azathoths_version() -> None:
    assert azathoth_mcp.__version__ == azathoth.__version__


def test_the_installed_distribution_is_this_version() -> None:
    assert version(DISTRIBUTION_NAME) == azathoth_mcp.__version__


def test_it_requires_exactly_its_own_minor_release_of_azathoth() -> None:
    pinned = f"azathoth-ai=={minor_release(azathoth.__version__)}.*"
    declared = project(PACKAGE_ROOT)["dependencies"]

    assert isinstance(declared, list)
    assert pinned in declared
    assert pinned in runtime_requirements()


def test_it_declares_exactly_its_runtime_dependencies() -> None:
    assert runtime_requirements() == (
        f"azathoth-ai=={minor_release(azathoth.__version__)}.*",
        "mcp<3,>=2.3",
        "pyjwt[crypto]<3,>=2.10",
    )


def test_azathoth_itself_gains_no_dependency_on_the_sdk() -> None:
    dependencies = project(PROJECT_ROOT)["dependencies"]

    assert isinstance(dependencies, list)
    assert not any(
        str(requirement).startswith(("mcp", "pyjwt", "azathoth-mcp"))
        for requirement in dependencies
    )


def test_it_supports_the_pythons_azathoth_supports() -> None:
    package_metadata = metadata(DISTRIBUTION_NAME)

    assert package_metadata["Requires-Python"] == metadata("azathoth-ai")["Requires-Python"]

    supported = {
        classifier
        for classifier in metadata("azathoth-ai").get_all("Classifier") or ()
        if classifier.startswith("Programming Language :: Python :: 3.")
    }

    assert supported
    assert supported <= set(package_metadata.get_all("Classifier") or ())


def test_it_is_licensed_as_azathoth_is() -> None:
    assert metadata(DISTRIBUTION_NAME)["License"] == "MIT"
    assert (PACKAGE_ROOT / "LICENSE").read_text(encoding="utf-8") == (
        PROJECT_ROOT / "LICENSE"
    ).read_text(encoding="utf-8")


def test_it_ships_type_information() -> None:
    assert (PACKAGE_ROOT / "src" / "azathoth_mcp" / "py.typed").is_file()


def test_its_description_is_its_readme_with_absolute_links() -> None:
    description = metadata(DISTRIBUTION_NAME)["Description"]
    readme = (PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")

    assert description is not None
    assert description.startswith("# Azathoth MCP")

    targets = LINK.findall(readme)

    assert targets
    assert all(target.startswith("https://") for target in targets), targets


def test_no_mcp_directory_at_the_root_shadows_the_sdk() -> None:
    assert not (PROJECT_ROOT / "mcp").exists()
    assert not (PROJECT_ROOT / "azathoth_mcp").exists()


def test_the_development_install_includes_it_everywhere_it_is_documented() -> None:
    for name in ("Makefile", "CONTRIBUTING.md", "RELEASING.md"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        installs = re.findall(r"pip install -e [^\n]*", text)

        assert installs, name
        assert all(install.endswith(EDITABLE_INSTALL) for install in installs), (name, installs)


def test_ci_installs_it_wherever_the_whole_suite_runs() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    whole_suite = workflow.split("\n  container:\n")[0]

    assert whole_suite.count(f"run: python -m pip install {EDITABLE_INSTALL}\n") == 2


def test_ci_installs_it_where_the_image_tests_run() -> None:
    """The image tests talk to the image's MCP server with the SDK's client."""

    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    container = workflow.split("\n  container:\n")[1].split("\n  postgres:\n")[0]

    assert f"run: python -m pip install {EDITABLE_INSTALL}\n" in container
    assert "from mcp import Client, StdioServerParameters" in (
        PROJECT_ROOT / "tests" / "container" / "test_image.py"
    ).read_text(encoding="utf-8")


def test_every_type_check_covers_it() -> None:
    for path in (
        PROJECT_ROOT / "Makefile",
        PROJECT_ROOT / "CONTRIBUTING.md",
        PROJECT_ROOT / "RELEASING.md",
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
    ):
        checks = re.findall(r"mypy [^\n]*", path.read_text(encoding="utf-8"))
        commands = [check for check in checks if check.startswith("mypy src/")]

        assert commands, path.name
        assert all(SOURCE_PATH in command for command in commands), (path.name, commands)


def test_its_page_links_the_guide() -> None:
    urls = metadata(DISTRIBUTION_NAME).get_all("Project-URL") or ()

    assert "Documentation, https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md" in urls
    assert "https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md" in (
        PACKAGE_ROOT / "README.md"
    ).read_text(encoding="utf-8")
