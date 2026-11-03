"""Tests for keeping resolved content in S3 from the command line (ADR 0108).

`AZATHOTH_CONTENT_STORE` moves every command's content store from the
database to S3. The store's client is answered by botocore's `Stubber`.
"""

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import azathoth.cli.persistence as cli_persistence
from azathoth.cli import CliRuntimeConfiguration, main
from azathoth.inputs import (
    CONTENT_STORE_VARIABLE,
    MISSING_CONTENT_STORE_EXTRA_MESSAGE,
    ContentStoreError,
    S3ContentLocation,
    S3ContentStore,
    SQLiteContentStore,
    content_bytes_digest,
    file_uri,
)
from azathoth.jobs import JobResult, JobStatus
from tests.cli.test_job_commands import Environment, request_data, write_request
from tests.cli.test_worker_command import QUEUE_URL, deploy

BUCKET = "azathoth-content"

STORE = f"s3://{BUCKET}/evidence"

CONTENT = json.dumps({"request": "review the rename"}).encode()

KEY = f"evidence/sha256/{content_bytes_digest(CONTENT)}"


@pytest.fixture
def s3(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Any]:
    """Point the content store at S3, with a client whose every call the Stubber answers."""

    pytest.importorskip("boto3")

    client = (
        importlib.import_module("boto3")
        .session.Session()
        .client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
    )

    monkeypatch.setenv(CONTENT_STORE_VARIABLE, STORE)
    monkeypatch.setattr(
        cli_persistence,
        "open_content_store",
        lambda location: S3ContentStore(location, client=client),
    )

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def job_with_input_file(
    tmp_path: Path,
) -> Path:
    """Write an input file, and a job request whose input is that file."""

    content = tmp_path / "review.json"
    content.write_bytes(CONTENT)

    return write_request(
        tmp_path / "request.json",
        request_data(input={"uri": file_uri(content), "media_type": "application/json"}),
    )


def run_job(
    capsys: pytest.CaptureFixture[str],
    request: Path,
) -> tuple[int, str, str]:
    """Run one job, returning its status, stdout and stderr."""

    status = main(("job", "run", str(request)))
    captured = capsys.readouterr()

    return status, captured.out, captured.err


# Configuration


def test_the_configuration_names_the_s3_store_or_none() -> None:
    assert CliRuntimeConfiguration.from_environment({}).content_store is None
    assert CliRuntimeConfiguration.from_environment(
        {CONTENT_STORE_VARIABLE: STORE}
    ).content_store == S3ContentLocation(bucket=BUCKET, prefix="evidence")


def test_a_content_store_that_is_not_s3_stops_any_command_in_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)
    monkeypatch.setenv(CONTENT_STORE_VARIABLE, "/var/lib/azathoth/content")

    assert main(("workflow", "list")) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "AZATHOTH_CONTENT_STORE '/var/lib/azathoth/content' is not an "
        "s3://<BUCKET>[/<PREFIX>] URL.\n"
    )


def test_a_command_that_stores_nothing_never_opens_the_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)
    monkeypatch.setenv(CONTENT_STORE_VARIABLE, STORE)
    monkeypatch.setitem(sys.modules, "boto3", None)

    assert main(("workflow", "list")) == 0


# Storing


def test_a_resolved_input_is_kept_in_s3_and_not_in_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    s3: Any,
) -> None:
    environment = Environment(tmp_path, monkeypatch)
    s3.add_response(
        "put_object",
        {},
        {"Bucket": BUCKET, "Key": KEY, "Body": CONTENT, "IfNoneMatch": "*"},
    )

    status, out, err = run_job(capsys, job_with_input_file(tmp_path))

    assert (status, err) == (0, "")
    assert JobResult.model_validate_json(out).status is JobStatus.SUCCEEDED
    assert SQLiteContentStore(environment.database).get(content_bytes_digest(CONTENT)) is None


def test_content_already_in_s3_is_not_written_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    s3: Any,
) -> None:
    Environment(tmp_path, monkeypatch)
    s3.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)

    status, out, _ = run_job(capsys, job_with_input_file(tmp_path))

    assert status == 0
    assert JobResult.model_validate_json(out).status is JobStatus.SUCCEEDED


def test_a_store_that_refuses_stops_the_job_before_it_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    s3: Any,
) -> None:
    environment = Environment(tmp_path, monkeypatch)
    s3.add_client_error(
        "put_object",
        service_error_code="AccessDenied",
        service_message="Access Denied",
        http_status_code=403,
    )

    status, out, err = run_job(capsys, job_with_input_file(tmp_path))

    assert (status, out) == (1, "")
    assert err == f"Cannot store content in s3://{BUCKET}/{KEY}: AccessDenied: Access Denied\n"
    assert environment.invocations() == ()
    assert environment.runtime_loads == 0


def test_without_boto3_a_job_that_stores_content_says_which_extra_to_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)
    monkeypatch.setenv(CONTENT_STORE_VARIABLE, STORE)
    monkeypatch.setitem(sys.modules, "boto3", None)

    status, out, err = run_job(capsys, job_with_input_file(tmp_path))

    assert (status, out) == (1, "")
    assert err == f"{MISSING_CONTENT_STORE_EXTRA_MESSAGE}\n"


# The worker


def test_a_worker_whose_s3_store_cannot_open_stops_before_it_receives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployment = deploy(tmp_path, monkeypatch)
    monkeypatch.setenv(CONTENT_STORE_VARIABLE, STORE)
    monkeypatch.setitem(sys.modules, "boto3", None)

    status = main(("worker", "run", "--queue-url", QUEUE_URL, "--wait-seconds", "0"))
    captured = capsys.readouterr()

    assert (status, captured.out) == (1, "")
    assert captured.err == f"{MISSING_CONTENT_STORE_EXTRA_MESSAGE}\n"
    assert deployment.queue.calls == []


def test_the_error_is_a_content_store_error() -> None:
    with pytest.raises(ContentStoreError):
        S3ContentLocation.parse("azathoth-content")


# The guides

CLI_README = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

INPUTS_README = Path(__file__).parents[2] / "src" / "azathoth" / "inputs" / "README.md"


@pytest.mark.parametrize("path", [CLI_README, INPUTS_README])
def test_the_readmes_quote_the_real_missing_extra_message(
    path: Path,
) -> None:
    assert f"\n{MISSING_CONTENT_STORE_EXTRA_MESSAGE}\n" in path.read_text(encoding="utf-8")


def test_the_cli_readme_quotes_the_real_refusal_of_a_store_that_is_not_s3() -> None:
    with pytest.raises(ContentStoreError) as raised:
        CliRuntimeConfiguration.from_environment(
            {CONTENT_STORE_VARIABLE: "/var/lib/azathoth/content"}
        )

    assert f"\n{raised.value}\n" in CLI_README.read_text(encoding="utf-8")


def test_the_readmes_quote_the_shape_of_a_refused_write() -> None:
    for path in (CLI_README, INPUTS_README):
        assert "\nCannot store content in s3://<BUCKET>/<KEY>: <CODE>: <MESSAGE>\n" in (
            path.read_text(encoding="utf-8")
        )
