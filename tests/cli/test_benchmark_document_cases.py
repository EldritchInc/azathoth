"""Tests that a benchmark case holds a document, and its run reads it (ADR 0117).

A PDF becomes a case from the run it was given to, or straight from its
file. The case's run receives it as that run did, so `segment_pdf` reads it
and a cited step is shown the extraction a step of the case's run kept.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import main
from azathoth.cli.benchmark_execution import case_runner
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.inputs import InputProvenance, content_bytes_digest, file_uri
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import CITATIONS_RESOURCE_KIND
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import SOURCE_URI_METADATA_KEY, journaled_citations
from tests.cli.test_cited_invocation import (
    MODEL,
    PDF,
    PROVIDER,
    REPLY,
    WORKFLOW_ID,
    cited_workflow,
)

BENCHMARK_ID = "c1670000-0000-4000-8000-000000000001"

MISSING_CASE_ID = "c1670000-0000-4000-8000-000000000002"

MISSING_PDF = b"%PDF-1.7\n% never kept\n%%EOF\n"


def handle(
    content: bytes,
) -> dict[str, JsonValue]:
    """Return the handle of some PDF content."""

    return {
        "content": {
            "digest": content_bytes_digest(content),
            "media_type": "application/pdf",
            "size_bytes": len(content),
        }
    }


def benchmark(
    *cases: BenchmarkCase,
) -> str:
    """Return a benchmark document holding some cases."""

    return BenchmarkDataset(
        id=UUID(BENCHMARK_ID),
        name="claims",
        description="When each claim was received.",
        cases=cases,
    ).model_dump_json()


def run(
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database with the cited workflow, an empty benchmark and a citing model."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(ModelMetadata(provider=PROVIDER, model=MODEL, display_name=MODEL),)
        ),
    )
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                f"{PROVIDER}/{MODEL}": DeterministicLanguageModel(
                    provider=PROVIDER,
                    model=MODEL,
                    response_text=json.dumps(REPLY),
                )
            }
        ),
    )

    workflow: dict[str, Any] = cited_workflow().model_dump(mode="json")
    workflow["result"] = {"name": "answer"}

    (tmp_path / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
    (tmp_path / "benchmark.json").write_text(benchmark(), encoding="utf-8")
    (tmp_path / "claim.pdf").write_bytes(PDF)

    for arguments in (
        ("init",),
        ("workflow", "import", "workflow.json"),
        ("benchmark", "import", "benchmark.json"),
    ):
        status, _, err = run(*arguments, capsys=capsys)

        assert status == 0, err

    return path


def answered(
    capsys: pytest.CaptureFixture[str],
) -> tuple[UUID, JsonValue]:
    """Run the workflow on the claim's PDF; return the run's ID and its result."""

    status, out, err = run(
        "workflow",
        "run",
        WORKFLOW_ID,
        "--input-file",
        "claim.pdf",
        "--output",
        "jsonl",
        capsys=capsys,
    )

    assert status == 0, err

    record = json.loads(out.strip().splitlines()[-1])

    return UUID(record["run_id"]), record["value"]


def cases(
    database: Path,
) -> tuple[BenchmarkCase, ...]:
    """Return the benchmark's cases, as its latest revision holds them."""

    dataset = open_repositories(database).benchmarks.get(UUID(BENCHMARK_ID))

    assert dataset is not None

    return dataset.cases


def test_a_run_given_a_pdf_becomes_a_case_holding_its_handle_and_provenance(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id, result = answered(capsys)

    status, out, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--from-run",
        str(run_id),
        "--comparison",
        "exact",
        "--expected",
        json.dumps(result),
        capsys=capsys,
    )

    assert status == 0, err
    assert out.startswith("Added benchmark case ")

    (case,) = cases(database)

    assert case.input == handle(PDF)
    assert case.input_provenance == InputProvenance(
        uri=file_uri(tmp_path / "claim.pdf"),
        media_type="application/pdf",
        size_bytes=len(PDF),
        digest=content_bytes_digest(PDF),
    )


