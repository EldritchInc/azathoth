"""End-to-end tests for the built Azathoth wheel."""

import os
import shutil
import subprocess
import sys
import sysconfig
import venv
import zipfile
from pathlib import Path

from azathoth import __version__
from azathoth.cli import DATABASE_ENVIRONMENT_VARIABLE

DISTRIBUTION_PREFIX = "azathoth_ai"
PACKAGE_NAME = "azathoth"
CONSOLE_SCRIPT = "azathoth"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_WORKFLOW = PROJECT_ROOT / "examples" / "workflows" / "simple-prompt.json"
WORKFLOW_ID = "11111111-1111-1111-1111-111111111111"

LIBRARY_DIRECTORY_SCRIPT = "import sysconfig; print(sysconfig.get_path('purelib'))"

STANDARD_TOOL_FILES = (
    "run-workflow.json",
    "loop-workflow.json",
    "json-select.json",
    "json-object.json",
    "json-merge.json",
    "validate-json.json",
    "chunk-text.json",
    "join-text.json",
    "render-template.json",
)

STANDARD_TOOLS_SCRIPT = (
    "from azathoth.standard import standard_tool_documents; "
    "print(' '.join("
    "f'{document.definition.name}@{document.definition.version}' "
    "for document in standard_tool_documents()))"
)


