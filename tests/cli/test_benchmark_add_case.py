"""Tests for appending benchmark cases from recorded runs through the CLI."""

from argparse import Namespace
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

import azathoth.cli.application as cli_application
import azathoth.cli.bootstrap as bootstrap
from azathoth.cli import (
    SuppliedExpectedValue,
    add_benchmark_case,
    build_parser,
    main,
)
from azathoth.cli.dispatching import dispatch_benchmark_command
from azathoth.cli.parsing import BENCHMARK_CASE_EXPECTED_ATTRIBUTE
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.workflows import (
    SOURCE_FEEDBACK_METADATA_KEY,
    SOURCE_RUN_METADATA_KEY,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowRun,
    WorkflowRunFeedback,
)
from tests.cli.test_workflow_run import configure_database
from tests.workflows.test_benchmark_case_source import (
    FIRST_FEEDBACK_ID,
    INPUT,
    RUN_ID,
    SECOND_FEEDBACK_ID,
    bad_feedback,
    create_run,
    good_feedback,
    input_event,
)

BENCHMARK_ID = UUID("99999999-9999-9999-9999-999999999991")
UNKNOWN_BENCHMARK_ID = UUID("99999999-9999-9999-9999-999999999992")
EXISTING_CASE_ID = UUID("99999999-9999-9999-9999-999999999993")
UNKNOWN_RUN_ID = UUID("99999999-9999-9999-9999-999999999994")


def create_dataset() -> BenchmarkDataset:
    """Create one benchmark dataset whose single case does not replay the run."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="Word count",
        description="Count words.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=EXISTING_CASE_ID,
                input={"text": "that is not dead"},
                expected=ExpectedOutcome(
                    description="Four words.",
                    value=4,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def forbid_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail the test if any part of runtime bootstrap is reached."""

    def fail(
        *_arguments: object,
        **_keywords: object,
    ) -> object:
        raise AssertionError("Runtime must not be loaded.")

    for name in (
        "load_runtime",
        "_load_current_models",
        "_load_language_models",
    ):
        monkeypatch.setattr(
            bootstrap,
            name,
            fail,
        )


def configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    run: WorkflowRun | None = None,
    feedback: tuple[WorkflowRunFeedback, ...] = (),
) -> Path:
    """Save one benchmark, one run, and its feedback in an isolated database."""

    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    forbid_runtime(monkeypatch)

    SQLiteBenchmarkRepository(database).save(create_dataset())

    SQLiteWorkflowRunRepository(database).save(
        run if run is not None else create_run(input_event()),
    )

    feedback_repository = SQLiteWorkflowRunFeedbackRepository(database)

    for record in feedback:
        feedback_repository.save(record)

    return database


def revisions(
    database: Path,
) -> int:
    """Return how many revisions the benchmark has."""

    return len(SQLiteBenchmarkRepository(database).revisions(BENCHMARK_ID))


def added_case(
    database: Path,
) -> BenchmarkCase:
    """Return the last case of the benchmark's latest revision."""

    dataset = SQLiteBenchmarkRepository(database).get(BENCHMARK_ID)

    assert dataset is not None

    return dataset.cases[-1]


def test_add_case_appends_a_revision_with_the_supplied_expected_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert revisions(database) == 2

    latest = SQLiteBenchmarkRepository(database).latest_revision(BENCHMARK_ID)

    assert latest is not None
    assert latest.number == 2

    dataset = latest.dataset

    assert tuple(case.id for case in dataset.cases)[0] == EXISTING_CASE_ID
    assert len(dataset.cases) == 2

    case = dataset.cases[-1]

    assert captured.out == (
        f"Added benchmark case {case.id} to benchmark dataset {BENCHMARK_ID} revision 2.\n"
    )

    assert case.input == INPUT
    assert case.expected.value == 4
    assert case.expected.comparison is OutcomeComparison.EXACT
    assert case.expected.description == f"Added from run {RUN_ID}."
    assert case.metadata == {
        SOURCE_RUN_METADATA_KEY: str(RUN_ID),
    }


def test_add_case_keeps_the_dataset_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    capsys.readouterr()

    dataset = SQLiteBenchmarkRepository(database).get(BENCHMARK_ID)

    assert dataset is not None
    assert dataset.version == "1.0.0"


def test_add_case_leaves_the_earlier_revision_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    capsys.readouterr()

    first = SQLiteBenchmarkRepository(database).revision(BENCHMARK_ID, 1)

    assert first is not None
    assert first.dataset == create_dataset()


def test_add_case_uses_a_supplied_description(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
        description="Four words.",
    )

    capsys.readouterr()

    assert added_case(database).expected.description == "Four words."


def test_add_case_accepts_a_supplied_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=None,
        ),
    )

    capsys.readouterr()

    assert result == 0
    assert added_case(database).expected.value is None


