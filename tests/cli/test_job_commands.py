"""Tests for `azathoth job run` (ADR 0097)."""

import io
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import azathoth.cli.application as application
import azathoth.cli.bootstrap as cli_bootstrap
import azathoth.cli.jobs as cli_jobs
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    CliRuntimeConfiguration,
    build_parser,
    main,
    run_job_request,
)
from azathoth.cli.rendering import (
    render_job_result,
    render_production_invocation,
)
from azathoth.context import Context
from azathoth.inputs import SQLiteContentStore, content_bytes_digest, file_uri
from azathoth.jobs import JobResult, JobStatus, decode_job_request, job_request_digest
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    InvocationIdempotency,
    ProductionInvocation,
    SQLiteProductionInvocationRepository,
    SQLiteWorkflowProductionStateRepository,
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNDEPLOYED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")

KEY = "order-4711-review"

MODEL = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def request_data(
    **changes: Any,
) -> dict[str, Any]:
    """Return one valid request document, with changes."""

    data: dict[str, Any] = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": KEY,
        "workflow_id": str(WORKFLOW_ID),
        "input": {"value": {"request": "review the rename"}},
        "caller_metadata": {"ticket": "OPS-12"},
    }

    data.update(changes)

    return data


def write_request(
    path: Path,
    data: dict[str, Any],
) -> Path:
    """Write one request document to a file."""

    path.write_text(json.dumps(data), encoding="utf-8")

    return path