def run(
    *arguments: str,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess and capture its text output."""

    return subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def copy_build_context(
    destination: Path,
) -> Path:
    """Copy the repository into an isolated wheel build context."""

    source = destination / "source"

    shutil.copytree(
        PROJECT_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "*.egg-info",
        ),
    )

    return source


def build_wheel(
    *,
    workspace: Path,
) -> Path:
    """Build one wheel without network access or build isolation."""

    source = copy_build_context(
        workspace,
    )
    wheel_directory = workspace / "wheelhouse"
    wheel_directory.mkdir()

    result = run(
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--no-build-isolation",
        "--wheel-dir",
        str(wheel_directory),
        str(source),
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr

    wheels = tuple(
        wheel_directory.glob(
            "*.whl",
        )
    )

    assert len(wheels) == 1

    return wheels[0]


def environment_bin_directory(
    environment: Path,
) -> Path:
    """Return the executable directory for one virtual environment."""

    if os.name == "nt":
        return environment / "Scripts"

    return environment / "bin"


def development_library_directories() -> tuple[Path, ...]:
    """Return the directories holding this environment's installed dependencies.

    `sysconfig` names them directly. `site.getsitepackages()` is not used,
    because on Windows its first entry is the installation root rather than
    `Lib\\site-packages`.
    """

    directories = (
        Path(sysconfig.get_path("purelib")),
        Path(sysconfig.get_path("platlib")),
    )

    return tuple(dict.fromkeys(directories))


def create_installed_environment(
    *,
    workspace: Path,
    wheel: Path,
) -> Path:
    """Install the wheel with runtime dependencies available offline."""

    environment = workspace / "installed"

    venv.EnvBuilder(
        with_pip=True,
    ).create(
        environment,
    )

    python = environment_bin_directory(environment) / (
        "python.exe" if os.name == "nt" else "python"
    )

    install_result = run(
        str(python),
        "-m",
        "pip",
        "install",
        "--no-deps",
        str(wheel),
        cwd=workspace,
    )

    assert install_result.returncode == 0, install_result.stderr

    library_result = run(
        str(python),
        "-c",
        LIBRARY_DIRECTORY_SCRIPT,
        cwd=workspace,
    )

    assert library_result.returncode == 0, library_result.stderr

    environment_library = Path(
        library_result.stdout.strip(),
    )

    dependency_path = environment_library / "azathoth-development-dependencies.pth"
    dependency_path.write_text(
        "".join(f"{directory}\n" for directory in development_library_directories()),
        encoding="utf-8",
    )

    return environment


def test_wheel_contains_package_and_typed_marker(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )

    with zipfile.ZipFile(
        wheel,
    ) as archive:
        files = set(
            archive.namelist(),
        )

    assert f"{PACKAGE_NAME}/__init__.py" in files
    assert f"{PACKAGE_NAME}/py.typed" in files


def test_wheel_contains_the_standard_tool_library(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )

    with zipfile.ZipFile(
        wheel,
    ) as archive:
        files = set(
            archive.namelist(),
        )

    assert f"{PACKAGE_NAME}/standard/__init__.py" in files

    for name in STANDARD_TOOL_FILES:
        assert f"{PACKAGE_NAME}/standard/tools/{name}" in files


def test_wheel_contains_distribution_metadata(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )

    with zipfile.ZipFile(
        wheel,
    ) as archive:
        files = tuple(
            archive.namelist(),
        )

    metadata_files = tuple(
        name
        for name in files
        if name.endswith(
            ".dist-info/METADATA",
        )
    )
    entry_point_files = tuple(
        name
        for name in files
        if name.endswith(
            ".dist-info/entry_points.txt",
        )
    )

    assert len(metadata_files) == 1
    assert len(entry_point_files) == 1


def test_wheel_installs_and_imports_outside_repository(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )
    environment = create_installed_environment(
        workspace=tmp_path,
        wheel=wheel,
    )

    python = environment_bin_directory(environment) / (
        "python.exe" if os.name == "nt" else "python"
    )
    working_directory = tmp_path / "consumer"
    working_directory.mkdir()

    result = run(
        str(python),
        "-c",
        (
            "from pathlib import Path; "
            "import azathoth; "
            "print(azathoth.__version__); "
            "print(Path(azathoth.__file__).resolve())"
        ),
        cwd=working_directory,
    )

    assert result.returncode == 0, result.stderr

    output = result.stdout.splitlines()

    assert output[0] == __version__

    installed_package = Path(
        output[1],
    )

    assert environment in installed_package.parents
    assert PROJECT_ROOT not in installed_package.parents


def test_wheel_installs_console_script_outside_repository(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )
    environment = create_installed_environment(
        workspace=tmp_path,
        wheel=wheel,
    )

    executable = environment_bin_directory(environment) / (
        f"{CONSOLE_SCRIPT}.exe" if os.name == "nt" else CONSOLE_SCRIPT
    )
    working_directory = tmp_path / "consumer"
    working_directory.mkdir()

    assert executable.exists()

    version_result = run(
        str(executable),
        "--version",
        cwd=working_directory,
    )
    help_result = run(
        str(executable),
        "--help",
        cwd=working_directory,
    )

    assert version_result.returncode == 0
    assert version_result.stdout == f"azathoth {__version__}\n"
    assert version_result.stderr == ""

    assert help_result.returncode == 0
    assert help_result.stdout.startswith(
        "usage: azathoth",
    )
    assert help_result.stderr == ""


def test_wheel_runs_provider_free_workflow_inspection_outside_repository(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )
    environment = create_installed_environment(
        workspace=tmp_path,
        wheel=wheel,
    )

    executable = environment_bin_directory(environment) / (
        f"{CONSOLE_SCRIPT}.exe" if os.name == "nt" else CONSOLE_SCRIPT
    )
    working_directory = tmp_path / "consumer"
    working_directory.mkdir()

    workflow = working_directory / "workflow.json"
    shutil.copyfile(
        EXAMPLE_WORKFLOW,
        workflow,
    )

    database = working_directory / "azathoth.db"

    process_environment = os.environ.copy()
    process_environment[DATABASE_ENVIRONMENT_VARIABLE] = str(
        database,
    )
    process_environment.pop(
        "OPENROUTER_API_KEY",
        None,
    )

    import_result = run(
        str(executable),
        "workflow",
        "import",
        str(workflow),
        cwd=working_directory,
        environment=process_environment,
    )

    assert import_result.returncode == 0, import_result.stderr
    assert import_result.stdout == f"Imported workflow {WORKFLOW_ID} revision 1.\n"

    list_result = run(
        str(executable),
        "workflow",
        "list",
        cwd=working_directory,
        environment=process_environment,
    )

    assert list_result.returncode == 0, list_result.stderr
    assert WORKFLOW_ID in list_result.stdout

    show_result = run(
        str(executable),
        "workflow",
        "show",
        WORKFLOW_ID,
        cwd=working_directory,
        environment=process_environment,
    )

    assert show_result.returncode == 0, show_result.stderr
    assert WORKFLOW_ID in show_result.stdout


def test_wheel_loads_the_standard_tool_library_outside_repository(
    tmp_path: Path,
) -> None:
    wheel = build_wheel(
        workspace=tmp_path,
    )
    environment = create_installed_environment(
        workspace=tmp_path,
        wheel=wheel,
    )

    python = environment_bin_directory(environment) / (
        "python.exe" if os.name == "nt" else "python"
    )
    working_directory = tmp_path / "consumer"
    working_directory.mkdir()

    result = run(
        str(python),
        "-c",
        STANDARD_TOOLS_SCRIPT,
        cwd=working_directory,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "run_workflow@1.0.0 loop_workflow@1.1.0 json_select@1.0.0 json_object@1.0.0 "
        "json_merge@1.0.0 validate_json@1.0.0 chunk_text@1.0.0 join_text@1.0.0 "
        "render_template@1.0.0\n"
    )
