"""The CLI's whole provider-free lifecycle against PostgreSQL (ADR 0102).

`init` creates the schema; tools and workflows are imported; a workflow is
promoted; a parent workflow runs its promoted child in a separate process
over the same database; jobs run, replay and conflict. They need a server,
so they run only with `AZATHOTH_TEST_POSTGRES_URL`.
"""

import io
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from azathoth.cli import DATABASE_ENVIRONMENT_VARIABLE, main, run_job_request
from azathoth.inputs import content_bytes_digest
from azathoth.jobs import JobErrorCode, JobResult, JobStatus
from azathoth.persistence import MISSING_DRIVER_MESSAGE, PostgresLocation
from azathoth.persistence.repositories import close_postgres_databases, open_repositories

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLES = PROJECT_ROOT / "examples"

CHILD_WORKFLOW_ID = "a1000000-0000-4000-8000-000000000002"

PARENT_WORKFLOW_ID = "a1000000-0000-4000-8000-000000000003"

INSTALLED = (
    "Installed tool run_workflow@1.0.0 revision 1.\n"
    "Installed tool loop_workflow@1.1.0 revision 1.\n"
)

ALREADY_INSTALLED = (
    "Tool run_workflow@1.0.0 is already installed (revision 1).\n"
    "Tool loop_workflow@1.1.0 is already installed (revision 1).\n"
)


@pytest.fixture
def database_url(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Point the CLI at a fresh PostgreSQL schema."""

    monkeypatch.setenv(DATABASE_ENVIRONMENT_VARIABLE, postgres_url)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    return postgres_url


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command, and return its status, stdout and stderr."""

    code = main(arguments)
    captured = capsys.readouterr()

    return code, captured.out, captured.err


def job(
    capsys: pytest.CaptureFixture[str],
    request: dict[str, object],
) -> JobResult:
    """Run one job request through standard input, and return its one result."""

    run_job_request("-", stdin=io.BytesIO(json.dumps(request).encode("utf-8")))

    (line,) = capsys.readouterr().out.splitlines()

    return JobResult.model_validate_json(line)


def deploy_the_child_workflow_example(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Initialize the database, then import and promote the child-workflow example."""

    for arguments in (
        ("init",),
        ("tool", "import", str(EXAMPLES / "tools" / "word-count.json")),
        ("tool", "import", str(EXAMPLES / "tools" / "word-count-process.json")),
        ("workflow", "import", str(EXAMPLES / "workflows" / "word-count-messages.json")),
        ("workflow", "import", str(EXAMPLES / "workflows" / "count-words-in-child.json")),
        ("workflow", "promote", CHILD_WORKFLOW_ID),
    ):
        code, _, err = cli(capsys, *arguments)

        assert code == 0, (arguments, err)


# Initializing


def test_an_uninitialized_database_is_refused_without_its_password(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = cli(capsys, "workflow", "list")

    shown = PostgresLocation(database_url).display()

    assert code == 1
    assert out == ""
    assert err == f"Database {shown} is not initialized; run azathoth init.\n"

    #
    # The password may also be an ordinary word of the URL, such as the user
    # or database name, so it is looked for where it would be a secret: in
    # the URL's credentials.
    #
    password = urlsplit(database_url).password

    assert urlsplit(shown).password is None

    if password:
        assert f":{password}@" not in err


def test_init_creates_the_schema_then_finds_it(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shown = PostgresLocation(database_url).display()

    assert cli(capsys, "init") == (0, f"Database: {shown} (created)\n{INSTALLED}", "")
    assert cli(capsys, "init") == (0, f"Database: {shown} (existing)\n{ALREADY_INSTALLED}", "")


def test_without_the_extra_a_command_says_what_to_install(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "psycopg", None)

    assert cli(capsys, "workflow", "list") == (1, "", f"{MISSING_DRIVER_MESSAGE}\n")
    assert cli(capsys, "init") == (1, "", f"{MISSING_DRIVER_MESSAGE}\n")


# The lifecycle


def test_a_parent_workflow_runs_its_promoted_child_over_postgresql(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deploy_the_child_workflow_example(capsys)

    code, out, err = cli(
        capsys,
        "workflow",
        "run",
        PARENT_WORKFLOW_ID,
        "--input",
        json.dumps({"workflow_id": CHILD_WORKFLOW_ID, "input": "the old ones wait — and dream"}),
        "--output",
        "result",
    )

    assert (code, out) == (0, "7\n"), err

    try:
        repositories = open_repositories(database_url)
        runs = repositories.runs.runs()
        invocations = repositories.invocations.invocations()
    finally:
        close_postgres_databases()

    assert [str(run.workflow.id) for run in runs] == [CHILD_WORKFLOW_ID, PARENT_WORKFLOW_ID]
    assert [str(invocation.workflow_id) for invocation in invocations] == [CHILD_WORKFLOW_ID]


def test_jobs_run_replay_and_conflict_over_postgresql(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deploy_the_child_workflow_example(capsys)

    request: dict[str, object] = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": "postgres-lifecycle-1",
        "workflow_id": CHILD_WORKFLOW_ID,
        "input": {"value": "the old ones wait"},
    }

    first = job(capsys, request)
    replayed = job(capsys, request)
    conflict = job(capsys, {**request, "input": {"value": "something else entirely"}})

    assert first.status is JobStatus.SUCCEEDED
    assert first.result == {"result": 4}
    assert replayed.status is JobStatus.SUCCEEDED
    assert replayed.replayed is True
    assert replayed.invocation_id == first.invocation_id
    assert conflict.status is JobStatus.REJECTED
    assert conflict.error is not None
    assert conflict.error.code is JobErrorCode.IDEMPOTENCY_CONFLICT

    code, out, _ = cli(capsys, "invocation", "show", str(first.invocation_id))

    assert code == 0
    assert "postgres-lifecycle-1" in out


def test_an_input_file_is_stored_in_postgresql(
    database_url: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    deploy_the_child_workflow_example(capsys)

    source = tmp_path / "words.txt"
    source.write_text("one two three", encoding="utf-8")

    code, out, err = cli(
        capsys,
        "workflow",
        "invoke",
        CHILD_WORKFLOW_ID,
        "--input-file",
        str(source),
        "--output",
        "result",
    )

    assert code == 0, err
    assert json.loads(out) == {"result": 3}

    try:
        stored = open_repositories(database_url).content.get(content_bytes_digest(b"one two three"))
    finally:
        close_postgres_databases()

    assert stored == b"one two three"