def test_a_pdf_file_becomes_a_case_and_its_content_is_kept(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "other.pdf").write_bytes(MISSING_PDF)

    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--input-file",
        "other.pdf",
        "--comparison",
        "exact",
        "--expected",
        '{"received": "December 14"}',
        capsys=capsys,
    )

    assert status == 0, err

    (case,) = cases(database)
    uri = file_uri(tmp_path / "other.pdf")

    assert case.input == handle(MISSING_PDF)
    assert case.input_provenance is not None
    assert case.input_provenance.uri == uri
    assert case.expected.description == f"Added from {uri}."
    assert case.metadata == {SOURCE_URI_METADATA_KEY: uri}
    assert open_repositories(database).content.get(content_bytes_digest(MISSING_PDF)) == (
        MISSING_PDF
    )


def test_a_file_with_a_given_media_type_becomes_a_case_of_that_type(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "claim.bin").write_bytes(PDF)

    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--input-file",
        "claim.bin",
        "--media-type",
        "application/pdf",
        "--comparison",
        "exact",
        "--expected",
        "1",
        capsys=capsys,
    )

    assert status == 0, err
    assert cases(database)[0].input == handle(PDF)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(
            ("--input-file", "claim.pdf"),
            "A case read from --input-file needs --expected.\n",
            id="no-expected",
        ),
        pytest.param(
            ("--input-file", "claim.unknown", "--expected", "1"),
            "Cannot tell the media type of claim.unknown from its extension; give it with "
            "--media-type.\n",
            id="unknown-media-type",
        ),
        pytest.param(
            ("--from-run", "c1670000-0000-4000-8000-000000000009", "--media-type", "text/plain"),
            "--media-type requires --input-file.\n",
            id="media-type-without-file",
        ),
    ],
)
def test_a_case_that_cannot_be_read_from_a_file_is_refused_and_nothing_is_added(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
    message: str,
) -> None:
    status, out, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        *arguments,
        "--comparison",
        "exact",
        capsys=capsys,
    )

    assert (status, out, err) == (1, "", message)
    assert cases(database) == ()


def test_a_run_whose_content_the_store_no_longer_holds_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _ = answered(capsys)

    monkeypatch.setattr(
        "azathoth.persistence.repositories.SQLiteContentStore.contains",
        lambda self, digest: False,
    )

    status, out, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--from-run",
        str(run_id),
        "--comparison",
        "exact",
        "--expected",
        "1",
        capsys=capsys,
    )

    assert (status, out) == (1, "")
    assert err == (
        f"Run {run_id} received content {content_bytes_digest(PDF)}, which the content "
        "store no longer holds.\n"
    )
    assert cases(database) == ()


def test_a_run_given_a_json_file_needs_no_content_kept_to_become_a_case(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "input.json").write_text('{"text": "the old ones wait"}', encoding="utf-8")

    status, out, err = run(
        "workflow",
        "run",
        WORKFLOW_ID,
        "--input-file",
        "input.json",
        "--output",
        "jsonl",
        capsys=capsys,
    )
    run_id = json.loads(out.strip().splitlines()[0])["run_id"]

    monkeypatch.setattr(
        "azathoth.persistence.repositories.SQLiteContentStore.contains",
        lambda self, digest: False,
    )

    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--from-run",
        run_id,
        "--comparison",
        "exact",
        "--expected",
        "1",
        capsys=capsys,
    )

    assert status == 0, err

    (case,) = cases(database)

    assert case.input == {"text": "the old ones wait"}
    assert case.input_provenance is not None
    assert case.input_provenance.media_type == "application/json"


