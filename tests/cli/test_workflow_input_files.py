"""Tests for giving `workflow run` and `workflow invoke` a file as input (ADR 0096)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.application as cli_application
import azathoth.cli.inputs as cli_inputs
from azathoth.cli import (
    WorkflowInputFile,
    WorkflowRunInput,
    main,
)
from azathoth.cli.keyed_invocation import keyed_request
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.workflows import SENSITIVITY_WITHOUT_INPUT_MESSAGE
from azathoth.context import INPUT_SENSITIVITY_EVENT_TYPE, Context, context_sensitivity
from azathoth.inputs import (
    FileInputResolver,
    InputPolicy,
    InputSourceError,
    SQLiteContentStore,
    content_bytes_digest,
    file_uri,
)
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    SQLiteProductionInvocationRepository,
    SQLiteWorkflowRunRepository,
)
from azathoth.workflows.production_invocation import PRODUCTION_INVOCATION_EVENT_TYPE
from tests.examples.test_word_count_benchmark_examples import (
    configure_walkthrough,
    import_examples,
    run_cli,
)
from tests.examples.test_word_count_messages_examples import (
    TEXT,
    WORKFLOW_ID,
)

CONTENT = TEXT.encode()


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the word-count examples into an isolated database and return it."""

    path = configure_walkthrough(monkeypatch, tmp_path)

    import_examples(capsys)

    return path


def write(
    path: Path,
    content: bytes,
) -> Path:
    """Write content to one file and return its path."""

    path.write_bytes(content)

    return path


def run_status(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one CLI command, returning its status, standard output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


def initial_context(
    database: Path,
) -> Context:
    """Return the initial context of the latest configured run of the example."""

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert runs

    return runs[-1].initial_context


def resolved_payload(
    path: Path,
    media_type: str,
    content: bytes = CONTENT,
) -> dict[str, object]:
    """Return the provenance a resolved file input records."""

    return {
        "uri": file_uri(path),
        "media_type": media_type,
        "size_bytes": len(content),
        "digest": content_bytes_digest(content),
    }


def test_input_file_source_infers_the_media_type_from_the_extension(
    tmp_path: Path,
) -> None:
    source = cli_inputs.input_file_source(WorkflowInputFile(path=tmp_path / "chapter.md"))

    assert source.uri == file_uri(tmp_path / "chapter.md")
    assert source.media_type == "text/markdown"


def test_input_file_source_prefers_a_given_media_type(
    tmp_path: Path,
) -> None:
    source = cli_inputs.input_file_source(
        WorkflowInputFile(path=tmp_path / "chapter.md", media_type="text/plain"),
    )

    assert source.media_type == "text/plain"


def test_input_file_source_refuses_an_unknown_extension(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputSourceError, match="give it with --media-type"):
        cli_inputs.input_file_source(WorkflowInputFile(path=tmp_path / "words.data"))


def test_the_cli_accepts_only_local_files() -> None:
    assert cli_inputs.CLI_INPUT_POLICY.accepted_schemes == ("file",)
    assert cli_inputs.CLI_INPUT_POLICY.max_bytes == 10_485_760


def test_run_dispatches_an_input_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: list[WorkflowRunInput | WorkflowInputFile | None] = []

    def fake_run_workflow(
        workflow_id: UUID,
        *,
        workflow_input: WorkflowRunInput | WorkflowInputFile | None,
        output: WorkflowOutputFormat,
        sensitivity: Sensitivity | None = None,
    ) -> int:
        received.append(workflow_input)

        return 0

    monkeypatch.setattr(cli_application, "run_workflow", fake_run_workflow)

    path = tmp_path / "words.data"

    assert (
        main(
            (
                "workflow",
                "run",
                str(WORKFLOW_ID),
                "--input-file",
                str(path),
                "--media-type",
                "text/plain",
            )
        )
        == 0
    )

    assert received == [WorkflowInputFile(path=path, media_type="text/plain")]


def test_invoke_dispatches_an_input_file_as_its_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: list[object] = []

    def fake_invoke_workflow(
        *,
        workflow_id: UUID,
        payload: object,
        output: WorkflowOutputFormat,
        idempotency_key: str | None = None,
        sensitivity: Sensitivity | None = None,
    ) -> int:
        assert idempotency_key is None

        received.append(payload)

        return 0

    monkeypatch.setattr(cli_application, "invoke_workflow", fake_invoke_workflow)

    path = tmp_path / "words.txt"

    assert main(("workflow", "invoke", str(WORKFLOW_ID), "--input-file", str(path))) == 0

    assert received == [WorkflowInputFile(path=path)]


@pytest.mark.parametrize("action", ["run", "invoke"])
def test_input_and_input_file_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    action: str,
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                action,
                str(WORKFLOW_ID),
                "--input",
                '"text"',
                "--input-file",
                str(tmp_path / "words.txt"),
            )
        )

    assert raised.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_invoke_requires_one_of_its_inputs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("workflow", "invoke", str(WORKFLOW_ID)))

    errors = capsys.readouterr().err

    assert raised.value.code == 2
    assert "--input" in errors
    assert "--input-file" in errors


