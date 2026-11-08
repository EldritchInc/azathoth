"""Tests that the release run's PDF and MCP-tool steps print what RELEASING says.

Each step's shell block is taken from RELEASING.md and run as written, by
bash from the checkout's root, with `azathoth` and `python` on the `PATH`
standing for the fresh venv's, against a database where step 3 has
installed the standard tools.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from azathoth.citations import SegmentedText
from azathoth.persistence.repositories import open_repositories

PROJECT_ROOT = Path(__file__).parents[1]

RELEASING = PROJECT_ROOT / "RELEASING.md"

CLAIM_PDF = PROJECT_ROOT / "examples" / "documents" / "claim.pdf"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="The release run's steps are bash; RELEASING runs it on macOS."
)


def step(
    heading: str,
) -> str:
    """Return one step of the pre-release examples run."""

    text = RELEASING.read_text(encoding="utf-8")
    start = text.index(heading)

    return text[start : text.index("\n### ", start + len(heading))]


def fenced(
    block: str,
    language: str,
) -> str:
    """Return the first fenced block of one language in a step."""

    found = re.search(rf"```{language}\n(.*?)```", block, re.DOTALL)

    assert found is not None

    return found.group(1)


def venv(
    tmp_path: Path,
) -> dict[str, str]:
    """Return an environment whose `azathoth` and `python` are this interpreter's.

    Its database has the standard tools installed, as step 3 leaves it.
    """

    #
    # Each command is a script that runs this interpreter by its own path. A
    # link to it would not do: a venv's interpreter, run through a link
    # elsewhere, no longer finds the venv's packages.
    #
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()

    for name, arguments in (("azathoth", '-m azathoth.cli "$@"'), ("python", '"$@"')):
        command = bin_directory / name
        command.write_text(f'#!/bin/sh\nexec "{sys.executable}" {arguments}\n', encoding="utf-8")
        command.chmod(0o755)

    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("AZATHOTH_", "OPENROUTER_", "OTEL_"))
    }
    environment["PATH"] = f"{bin_directory}{os.pathsep}{environment.get('PATH', '')}"
    environment["AZATHOTH_DATABASE"] = str(tmp_path / "examples.db")

    installed = subprocess.run(
        ["azathoth", "tool", "install-standard"],
        env=environment,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert installed.returncode == 0, installed.stderr

    return environment


def run_step(
    heading: str,
    environment: dict[str, str],
) -> str:
    """Run one step's shell block as written; return what it printed."""

    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", fenced(step(heading), "bash")],
        env=environment,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    return completed.stdout


def test_the_pdf_step_prints_the_line_releasing_shows(
    tmp_path: Path,
) -> None:
    environment = venv(tmp_path)
    printed = run_step("### 5. Read a PDF", environment).splitlines()[-1]
    extraction = json.loads(printed)["extraction"]
    expected = fenced(step("### 5. Read a PDF"), "text").strip()

    assert printed == (
        expected.replace("<PDFMINER_VERSION>", version("pdfminer.six")).replace(
            "<EXTRACTION_DIGEST>", extraction["digest"]
        )
    )
    assert extraction["source_digest"] == hashlib.sha256(CLAIM_PDF.read_bytes()).hexdigest()

    kept = open_repositories(Path(environment["AZATHOTH_DATABASE"])).content.get(
        extraction["digest"]
    )

    assert kept is not None
    assert len(SegmentedText.model_validate_json(kept).segments) == 5


def test_the_mcp_tool_step_prints_six(
    tmp_path: Path,
) -> None:
    environment = venv(tmp_path)
    printed = run_step("### 6. Call an MCP tool", environment)

    assert printed.splitlines()[-1] == "6"
    assert "The run must print exactly `6`." in step("### 6. Call an MCP tool")
    assert (tmp_path / "count-words-mcp.json").is_file()


def test_the_install_step_installs_the_documents_extra() -> None:
    install = fenced(step("### 2. Install them into a fresh venv"), "bash")

    assert '"$(echo dist/azathoth_ai-*.whl)[documents]"' in install