def test_a_document_case_runs_as_its_run_did_and_one_whose_content_is_gone_fails(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id, result = answered(capsys)

    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--from-run",
        str(run_id),
        "--comparison",
        "exact",
        "--expected",
        json.dumps(result),
        capsys=capsys,
    )

    assert status == 0, err

    (kept,) = cases(database)
    missing = BenchmarkCase(
        id=UUID(MISSING_CASE_ID),
        input=handle(MISSING_PDF),
        input_provenance=InputProvenance(
            uri="file:///claims/gone.pdf",
            media_type="application/pdf",
            size_bytes=len(MISSING_PDF),
            digest=content_bytes_digest(MISSING_PDF),
        ),
        expected=ExpectedOutcome(
            description="Gone.", value=result, comparison=OutcomeComparison.EXACT
        ),
    )

    (tmp_path / "benchmark.json").write_text(benchmark(kept, missing), encoding="utf-8")

    status, _, err = run("benchmark", "import", "benchmark.json", capsys=capsys)

    assert status == 0, err

    status, out, err = run(
        "benchmark", "run", BENCHMARK_ID, "--workflow", WORKFLOW_ID, capsys=capsys
    )

    assert status == 0, err
    assert "Cases Run: 2\nCases Passed: 1\n" in out
    assert "Run failures: 1\n" in out

    repositories = open_repositories(database)
    case_runs = [
        recorded
        for recorded in repositories.runs.runs()
        if recorded.id != run_id and recorded.workflow.id == UUID(WORKFLOW_ID)
    ]
    passed = next(recorded for recorded in case_runs if recorded.failed_step_count == 0)
    failed = next(recorded for recorded in case_runs if recorded.failed_step_count > 0)

    assert len(case_runs) == 2
    assert (
        f"Content {content_bytes_digest(MISSING_PDF)} is not in the content store."
        in failed.model_dump_json()
    )
    cited = passed.steps[1].execution

    assert cited is not None

    (record,) = (
        resource for resource in cited.resources if resource.kind == CITATIONS_RESOURCE_KIND
    )

    assert record.attributes["verified"] == 1
    assert journaled_citations(repositories.run_journal, passed.id) == (
        (passed.steps[1].step_id, record.identifier),
    )
    assert kept.input_provenance is not None
    assert passed.initial_context.events[1].payload == kept.input_provenance.model_dump(mode="json")


HAND_WRITTEN = {
    "received": "December 14",
    "citations": [
        {"source": "claim", "segment": "p1.s2"},
        {"source": "claim", "segment": "p2.s1"},
    ],
}
"""The answer the cited step gives, written by hand: each citation by its segment."""


def cited_case(
    capsys: pytest.CaptureFixture[str],
    *options: str,
) -> UUID:
    """Add a case from a run on the claim's PDF, naming some citation options; return the run."""

    run_id, _ = answered(capsys)

    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--from-run",
        str(run_id),
        "--comparison",
        "exact",
        "--expected",
        json.dumps(HAND_WRITTEN),
        *options,
        capsys=capsys,
    )

    assert status == 0, err

    return run_id


@pytest.mark.parametrize(
    ("options", "passed"),
    [
        pytest.param(
            ("--require-citation", "claim:p1.s2", "--on-unverified", "ignore"), 1, id="met"
        ),
        pytest.param(("--require-citation", "claim:p1.s2"), 0, id="an-unverified-citation"),
        pytest.param(
            ("--require-citation", "claim:p2.s1", "--on-unverified", "ignore"), 0, id="missing"
        ),
        pytest.param((), 1, id="no-expectation"),
    ],
)
def test_a_cited_case_is_judged_by_its_answer_and_the_checks_its_run_kept(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    options: tuple[str, ...],
    passed: int,
) -> None:
    cited_case(capsys, *options)

    status, out, err = run(
        "benchmark", "run", BENCHMARK_ID, "--workflow", WORKFLOW_ID, capsys=capsys
    )

    assert status == 0, err
    assert f"Cases Run: 1\nCases Passed: {passed}\n" in out
    assert "Run failures: 0\n" in out