@pytest.mark.parametrize("action", ["run", "invoke"])
def test_an_unsupported_media_type_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    action: str,
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                action,
                str(WORKFLOW_ID),
                "--input-file",
                str(tmp_path / "animation.gif"),
                "--media-type",
                "image/gif",
            )
        )

    assert raised.value.code == 2
    assert "Media type 'image/gif' is not supported" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["run", "invoke"])
def test_a_media_type_needs_an_input_file(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    status, output, errors = run_status(
        capsys,
        "workflow",
        action,
        str(WORKFLOW_ID),
        "--input",
        '"text"',
        "--media-type",
        "text/plain",
    )

    assert (status, output, errors) == (1, "", "--media-type requires --input-file.\n")


def test_run_reads_a_text_file_as_its_input(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.txt", CONTENT)

    from_file = run_cli(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
        "--output",
        "result",
    )
    inline = run_cli(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input",
        json.dumps(TEXT),
        "--output",
        "result",
    )

    assert from_file == inline == "4\n"


def test_run_records_the_file_input_and_its_provenance(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.txt", CONTENT)

    run_cli(capsys, "workflow", "run", str(WORKFLOW_ID), "--input-file", str(path))

    context = initial_context(database)

    assert [event.event_type for event in context.events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    ]
    assert context.events[0].payload == {"input": TEXT}
    assert context.events[1].payload == resolved_payload(path, "text/plain")


def test_run_stores_the_file_content_by_its_digest(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.txt", CONTENT)

    run_cli(capsys, "workflow", "run", str(WORKFLOW_ID), "--input-file", str(path))

    assert SQLiteContentStore(database).get(content_bytes_digest(CONTENT)) == CONTENT


def test_an_inline_run_records_no_provenance(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "run", str(WORKFLOW_ID), "--input", json.dumps(TEXT))

    assert [event.event_type for event in initial_context(database).events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
    ]


def test_run_parses_a_json_file(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = json.dumps(TEXT).encode()
    path = write(tmp_path / "words.json", content)

    output = run_cli(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
        "--output",
        "result",
    )

    assert output == "4\n"
    assert initial_context(database).events[1].payload == resolved_payload(
        path,
        "application/json",
        content,
    )


def test_run_reads_an_unknown_extension_with_a_media_type(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.data", CONTENT)

    output = run_cli(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
        "--media-type",
        "text/plain",
        "--output",
        "result",
    )

    assert output == "4\n"


def test_run_refuses_an_unknown_extension_without_a_media_type(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.data", CONTENT)

    status, output, errors = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output) == (1, "")
    assert errors == (
        f"Cannot tell the media type of {path} from its extension; give it with --media-type.\n"
    )
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID) == ()


def test_run_refuses_a_missing_file_and_starts_no_run(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "missing.txt"

    status, output, errors = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output, errors) == (1, "", f"Input {file_uri(path)} does not exist.\n")
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID) == ()


def test_run_refuses_invalid_json_and_stores_nothing(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.json", b"{not json")

    status, output, errors = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output) == (1, "")
    assert errors.startswith(f"Input {file_uri(path)}: Content is not valid JSON")
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID) == ()
    assert not SQLiteContentStore(database).contains(content_bytes_digest(b"{not json"))


def test_run_refuses_a_file_over_the_cap(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli_inputs,
        "CLI_INPUT_POLICY",
        InputPolicy(resolvers={"file": FileInputResolver()}, max_bytes=4),
    )

    path = write(tmp_path / "words.txt", CONTENT)

    status, output, errors = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output) == (1, "")
    assert errors == f"Input {file_uri(path)} is larger than the limit of 4 bytes.\n"


def test_invoke_reads_a_file_and_records_its_provenance(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))

    path = write(tmp_path / "words.md", CONTENT)

    from_file = run_cli(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
        "--output",
        "result",
    )
    inline = run_cli(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input",
        json.dumps(TEXT),
        "--output",
        "result",
    )

    assert from_file == inline

    first, second = SQLiteProductionInvocationRepository(database).invocations_for_workflow(
        WORKFLOW_ID,
    )

    assert [event.event_type for event in first.initial_context.events] == [
        PRODUCTION_INVOCATION_EVENT_TYPE,
        WORKFLOW_INPUT_EVENT_TYPE,
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    ]
    assert first.initial_context.events[0].payload == {"input": TEXT}
    assert first.initial_context.events[1].payload == {"input": TEXT}
    assert first.initial_context.events[2].payload == resolved_payload(path, "text/markdown")

    assert [event.event_type for event in second.initial_context.events] == [
        PRODUCTION_INVOCATION_EVENT_TYPE,
        WORKFLOW_INPUT_EVENT_TYPE,
    ]


def test_invoke_refuses_a_missing_file_and_records_no_invocation(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))

    path = tmp_path / "missing.txt"

    status, output, errors = run_status(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output, errors) == (1, "", f"Input {file_uri(path)} does not exist.\n")
    assert (
        SQLiteProductionInvocationRepository(database).invocations_for_workflow(
            WORKFLOW_ID,
        )
        == ()
    )


PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def test_run_gives_a_pdf_file_to_the_workflow_as_a_content_handle(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "claim.pdf", PDF)

    run_status(capsys, "workflow", "run", str(WORKFLOW_ID), "--input-file", str(path))

    context = initial_context(database)
    digest = content_bytes_digest(PDF)

    assert context.events[0].payload == {
        "input": {
            "content": {
                "digest": digest,
                "media_type": "application/pdf",
                "size_bytes": len(PDF),
            }
        }
    }
    assert context.events[1].payload == resolved_payload(path, "application/pdf", PDF)
    assert SQLiteContentStore(database).get(digest) == PDF


def test_run_refuses_a_file_that_is_not_what_its_extension_says(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "claim.pdf", CONTENT)

    status, output, errors = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
    )

    assert (status, output, errors) == (
        1,
        "",
        f"Input {file_uri(path)}: Content is not application/pdf: "
        "no PDF header in its first 1024 bytes.\n",
    )
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID) == ()
    assert not SQLiteContentStore(database).contains(content_bytes_digest(CONTENT))