def test_add_case_takes_the_latest_corrected_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        feedback=(
            bad_feedback(
                FIRST_FEEDBACK_ID,
                corrected=3,
                minutes=5,
            ),
            bad_feedback(
                SECOND_FEEDBACK_ID,
                corrected=4,
                minutes=10,
            ),
        ),
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
    )

    capsys.readouterr()

    assert result == 0

    case = added_case(database)

    assert case.expected.value == 4
    assert case.metadata == {
        SOURCE_RUN_METADATA_KEY: str(RUN_ID),
        SOURCE_FEEDBACK_METADATA_KEY: str(SECOND_FEEDBACK_ID),
    }


def test_add_case_ignores_good_feedback_after_a_correction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        feedback=(
            bad_feedback(
                FIRST_FEEDBACK_ID,
                corrected=4,
                minutes=5,
            ),
            good_feedback(
                SECOND_FEEDBACK_ID,
                minutes=10,
            ),
        ),
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
    )

    capsys.readouterr()

    assert result == 0
    assert added_case(database).metadata[SOURCE_FEEDBACK_METADATA_KEY] == str(FIRST_FEEDBACK_ID)


def test_add_case_supplied_value_wins_over_feedback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        feedback=(
            bad_feedback(
                FIRST_FEEDBACK_ID,
                corrected=3,
                minutes=5,
            ),
        ),
    )

    add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    capsys.readouterr()

    case = added_case(database)

    assert case.expected.value == 4
    assert SOURCE_FEEDBACK_METADATA_KEY not in case.metadata


def assert_rejected(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    result: int,
    message: str,
) -> None:
    """Require one rejection on stderr that wrote nothing."""

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"{message}\n"

    assert revisions(database) == 1


def test_add_case_rejects_an_unconfigured_benchmark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        UNKNOWN_BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Benchmark dataset {UNKNOWN_BENCHMARK_ID} is not configured.",
    )

    assert SQLiteBenchmarkRepository(database).revisions(UNKNOWN_BENCHMARK_ID) == ()


def test_add_case_rejects_an_unknown_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=UNKNOWN_RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Run {UNKNOWN_RUN_ID} was not found.",
    )


def test_add_case_rejects_a_run_without_input_before_reading_feedback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        run=create_run(),
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Run {RUN_ID} did not receive workflow input.",
    )


def test_add_case_rejects_a_run_with_repeated_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        run=create_run(
            input_event(),
            input_event({"text": "again"}),
        ),
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Run {RUN_ID} received workflow input more than once.",
    )


def test_add_case_rejects_a_run_without_feedback_or_expected_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Run {RUN_ID} has no corrected output; pass --expected.",
    )


def test_add_case_rejects_a_run_judged_good_without_a_correction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        feedback=(
            good_feedback(
                FIRST_FEEDBACK_ID,
                minutes=5,
            ),
            bad_feedback(
                SECOND_FEEDBACK_ID,
                corrected=None,
                minutes=10,
            ),
        ),
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
    )

    assert_rejected(
        database,
        capsys,
        result,
        f"Run {RUN_ID} has no corrected output; pass --expected.",
    )


def test_add_case_rejects_a_value_that_is_not_a_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.SCHEMA,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    assert_rejected(
        database,
        capsys,
        result,
        "Expected value cannot be used with comparison 'schema': "
        "A JSON Schema must be an object or a boolean.",
    )


def test_add_case_accepts_semantic_comparison_without_configured_judges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.SEMANTIC,
        expected=SuppliedExpectedValue(
            value="four words",
        ),
    )

    capsys.readouterr()

    assert result == 0
    assert added_case(database).expected.comparison is OutcomeComparison.SEMANTIC


def test_add_case_rejects_an_equivalent_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    first = capsys.readouterr()

    assert first.err == ""

    existing = added_case(database)

    result = add_benchmark_case(
        BENCHMARK_ID,
        run_id=RUN_ID,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(
            value=4,
        ),
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        f"Benchmark dataset {BENCHMARK_ID} already contains case {existing.id} "
        "with this input and expected outcome.\n"
    )

    assert revisions(database) == 2


def test_add_case_accepts_the_same_input_with_another_expected_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
    )

    for value in ("four words", "4 words"):
        assert (
            add_benchmark_case(
                BENCHMARK_ID,
                run_id=RUN_ID,
                comparison=OutcomeComparison.SEMANTIC,
                expected=SuppliedExpectedValue(
                    value=value,
                ),
            )
            == 0
        )

    capsys.readouterr()

    assert revisions(database) == 3


