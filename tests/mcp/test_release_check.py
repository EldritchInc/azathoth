"""Tests that RELEASING's MCP check runs and prints what it says it prints (ADR 0111).

The check's document and script are taken from RELEASING.md and run as
written, against a database where step 3's word-count workflow is promoted.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]

RELEASING = PROJECT_ROOT / "RELEASING.md"

WORKFLOW_ID = "a1000000-0000-4000-8000-000000000002"


def step(
    heading: str,
) -> str:
    """Return one step of the pre-release examples run."""

    text = RELEASING.read_text(encoding="utf-8")
    start = text.index(heading)

    return text[start : text.index("\n### ", start + len(heading))]


def heredoc(
    block: str,
    opening: str,
) -> str:
    """Return the body of the here-document a line of a shell block opens."""

    start = block.index(opening) + len(opening) + 1

    return block[start : block.index("\nEOF\n", start) + 1]


def azathoth(
    *arguments: str,
    environment: dict[str, str],
) -> None:
    """Run one `azathoth` command, requiring it to succeed."""

    completed = subprocess.run(
        [sys.executable, "-m", "azathoth.cli", *arguments],
        env=environment,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_the_mcp_check_prints_what_releasing_says(
    tmp_path: Path,
) -> None:
    check = step("### 4. Serve a workflow over MCP")
    shell = re.search(r"```bash\n(.*?)```", check, re.DOTALL)
    expected = re.search(r"```text\n(.*?)```", check, re.DOTALL)

    assert shell is not None
    assert expected is not None

    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("AZATHOTH_", "OPENROUTER_", "OTEL_"))
    }
    environment["AZATHOTH_DATABASE"] = str(tmp_path / "examples.db")

    for arguments in (
        ("tool", "import", "examples/tools/word-count.json"),
        ("tool", "import", "examples/tools/word-count-process.json"),
        ("workflow", "import", "examples/workflows/word-count-messages.json"),
        ("workflow", "promote", WORKFLOW_ID),
    ):
        azathoth(*arguments, environment=environment)

    opening = """cat > "$(dirname "$AZATHOTH_DATABASE")/exposure.json" <<'EOF'"""
    document = heredoc(shell.group(1), opening)
    (tmp_path / "exposure.json").write_text(document, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-"],
        input=heredoc(shell.group(1), "python - <<'EOF'"),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == expected.group(1)


def test_the_release_check_builds_and_installs_both_wheels() -> None:
    build = step("### 1. Build the wheels from `main`")
    install = step("### 2. Install them into a fresh venv")

    assert "python -m build packages/azathoth-mcp --outdir dist" in build
    assert (
        'python -m pip install "$(echo dist/azathoth_ai-*.whl)[documents]" dist/azathoth_mcp-*.whl'
        in install
    )
    assert "azathoth-mcp --version" in install


def test_the_testpypi_trial_installs_and_checks_both() -> None:
    text = RELEASING.read_text(encoding="utf-8")
    trial = text[text.index("## Trial Release on TestPyPI") : text.index("\n## Release\n")]

    assert '"azathoth-ai[documents]==<version>" "azathoth-mcp==<version>"' in trial
    assert "azathoth-mcp --version" in trial
    assert "Repeat steps 3 to 6 of the" in trial
