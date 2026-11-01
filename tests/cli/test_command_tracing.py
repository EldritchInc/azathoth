"""Tests for tracing `workflow run`, `workflow invoke` and `job run` (ADR 0100)."""

import json
import sys
from pathlib import Path

import pytest

import azathoth.cli.tracing as cli_tracing
from azathoth.cli import main
from azathoth.telemetry import (
    ATTRIBUTE_KEYS,
    MISSING_EXTRA_MESSAGE,
    NO_TELEMETRY,
    Telemetry,
    TelemetryConfigurationError,
    active_telemetry,
)
from azathoth.workflows import SQLiteWorkflowRunRepository
from tests.cli.test_job_commands import (
    KEY,
    WORKFLOW_ID,
    Environment,
    request_data,
    write_request,
)
from tests.cli.test_job_commands import (
    run as run_job,
)
from tests.cli.test_workflow_run import (
    WORKFLOW_ID as CONFIGURED_WORKFLOW_ID,
)
from tests.cli.test_workflow_run import (
    configure_runtime,
    create_runtime,
)
from tests.telemetry.fakes import RecordedSpan, RecordingTelemetry

UNSUPPORTED_EXPORTER = "OTEL_TRACES_EXPORTER=zipkin is not supported; supported exporters: otlp."


@pytest.fixture
def telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> RecordingTelemetry:
    """Make every traced command trace with one recording telemetry."""

    recording = RecordingTelemetry()

    monkeypatch.setattr(cli_tracing, "configure_from_environment", lambda: recording)

    return recording


