"""Static tests of the container image's build (ADR 0101).

They read the Dockerfile and need no Docker. `test_image.py` builds and runs
the image itself.
"""

import json
import re
import tomllib
from pathlib import Path

from azathoth.cli import DATABASE_ENVIRONMENT_VARIABLE

PROJECT_ROOT = Path(__file__).parents[2]

DOCKERFILE = PROJECT_ROOT / "Dockerfile"

DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"

VENV = "/opt/azathoth/venv"

DATA = "/var/lib/azathoth"

BUILD_INPUTS = ("pyproject.toml", "README.md", "LICENSE", "src/")


def instructions() -> tuple[tuple[str, str], ...]:
    """Return every Dockerfile instruction and its arguments, continuations joined."""

    logical: list[str] = []
    current = ""

    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not current and (not stripped or stripped.startswith("#")):
            continue

        if stripped.endswith("\\"):
            current += stripped[:-1].rstrip() + " "
            continue

        logical.append(current + stripped)
        current = ""

    assert current == "", "the Dockerfile ends inside a continuation"

    parsed: list[tuple[str, str]] = []

    for statement in logical:
        keyword, _, arguments = statement.partition(" ")
        parsed.append((keyword.upper(), arguments.strip()))

    return tuple(parsed)


def arguments(
    keyword: str,
) -> tuple[str, ...]:
    """Return the arguments of every instruction with one keyword, in order."""

    return tuple(rest for name, rest in instructions() if name == keyword)


def runtime_stage() -> tuple[tuple[str, str], ...]:
    """Return the instructions of the final stage."""

    parsed = instructions()
    last_from = max(index for index, (name, _) in enumerate(parsed) if name == "FROM")

    return parsed[last_from:]


def pairs(
    text: str,
) -> dict[str, str]:
    """Return the `KEY=value` pairs of one ENV or LABEL instruction."""

    return {
        key: value.strip('"') for key, value in re.findall(r'([A-Za-z_][\w.]*)=("[^"]*"|\S+)', text)
    }


def environment() -> dict[str, str]:
    """Return every variable the runtime stage sets."""

    merged: dict[str, str] = {}

    for name, rest in runtime_stage():
        if name == "ENV":
            merged.update(pairs(rest))

    return merged


def labels() -> dict[str, str]:
    """Return every label of the runtime stage."""

    merged: dict[str, str] = {}

    for name, rest in runtime_stage():
        if name == "LABEL":
            merged.update(pairs(rest))

    return merged


# The base


def test_the_base_is_slim_debian_trixie_with_a_tested_python() -> None:
    (default,) = (rest for rest in arguments("ARG") if rest.startswith("PYTHON_IMAGE="))

    match = re.fullmatch(r"PYTHON_IMAGE=python:(3\.\d+)-slim-trixie", default)

    assert match is not None, default

    python = match.group(1)
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert f'- "{python}"' in workflow
    assert f"Programming Language :: Python :: {python}" in project["project"]["classifiers"]


def test_a_builder_stage_builds_the_wheel_and_the_runtime_starts_clean() -> None:
    assert arguments("FROM") == ("${PYTHON_IMAGE} AS builder", "${PYTHON_IMAGE}")
    assert any("python -m build --wheel" in rest for rest in arguments("RUN"))
    assert "--from=builder /dist/ /tmp/dist/" in arguments("COPY")


# The install


def test_azathoth_is_installed_with_its_cloud_extras_into_its_own_venv() -> None:
    (install,) = (rest for name, rest in runtime_stage() if name == "RUN" and "pip install" in rest)

    assert f"python -m venv {VENV}" in install
    assert f"{VENV}/bin/python -m pip install" in install
    assert '"$1[otel,postgres,bedrock]"' in install
    assert "--no-cache-dir" in install


def test_the_venv_comes_first_on_path() -> None:
    variables = environment()

    assert variables["VIRTUAL_ENV"] == VENV
    assert variables["PATH"].split(":")[0] == f"{VENV}/bin"


def test_tini_is_installed_and_is_pid_1() -> None:
    assert any("apt-get install" in rest and " tini" in rest for rest in arguments("RUN"))

    (entrypoint,) = arguments("ENTRYPOINT")
    (command,) = arguments("CMD")

    assert json.loads(entrypoint) == ["/usr/bin/tini", "--", "azathoth"]
    assert json.loads(command) == ["--help"]


# Running


def test_the_image_runs_as_a_non_root_user_by_number() -> None:
    (user,) = arguments("USER")

    assert user == "10001:10001"
    assert any("--uid 10001" in rest and "--gid 10001" in rest for rest in arguments("RUN"))


def test_the_database_defaults_into_the_data_folder_without_a_volume() -> None:
    variables = environment()

    assert variables[DATABASE_ENVIRONMENT_VARIABLE] == f"{DATA}/azathoth.db"
    assert arguments("WORKDIR")[-1] == DATA
    assert arguments("VOLUME") == ()
    assert any(
        f"--owner=10001 --group=10001 --mode=0750 {DATA}" in rest for rest in arguments("RUN")
    )


def test_python_is_unbuffered_and_utf_8() -> None:
    variables = environment()

    assert variables["PYTHONUNBUFFERED"] == "1"
    assert variables["PYTHONDONTWRITEBYTECODE"] == "1"
    assert variables["PYTHONUTF8"] == "1"
    assert variables["LANG"] == "C.UTF-8"


def test_nothing_secret_is_baked_in() -> None:
    names = set(environment())

    assert not any(name.startswith(("OPENROUTER", "OTEL_", "AWS_")) for name in names)
    assert "AZATHOTH_OTEL" not in names
    assert arguments("ARG") == ("PYTHON_IMAGE=python:3.13-slim-trixie",)


def test_the_image_carries_oci_labels() -> None:
    assert labels() == {
        "org.opencontainers.image.title": "Azathoth",
        "org.opencontainers.image.description": (
            "An empirical optimization engine for context-aware AI workflows."
        ),
        "org.opencontainers.image.source": "https://github.com/EldritchInc/azathoth",
        "org.opencontainers.image.url": "https://github.com/EldritchInc/azathoth",
        "org.opencontainers.image.licenses": "MIT",
    }


def test_the_description_is_the_projects() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert labels()["org.opencontainers.image.description"] == project["project"]["description"]


# The build context


def test_the_build_context_holds_only_what_the_build_copies() -> None:
    lines = [
        line
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]

    assert lines[0] == "*"
    assert tuple(line[1:] for line in lines if line.startswith("!")) == BUILD_INPUTS
    assert {"**/__pycache__", "**/*.py[cod]", "**/*.egg-info"} <= set(lines)


def test_everything_the_build_copies_is_in_the_context() -> None:
    copied: list[str] = []

    for rest in arguments("COPY"):
        if rest.startswith("--from="):
            continue

        *sources, _destination = rest.split()
        copied.extend(sources)

    assert {source.rstrip("/") for source in copied} == {name.rstrip("/") for name in BUILD_INPUTS}

    for name in BUILD_INPUTS:
        assert (PROJECT_ROOT / name).exists(), name


def test_make_runs_the_image_tests() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"^\.PHONY:.*\bcontainer-test\b", makefile, re.MULTILINE)
    assert re.search(r"^container-test:$", makefile, re.MULTILINE)
    assert "AZATHOTH_RUN_CONTAINER_TESTS=1" in makefile