def test_a_cited_case_names_its_citations_and_provenance_when_shown(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cited_case(capsys, "--require-citation", "claim:p1.s2", "--require-citation", "claim:p2.s1")

    (case,) = cases(database)

    assert case.expected.citations is not None
    assert [(cited.source, cited.segment) for cited in case.expected.citations.require] == [
        ("claim", "p1.s2"),
        ("claim", "p2.s1"),
    ]

    status, out, err = run("benchmark", "case-show", BENCHMARK_ID, str(case.id), capsys=capsys)

    assert status == 0, err
    assert "Input Provenance:\n" in out
    assert f'"uri": "{file_uri(tmp_path / "claim.pdf")}"' in out
    assert (
        "  Comparison: exact\n"
        "  Citations:\n"
        "    Require: claim p1.s2\n"
        "    Require: claim p2.s1\n"
        "    On Unverified: fail\n"
    ) in out

    status, out, err = run("benchmark", "show", BENCHMARK_ID, capsys=capsys)

    assert status == 0, err
    assert "Cases: 1\nCited Cases: 1\n" in out


def test_a_case_naming_only_a_policy_requires_no_segment(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cited_case(capsys, "--on-unverified", "ignore")

    (case,) = cases(database)

    assert case.expected.citations is not None
    assert (case.expected.citations.require, case.expected.citations.on_unverified) == (
        (),
        "ignore",
    )


def test_a_case_naming_no_citations_shows_none(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--input-file",
        "claim.pdf",
        "--comparison",
        "exact",
        "--expected",
        "1",
        capsys=capsys,
    )

    assert status == 0, err

    (case,) = cases(database)
    status, out, _ = run("benchmark", "case-show", BENCHMARK_ID, str(case.id), capsys=capsys)

    assert "Citations:" not in out
    assert case.expected.citations is None

    status, out, _ = run("benchmark", "show", BENCHMARK_ID, capsys=capsys)

    assert "Cited Cases:" not in out


def test_a_segment_required_twice_is_refused_and_nothing_is_added(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = run(
        "benchmark",
        "add-case",
        BENCHMARK_ID,
        "--input-file",
        "claim.pdf",
        "--comparison",
        "exact",
        "--expected",
        "1",
        "--require-citation",
        "claim:p1.s2",
        "--require-citation",
        "claim:p1.s2",
        capsys=capsys,
    )

    assert (status, out) == (1, "")
    assert err == (
        "Citation expectation requires segment p1.s2 of source 'claim' more than once.\n"
    )
    assert cases(database) == ()


@pytest.mark.parametrize("value", ["claim", ":p1.s2", "claim:"])
def test_a_required_citation_names_a_source_and_a_segment(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "benchmark",
                "add-case",
                BENCHMARK_ID,
                "--input-file",
                "claim.pdf",
                "--comparison",
                "exact",
                "--require-citation",
                value,
            )
        )

    assert raised.value.code == 2
    assert (
        f"Expected SOURCE:SEGMENT, such as claim:p1.s2, got {value!r}." in capsys.readouterr().err
    )


OTHER_WORKFLOW_ID = "c1670000-0000-4000-8000-000000000003"


def test_compared_document_workflows_are_scored_on_the_citations_their_runs_kept(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cited_case(capsys)

    other: dict[str, Any] = cited_workflow().model_dump(mode="json")
    other["metadata"]["id"] = OTHER_WORKFLOW_ID
    other["metadata"]["name"] = "answer from a claim, again"
    other["result"] = {"name": "answer"}

    (tmp_path / "other.json").write_text(json.dumps(other), encoding="utf-8")

    status, _, err = run("workflow", "import", "other.json", capsys=capsys)

    assert status == 0, err

    status, out, err = run(
        "benchmark",
        "compare",
        BENCHMARK_ID,
        "--workflow",
        WORKFLOW_ID,
        "--workflow",
        OTHER_WORKFLOW_ID,
        "--target-latency",
        "60",
        "--target-cost",
        "1",
        capsys=capsys,
    )

    assert status == 0, err
    assert out.count("Cost: 1.000000\nCitations: 0.500000\nOverall: ") == 2


def test_benchmark_cases_run_with_the_databases_journal_children_and_content(
    database: Path,
) -> None:
    repositories = open_repositories(database)
    runner = case_runner(repositories)

    assert runner.children is repositories.run_children
    assert runner.content is repositories.tool_content