@pytest.fixture
def without_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turn tracing on in an environment where the `otel` extra cannot be imported."""

    monkeypatch.setenv("AZATHOTH_OTEL", "1")
    monkeypatch.setitem(sys.modules, "azathoth.telemetry.sdk", None)


def only(
    telemetry: RecordingTelemetry,
    name: str,
) -> RecordedSpan:
    """Return the one span with a name."""

    (span,) = telemetry.named(name)

    return span


def assert_carries_no_content(
    telemetry: RecordingTelemetry,
) -> None:
    """Assert every span carries known attributes only, and never the idempotency key."""

    for span in telemetry.spans:
        assert span.ended
        assert set(span.attributes) <= ATTRIBUTE_KEYS
        assert KEY not in repr(span.attributes)
        assert "review the rename" not in repr(span.attributes)
        assert "approve" not in repr(span.attributes)


# Running a command traced


def test_a_command_traces_with_the_active_telemetry_and_flushes_it(
    telemetry: RecordingTelemetry,
) -> None:
    seen: list[Telemetry] = []

    def command(
        given: Telemetry,
    ) -> int:
        seen.extend((given, active_telemetry()))

        return 7

    assert cli_tracing.run_traced(command) == 7
    assert seen == [telemetry, telemetry]
    assert telemetry.shut_down
    assert active_telemetry() is NO_TELEMETRY


def test_a_command_that_raises_still_flushes_and_restores(
    telemetry: RecordingTelemetry,
) -> None:
    def command(
        given: Telemetry,
    ) -> int:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        cli_tracing.run_traced(command)

    assert telemetry.shut_down
    assert active_telemetry() is NO_TELEMETRY


def test_a_failure_to_flush_never_changes_the_exit_status(
    telemetry: RecordingTelemetry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def shutdown() -> None:
        raise ConnectionError("collector is down")

    monkeypatch.setattr(telemetry, "shutdown", shutdown)

    assert cli_tracing.run_traced(lambda _telemetry: 0) == 0


def test_tracing_without_the_extra_runs_nothing(
    without_the_extra: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ran: list[Telemetry] = []

    def command(
        given: Telemetry,
    ) -> int:
        ran.append(given)

        return 0

    assert cli_tracing.run_traced(command) == 1
    assert ran == []
    assert capsys.readouterr().err == f"{MISSING_EXTRA_MESSAGE}\n"


def test_an_unsupported_exporter_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def configure() -> Telemetry:
        raise TelemetryConfigurationError(UNSUPPORTED_EXPORTER)

    monkeypatch.setattr(cli_tracing, "configure_from_environment", configure)

    assert cli_tracing.run_traced(lambda _telemetry: 0) == 1
    assert capsys.readouterr().err == f"{UNSUPPORTED_EXPORTER}\n"


# job run


def test_job_run_traces_the_job_its_invocation_run_and_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    telemetry: RecordingTelemetry,
) -> None:
    Environment(tmp_path, monkeypatch)
    request = write_request(tmp_path / "request.json", request_data())

    code, result, _ = run_job(capsys, "job", "run", str(request))

    job = only(telemetry, "azathoth.job")
    invocation = only(telemetry, "azathoth.invocation")
    run = only(telemetry, "azathoth.run")
    step = only(telemetry, "azathoth.step")

    assert code == 0
    assert job.parent is None
    assert invocation.parent is job
    assert run.parent is invocation
    assert step.parent is run

    assert job.attributes == {
        "azathoth.job.kind": "invoke",
        "azathoth.job.version": 1,
        "azathoth.job.status": "succeeded",
        "azathoth.job.replayed": False,
        "azathoth.invocation.id": str(result.invocation_id),
    }
    assert invocation.attributes["azathoth.invocation.outcome"] == "succeeded"
    assert run.attributes["azathoth.run.status"] == "succeeded"
    assert step.attributes["gen_ai.provider.name"] == "test-provider"
    assert step.attributes["gen_ai.request.model"] == "production-model"
    assert telemetry.shut_down
    assert_carries_no_content(telemetry)


def test_a_replayed_job_is_one_span_with_no_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    telemetry: RecordingTelemetry,
) -> None:
    Environment(tmp_path, monkeypatch)
    request = write_request(tmp_path / "request.json", request_data())

    run_job(capsys, "job", "run", str(request))
    telemetry.spans.clear()

    code, result, _ = run_job(capsys, "job", "run", str(request))

    (job,) = telemetry.spans

    assert code == 0
    assert result.replayed is True
    assert job.attributes["azathoth.job.replayed"] is True
    assert job.attributes["azathoth.invocation.id"] == str(result.invocation_id)


def test_a_rejected_job_is_marked_failed_with_its_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    telemetry: RecordingTelemetry,
) -> None:
    request = write_request(tmp_path / "request.json", request_data(version=2))

    code, result, _ = run_job(capsys, "job", "run", str(request))

    (job,) = telemetry.spans

    assert code == 1
    assert result.error is not None
    assert job.error_type == result.error.code.value
    assert job.attributes["azathoth.job.status"] == "rejected"


def test_job_run_without_the_extra_prints_no_envelope_and_runs_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    without_the_extra: None,
) -> None:
    environment = Environment(tmp_path, monkeypatch)
    request = write_request(tmp_path / "request.json", request_data())

    code = main(("job", "run", str(request)))
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == ""
    assert captured.err == f"{MISSING_EXTRA_MESSAGE}\n"
    assert environment.runtime_loads == 0
    assert environment.invocations() == ()


# workflow invoke


def test_workflow_invoke_traces_the_invocation_run_and_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    telemetry: RecordingTelemetry,
) -> None:
    Environment(tmp_path, monkeypatch)

    code = main(
        (
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            json.dumps({"request": "review the rename"}),
            "--output",
            "result",
        )
    )
    capsys.readouterr()

    invocation = only(telemetry, "azathoth.invocation")
    run = only(telemetry, "azathoth.run")
    step = only(telemetry, "azathoth.step")

    assert code == 0
    assert telemetry.named("azathoth.job") == []
    assert invocation.parent is None
    assert run.parent is invocation
    assert step.parent is run
    assert invocation.attributes["azathoth.workflow.id"] == str(WORKFLOW_ID)
    assert invocation.attributes["azathoth.invocation.outcome"] == "succeeded"
    assert telemetry.shut_down
    assert_carries_no_content(telemetry)


def test_workflow_invoke_without_the_extra_records_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    without_the_extra: None,
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    code = main(("workflow", "invoke", str(WORKFLOW_ID), "--input", "{}"))
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == ""
    assert captured.err == f"{MISSING_EXTRA_MESSAGE}\n"
    assert environment.invocations() == ()


# workflow run


def test_workflow_run_traces_the_run_and_its_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    telemetry: RecordingTelemetry,
) -> None:
    database = configure_runtime(monkeypatch, tmp_path, create_runtime())

    code = main(("workflow", "run", str(CONFIGURED_WORKFLOW_ID)))
    capsys.readouterr()

    run = only(telemetry, "azathoth.run")
    step = only(telemetry, "azathoth.step")
    (recorded,) = SQLiteWorkflowRunRepository(database).runs()

    assert code == 0
    assert run.parent is None
    assert step.parent is run
    assert run.attributes["azathoth.run.id"] == str(recorded.id)
    assert telemetry.named("azathoth.invocation") == []
    assert telemetry.shut_down
    assert_carries_no_content(telemetry)


def test_workflow_run_without_the_extra_runs_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    without_the_extra: None,
) -> None:
    database = configure_runtime(monkeypatch, tmp_path, create_runtime())

    code = main(("workflow", "run", str(CONFIGURED_WORKFLOW_ID)))
    captured = capsys.readouterr()

    assert code == 1
    assert captured.err == f"{MISSING_EXTRA_MESSAGE}\n"
    assert not database.exists() or SQLiteWorkflowRunRepository(database).runs() == ()