def create_state() -> WorkflowProductionState:
    """Create one deterministic active production workflow."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="job-cli",
                description="Exercise production invocation through job run.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="job-prompt",
                            description="Return deterministic production output.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return the deterministic production response.",
                        ),
                        model_selection=MODEL,
                    ),
                    outputs=(
                        WorkflowValueBinding(
                            name="answer",
                        ),
                    ),
                ),
            ),
        ),
        emissions=(
            WorkflowProductionEmission(
                name="verdict",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="answer",
                ),
            ),
        ),
    )


class Environment:
    """A deployed workflow, a database and a counted runtime, for real CLI runs."""

    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        deploy: bool = True,
    ) -> None:
        self.tmp_path = tmp_path
        self.database = tmp_path / "azathoth.db"
        self.runtime_loads = 0

        if deploy:
            SQLiteWorkflowProductionStateRepository(self.database).set(create_state())

        monkeypatch.setenv(DATABASE_ENVIRONMENT_VARIABLE, str(self.database))

        monkeypatch.setattr(
            cli_bootstrap,
            "_load_current_models",
            lambda _configuration: ModelCatalog(
                models=(
                    ModelMetadata(
                        provider=MODEL.provider,
                        model=MODEL.model,
                        display_name=MODEL.identifier,
                    ),
                )
            ),
        )

        monkeypatch.setattr(
            cli_bootstrap,
            "_load_language_models",
            lambda *, configuration, models: LanguageModelRegistry(
                {
                    MODEL.identifier: DeterministicLanguageModel(
                        provider=MODEL.provider,
                        model=MODEL.model,
                        response_text="approve",
                    ),
                }
            ),
        )

        real_load_runtime = cli_bootstrap.load_runtime

        def counted_load_runtime(
            configuration: CliRuntimeConfiguration,
        ) -> AzathothRuntime:
            self.runtime_loads += 1

            return real_load_runtime(configuration)

        monkeypatch.setattr(cli_jobs, "load_runtime", counted_load_runtime)

    def invocations(
        self,
    ) -> tuple[ProductionInvocation, ...]:
        """Return the invocations recorded in the database."""

        return SQLiteProductionInvocationRepository(self.database).invocations()


def run(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, JobResult, str]:
    """Run the CLI, and return its exit code, its one result envelope and stderr."""

    code = main(arguments)

    captured = capsys.readouterr()

    lines = captured.out.splitlines()

    assert len(lines) == 1, captured.out

    return code, JobResult.model_validate_json(lines[0]), captured.err


# Parsing and dispatch


def test_job_run_parser_records_the_request_source() -> None:
    arguments = build_parser().parse_args(("job", "run", "request.json"))

    assert arguments.command == "job"
    assert arguments.job_action == "run"
    assert arguments.job_request == "request.json"


def test_job_run_parser_accepts_standard_input() -> None:
    assert build_parser().parse_args(("job", "run", "-")).job_request == "-"


def test_job_run_requires_a_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(("job", "run"))

    assert raised.value.code == 2
    assert "FILE" in capsys.readouterr().err


def test_cli_dispatches_job_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources: list[str] = []

    def fake_run_job_request(
        source: str,
    ) -> int:
        sources.append(source)

        return 73

    monkeypatch.setattr(application, "run_job_request", fake_run_job_request)

    assert main(("job", "run", "request.json")) == 73
    assert sources == ["request.json"]


def test_cli_help_lists_the_job_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    assert raised.value.code == 0
    assert ",init,job}" in capsys.readouterr().out


def test_job_without_an_action_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(("job",)) == 0
    assert "usage: azathoth" in capsys.readouterr().out


# Rendering


def test_a_result_renders_as_one_line_of_json_with_every_field() -> None:
    result = JobResult(
        idempotency_key="schlüssel",
        status=JobStatus.SUCCEEDED,
        invocation_id=INVOCATION_ID,
        result={"verdict": "approve"},
        error=None,
    )

    rendered = render_job_result(result)

    assert "\n" not in rendered
    assert "schlüssel" in rendered
    assert list(json.loads(rendered)) == [
        "kind",
        "version",
        "idempotency_key",
        "status",
        "replayed",
        "invocation_id",
        "result",
        "error",
    ]
    assert JobResult.model_validate_json(rendered) == result


def test_invocation_show_names_the_key_and_digest() -> None:
    invocation = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
        idempotency=InvocationIdempotency(key=KEY, request_digest="a" * 64),
    )

    rendered = render_production_invocation(invocation, result=None, run_id=None)

    assert f"Run ID: no run\nIdempotency Key: {KEY}\nRequest Digest: {'a' * 64}\n" in rendered


def test_invocation_show_omits_them_without_a_key() -> None:
    invocation = ProductionInvocation(
        id=INVOCATION_ID,
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
    )

    rendered = render_production_invocation(invocation, result=None, run_id=None)

    assert "Idempotency Key" not in rendered
    assert "Request Digest" not in rendered


# Running


def test_job_run_invokes_and_prints_a_succeeded_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    path = write_request(tmp_path / "request.json", request_data())

    code, result, err = run(capsys, "job", "run", str(path))

    assert code == 0
    assert err == ""
    assert result.status is JobStatus.SUCCEEDED
    assert result.replayed is False
    assert result.idempotency_key == KEY
    assert result.result == {"verdict": "approve"}

    (invocation,) = environment.invocations()

    assert invocation.id == result.invocation_id
    assert invocation.caller_metadata == {"ticket": "OPS-12"}
    assert invocation.idempotency == InvocationIdempotency(
        key=KEY,
        request_digest=job_request_digest(decode_job_request(request_data())),
    )
    assert environment.runtime_loads == 1


def test_job_run_replays_a_retry_without_loading_the_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    path = write_request(tmp_path / "request.json", request_data())

    _, first, _ = run(capsys, "job", "run", str(path))
    code, retry, _ = run(capsys, "job", "run", str(path))

    assert code == 0
    assert retry.status is JobStatus.SUCCEEDED
    assert retry.replayed is True
    assert retry.invocation_id == first.invocation_id
    assert len(environment.invocations()) == 1
    assert environment.runtime_loads == 1


def test_job_run_reads_the_request_from_standard_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)

    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(json.dumps(request_data()).encode("utf-8"))),
    )

    code, result, _ = run(capsys, "job", "run", "-")

    assert code == 0
    assert result.status is JobStatus.SUCCEEDED


def test_run_job_request_takes_an_explicit_standard_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)

    code = run_job_request(
        "-",
        stdin=io.BytesIO(json.dumps(request_data()).encode("utf-8")),
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"


def test_job_run_resolves_a_file_input_and_records_its_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    content = b'{"request": "review the rename"}'

    change = tmp_path / "change.json"
    change.write_bytes(content)

    path = write_request(
        tmp_path / "request.json",
        request_data(input={"uri": file_uri(change), "media_type": "application/json"}),
    )

    code, result, _ = run(capsys, "job", "run", str(path))

    assert code == 0
    assert result.status is JobStatus.SUCCEEDED

    (invocation,) = environment.invocations()

    resolved = [
        event.payload
        for event in invocation.initial_context.events
        if event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE
    ]

    assert resolved == [
        {
            "uri": file_uri(change),
            "media_type": "application/json",
            "size_bytes": len(content),
            "digest": content_bytes_digest(content),
        }
    ]
    assert SQLiteContentStore(environment.database).get(content_bytes_digest(content)) == content


def test_job_run_reports_an_undeployed_workflow_as_a_failed_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    path = write_request(
        tmp_path / "request.json",
        request_data(workflow_id=str(UNDEPLOYED_WORKFLOW_ID)),
    )

    code, result, _ = run(capsys, "job", "run", str(path))

    assert code == 1
    assert result.status is JobStatus.FAILED
    assert result.error is not None
    assert result.error.code.value == "workflow_not_deployed"
    assert len(environment.invocations()) == 1


def test_job_run_reports_a_conflict_without_loading_the_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    first = write_request(tmp_path / "first.json", request_data())
    second = write_request(
        tmp_path / "second.json",
        request_data(input={"value": {"request": "review the order search"}}),
    )

    run(capsys, "job", "run", str(first))
    code, result, _ = run(capsys, "job", "run", str(second))

    assert code == 1
    assert result.status is JobStatus.REJECTED
    assert result.invocation_id is None
    assert result.error is not None
    assert result.error.code.value == "idempotency_conflict"
    assert environment.runtime_loads == 1


def test_job_run_rejects_an_unresolvable_input_and_records_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch)

    path = write_request(
        tmp_path / "request.json",
        request_data(
            input={"uri": file_uri(tmp_path / "missing.json"), "media_type": "application/json"}
        ),
    )

    code, result, _ = run(capsys, "job", "run", str(path))

    assert code == 1
    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key == KEY
    assert result.error is not None
    assert result.error.code.value == "invalid_input"
    assert environment.invocations() == ()
    assert environment.runtime_loads == 0


def test_job_run_accepts_only_file_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)

    path = write_request(
        tmp_path / "request.json",
        request_data(input={"uri": "s3://bucket/change.json", "media_type": "application/json"}),
    )

    code, result, _ = run(capsys, "job", "run", str(path))

    assert code == 1
    assert result.error is not None
    assert result.error.code.value == "invalid_input"
    assert "accepted schemes: file" in result.error.message


# Requests that never reach the database


@pytest.mark.parametrize(
    ("content", "code", "key"),
    [
        (b"not json", "invalid_request", None),
        (b"[]", "invalid_request", None),
        (json.dumps(request_data(version=2)).encode("utf-8"), "unsupported_version", KEY),
        (json.dumps(request_data(kind="map")).encode("utf-8"), "invalid_request", KEY),
        (
            json.dumps({k: v for k, v in request_data().items() if k != "input"}).encode("utf-8"),
            "invalid_request",
            KEY,
        ),
    ],
)
def test_a_request_that_does_not_decode_is_rejected_before_the_database_opens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: bytes,
    code: str,
    key: str | None,
) -> None:
    environment = Environment(tmp_path, monkeypatch, deploy=False)

    path = tmp_path / "request.json"
    path.write_bytes(content)

    exit_code, result, err = run(capsys, "job", "run", str(path))

    assert exit_code == 1
    assert err == ""
    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key == key
    assert result.error is not None
    assert result.error.code.value == code
    assert not environment.database.exists()
    assert environment.runtime_loads == 0


def test_a_request_file_that_cannot_be_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = Environment(tmp_path, monkeypatch, deploy=False)

    missing = tmp_path / "missing.json"

    code, result, _ = run(capsys, "job", "run", str(missing))

    assert code == 1
    assert result.status is JobStatus.REJECTED
    assert result.idempotency_key is None
    assert result.error is not None
    assert result.error.code.value == "invalid_request"
    assert result.error.message.startswith(f"Cannot read the job request {missing}: ")
    assert not environment.database.exists()


def test_a_directory_as_the_request_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch, deploy=False)

    code, result, _ = run(capsys, "job", "run", str(tmp_path))

    assert code == 1
    assert result.error is not None
    assert result.error.code.value == "invalid_request"


def test_invocation_show_names_the_key_of_a_job_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    Environment(tmp_path, monkeypatch)

    path = write_request(tmp_path / "request.json", request_data())

    _, result, _ = run(capsys, "job", "run", str(path))

    assert main(("invocation", "show", str(result.invocation_id))) == 0

    out = capsys.readouterr().out

    assert f"Idempotency Key: {KEY}\n" in out
    assert "Request Digest: " in out