def test_the_media_type_help_names_every_accepted_media_type(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(("workflow", "run", "--help"))

    help_text = " ".join(capsys.readouterr().out.split())

    assert "Workflow input read from a JSON, text, PDF or image file." in help_text
    assert (
        "Media type of --input-file: application/json, a text/* type, application/pdf, "
        "image/jpeg, image/png or image/webp." in help_text
    )


# Labelling the input (ADR 0123)


def labels_of(
    context: Context,
) -> list[object]:
    """Return the labels a context's sensitivity events record."""

    return [
        event.payload["sensitivity"]
        for event in context.events
        if event.event_type == INPUT_SENSITIVITY_EVENT_TYPE
    ]


def test_run_records_the_label_given_to_its_json_input(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, _ = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input",
        json.dumps(TEXT),
        "--sensitivity",
        "restricted",
        "--output",
        "result",
    )

    context = initial_context(database)

    assert status == 0
    assert labels_of(context) == ["restricted"]
    assert context_sensitivity(context) is Sensitivity.RESTRICTED


def test_run_records_the_label_given_to_its_file_input(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write(tmp_path / "words.md", CONTENT)

    status, _, _ = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--input-file",
        str(path),
        "--sensitivity",
        "public",
        "--output",
        "result",
    )

    assert status == 0
    assert [event.event_type for event in initial_context(database).events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
        INPUT_SENSITIVITY_EVENT_TYPE,
    ]
    assert labels_of(initial_context(database)) == ["public"]


def test_run_without_a_label_records_none(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_status(capsys, "workflow", "run", str(WORKFLOW_ID), "--input", json.dumps(TEXT))

    assert labels_of(initial_context(database)) == []


def test_a_label_without_input_starts_no_run(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = run_status(
        capsys,
        "workflow",
        "run",
        str(WORKFLOW_ID),
        "--sensitivity",
        "restricted",
    )

    assert (status, out) == (1, "")
    assert err == f"{SENSITIVITY_WITHOUT_INPUT_MESSAGE}\n"
    assert err == "--sensitivity labels the run's input; give --input or --input-file too.\n"
    assert SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID) == ()


def test_an_unknown_label_is_a_usage_error(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(("workflow", "run", str(WORKFLOW_ID), "--input", "1", "--sensitivity", "secret"))

    assert exited.value.code == 2
    assert "'secret' is not a sensitivity; choose public, internal, restricted." in (
        capsys.readouterr().err
    )


def test_invoke_records_the_label_given_to_its_input(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))

    path = write(tmp_path / "words.md", CONTENT)

    for arguments in (
        ("--input", json.dumps(TEXT)),
        ("--input-file", str(path)),
    ):
        status, _, _ = run_status(
            capsys,
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            *arguments,
            "--sensitivity",
            "restricted",
            "--output",
            "result",
        )

        assert status == 0

    from_json, from_file = SQLiteProductionInvocationRepository(database).invocations_for_workflow(
        WORKFLOW_ID
    )

    assert labels_of(from_json.initial_context) == ["restricted"]
    assert labels_of(from_file.initial_context) == ["restricted"]

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert {context_sensitivity(run.initial_context) for run in runs} == {Sensitivity.RESTRICTED}


def test_a_keyed_invoke_makes_the_label_part_of_its_request(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))

    def invoke(
        *labels: str,
    ) -> tuple[int, str, str]:
        return run_status(
            capsys,
            "workflow",
            "invoke",
            str(WORKFLOW_ID),
            "--input",
            json.dumps(TEXT),
            "--idempotency-key",
            "claim-412",
            *labels,
            "--output",
            "result",
        )

    first, _, _ = invoke("--sensitivity", "restricted")
    conflict, _, err = invoke()

    (invocation,) = SQLiteProductionInvocationRepository(database).invocations_for_workflow(
        WORKFLOW_ID,
    )

    assert first == 0
    assert labels_of(invocation.initial_context) == ["restricted"]
    assert conflict == 1
    assert "claim-412" in err


def test_keyed_request_carries_the_label_on_its_source() -> None:
    request = keyed_request(
        workflow_id=WORKFLOW_ID,
        payload={"claim": 412},
        idempotency_key="claim-412",
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert request.input.sensitivity is Sensitivity.RESTRICTED
    assert keyed_request(
        workflow_id=WORKFLOW_ID,
        payload={"claim": 412},
        idempotency_key="claim-412",
    ).input.model_dump(mode="json") == {"value": {"claim": 412}, "media_type": "application/json"}


def test_the_label_option_is_described_in_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for action in ("run", "invoke"):
        with pytest.raises(SystemExit):
            main(("workflow", action, "--help"))

        assert "--sensitivity LABEL" in capsys.readouterr().out


def test_the_documented_label_refusal_is_the_one_given() -> None:
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

    assert f"\n{SENSITIVITY_WITHOUT_INPUT_MESSAGE}\n" in readme.read_text(encoding="utf-8")