def test_cli_add_case_end_to_end_without_loading_the_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        monkeypatch,
        tmp_path,
        feedback=(
            bad_feedback(
                FIRST_FEEDBACK_ID,
                corrected=4,
                minutes=5,
            ),
        ),
    )

    result = main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "exact",
            "--description",
            "Four words.",
        )
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    case = added_case(database)

    assert captured.out == (
        f"Added benchmark case {case.id} to benchmark dataset {BENCHMARK_ID} revision 2.\n"
    )
    assert case.expected.value == 4
    assert case.expected.description == "Four words."


def capture_add_case(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    """Replace the add-case handler with one that records its request."""

    calls: list[dict[str, object]] = []

    def fake_add_benchmark_case(
        benchmark_id: UUID,
        *,
        run_id: UUID,
        comparison: OutcomeComparison,
        expected: SuppliedExpectedValue | None,
        description: str | None,
    ) -> int:
        calls.append(
            {
                "benchmark_id": benchmark_id,
                "run_id": run_id,
                "comparison": comparison,
                "expected": expected,
                "description": description,
            }
        )

        return 23

    monkeypatch.setattr(
        cli_application,
        "add_benchmark_case",
        fake_add_benchmark_case,
    )

    return calls


def test_cli_add_case_dispatches_the_complete_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_add_case(monkeypatch)

    result = main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "semantic",
            "--expected",
            '{"count": 4}',
            "--description",
            "Four words.",
        )
    )

    assert result == 23

    expected_value: JsonValue = {"count": 4}

    assert calls == [
        {
            "benchmark_id": BENCHMARK_ID,
            "run_id": RUN_ID,
            "comparison": OutcomeComparison.SEMANTIC,
            "expected": SuppliedExpectedValue(
                value=expected_value,
            ),
            "description": "Four words.",
        },
    ]


def test_cli_add_case_dispatches_supplied_null_as_an_expected_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_add_case(monkeypatch)

    main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "exact",
            "--expected",
            "null",
        )
    )

    assert calls[0]["expected"] == SuppliedExpectedValue(
        value=None,
    )


def test_cli_add_case_dispatches_no_expected_value_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_add_case(monkeypatch)

    main(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "exact",
        )
    )

    assert calls[0]["expected"] is None
    assert calls[0]["description"] is None


def test_add_case_parser_omits_expected_value_unless_given() -> None:
    arguments = build_parser().parse_args(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "exact",
        )
    )

    assert not hasattr(
        arguments,
        BENCHMARK_CASE_EXPECTED_ATTRIBUTE,
    )


def test_add_case_dispatch_converts_the_comparison() -> None:
    received: list[OutcomeComparison] = []

    def add_case(
        benchmark_id: UUID,
        *,
        run_id: UUID,
        comparison: OutcomeComparison,
        expected: SuppliedExpectedValue | None,
        description: str | None,
    ) -> int:
        received.append(comparison)

        return 0

    def unused(
        *_arguments: object,
        **_keywords: object,
    ) -> int:
        raise AssertionError("unrelated benchmark handler should not be dispatched")

    arguments: Namespace = build_parser().parse_args(
        (
            "benchmark",
            "add-case",
            str(BENCHMARK_ID),
            "--from-run",
            str(RUN_ID),
            "--comparison",
            "normalized",
        )
    )

    dispatch_benchmark_command(
        arguments,
        add_benchmark_case=add_case,
        compare_benchmarks=unused,
        export_benchmark=unused,
        import_benchmark=unused,
        list_benchmark_cases=unused,
        list_benchmark_executions=unused,
        list_benchmark_history=unused,
        list_benchmarks=unused,
        run_benchmark=unused,
        show_benchmark=unused,
        show_benchmark_case=unused,
        show_benchmark_execution=unused,
    )

    assert received == [OutcomeComparison.NORMALIZED]


@pytest.mark.parametrize(
    "missing",
    (
        "--from-run",
        "--comparison",
    ),
)
def test_cli_add_case_requires_run_and_comparison(
    missing: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options = {
        "--from-run": str(RUN_ID),
        "--comparison": "exact",
    }

    del options[missing]

    with pytest.raises(SystemExit) as raised:
        main(
            (
                "benchmark",
                "add-case",
                str(BENCHMARK_ID),
                *(item for pair in options.items() for item in pair),
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert f"the following arguments are required: {missing}" in captured.err


def test_cli_add_case_rejects_an_unknown_comparison(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "benchmark",
                "add-case",
                str(BENCHMARK_ID),
                "--from-run",
                str(RUN_ID),
                "--comparison",
                "fuzzy",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert "invalid choice: 'fuzzy'" in captured.err

    for comparison in OutcomeComparison:
        assert comparison.value in captured.err


def test_cli_add_case_rejects_invalid_expected_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "benchmark",
                "add-case",
                str(BENCHMARK_ID),
                "--from-run",
                str(RUN_ID),
                "--comparison",
                "exact",
                "--expected",
                "{nope",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2
    assert "argument --expected: Value must be valid JSON" in captured.err
