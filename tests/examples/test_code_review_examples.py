"""Tests proving the code-review example's workflow, tools and benchmark."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.prompting import ContextPromptStrategySpec, PromptOutputFormat
from azathoth.tools import (
    PythonToolExecutor,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowRun,
    WorkflowStepStatus,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_revision_examples import (
    RoutingLanguageModel,
    generate_novel_candidate,
    read_tool,
    read_workflow,
    run_with_input,
)

REVIEW_EXAMPLES = Path(__file__).parents[2] / "examples" / "code-review"

MERGE_TOOL_DOCUMENT = REVIEW_EXAMPLES / "tools" / "merge-reviews.json"

FINALIZE_TOOL_DOCUMENT = REVIEW_EXAMPLES / "tools" / "finalize-review.json"

REVIEW_WORKFLOW_DOCUMENT = REVIEW_EXAMPLES / "workflows" / "review-change.json"

REVIEW_BENCHMARK_DOCUMENT = REVIEW_EXAMPLES / "benchmarks" / "review-change.json"

REVIEWER_STEP_IDS = {
    "security": UUID("d2000000-0000-4000-8000-000000000011"),
    "correctness": UUID("d2000000-0000-4000-8000-000000000012"),
    "readability": UUID("d2000000-0000-4000-8000-000000000013"),
}

SUMMARIZE_STEP_ID = UUID("d2000000-0000-4000-8000-000000000014")

MERGE_STEP_ID = UUID("d2000000-0000-4000-8000-000000000015")

FINALIZE_STEP_ID = UUID("d2000000-0000-4000-8000-000000000016")

REVIEWER_MARKERS = {
    reviewer: f"You review code changes for {reviewer}." for reviewer in REVIEWER_STEP_IDS
}

SUMMARY_MARKER = "You are the lead reviewer on a code change."

SUMMARY = "Parameterize the query before this merges."

CHANGE: JsonValue = {
    "title": "Look up orders by customer name",
    "description": "Adds a search endpoint for support staff.",
    "diff": "+    query = f\"SELECT * FROM orders WHERE customer = '{customer_name}'\"\n",
}

INJECTION: dict[str, JsonValue] = {
    "severity": "high",
    "file": "app/orders.py",
    "line": 41,
    "summary": "customer_name is interpolated into the SQL query.",
    "suggestion": "Pass customer_name as a query parameter.",
}

SELECT_STAR: dict[str, JsonValue] = {
    "severity": "low",
    "file": "app/orders.py",
    "line": 41,
    "summary": "Select only the columns the endpoint returns.",
    "suggestion": "List the columns.",
}

NAMING: dict[str, JsonValue] = {
    "severity": "medium",
    "file": "app/orders.py",
    "line": None,
    "summary": "find_orders does not say what it searches by.",
    "suggestion": "Rename it find_orders_by_customer.",
}


def findings_reply(
    *findings: JsonValue,
) -> str:
    """Return one reviewer's JSON reply."""

    return json.dumps({"findings": list(findings)})


def review_model(
    *,
    security: tuple[JsonValue, ...] = (),
    correctness: tuple[JsonValue, ...] = (),
    readability: tuple[JsonValue, ...] = (),
) -> RoutingLanguageModel:
    """Script each reviewer's findings and the lead reviewer's comment."""

    return RoutingLanguageModel(
        (
            (REVIEWER_MARKERS["security"], findings_reply(*security)),
            (REVIEWER_MARKERS["correctness"], findings_reply(*correctness)),
            (REVIEWER_MARKERS["readability"], findings_reply(*readability)),
            (SUMMARY_MARKER, SUMMARY),
        )
    )


def review_candidate(
    model: RoutingLanguageModel,
) -> WorkflowCandidate:
    """Generate the review-change candidate backed by the scripted model."""

    return generate_novel_candidate(
        read_workflow(REVIEW_WORKFLOW_DOCUMENT),
        model,
        read_tool(MERGE_TOOL_DOCUMENT),
        read_tool(FINALIZE_TOOL_DOCUMENT),
    )


def review(
    model: RoutingLanguageModel,
    change: JsonValue = CHANGE,
) -> tuple[WorkflowRun, dict[str, JsonValue]]:
    """Run the code review and return its run and result."""

    candidate = review_candidate(model)

    run = run_with_input(candidate, change)

    assert candidate.result is not None

    result = workflow_result(run, candidate.result, steps=candidate.steps)

    assert isinstance(result, dict)

    return run, result


def merge(
    *,
    security: tuple[JsonValue, ...] = (),
    correctness: tuple[JsonValue, ...] = (),
    readability: tuple[JsonValue, ...] = (),
) -> dict[str, JsonValue]:
    """Run the merge tool directly."""

    return asyncio.run(
        PythonToolExecutor().execute(
            read_tool(MERGE_TOOL_DOCUMENT).implementations[0],
            {
                "security": list(security),
                "correctness": list(correctness),
                "readability": list(readability),
            },
        )
    )


def merged_review(
    **findings: tuple[JsonValue, ...],
) -> dict[str, JsonValue]:
    """Return the review the merge tool builds from the reviewers' findings."""

    review = merge(**findings)["review"]

    assert isinstance(review, dict)

    return review


def read_benchmark() -> BenchmarkDataset:
    """Decode the checked-in review-change benchmark."""

    return decode_benchmark_document(REVIEW_BENCHMARK_DOCUMENT.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("path", "encode", "decode"),
    [
        pytest.param(
            MERGE_TOOL_DOCUMENT,
            encode_tool_document,
            decode_tool_document,
            id="merge-tool",
        ),
        pytest.param(
            FINALIZE_TOOL_DOCUMENT,
            encode_tool_document,
            decode_tool_document,
            id="finalize-tool",
        ),
        pytest.param(
            REVIEW_WORKFLOW_DOCUMENT,
            encode_workflow_document,
            decode_workflow_document,
            id="review-workflow",
        ),
        pytest.param(
            REVIEW_BENCHMARK_DOCUMENT,
            encode_benchmark_document,
            decode_benchmark_document,
            id="benchmark",
        ),
    ],
)
def test_code_review_documents_are_canonical(
    path: Path,
    encode: object,
    decode: object,
) -> None:
    encoded = path.read_text(encoding="utf-8")

    assert callable(encode) and callable(decode)
    assert encode(decode(encoded)) == encoded.rstrip("\n")


def test_three_reviewers_run_together_before_the_merge() -> None:
    layers = read_workflow(REVIEW_WORKFLOW_DOCUMENT).execution_layers()

    assert [[step.id for step in layer] for layer in layers] == [
        list(REVIEWER_STEP_IDS.values()),
        [MERGE_STEP_ID],
        [SUMMARIZE_STEP_ID],
        [FINALIZE_STEP_ID],
    ]


def test_reviewers_reply_in_json() -> None:
    workflow = read_workflow(REVIEW_WORKFLOW_DOCUMENT)

    for step in workflow.steps:
        if step.id in REVIEWER_STEP_IDS.values():
            assert isinstance(step.specification, ContextPromptStrategySpec)
            assert step.specification.output_format is PromptOutputFormat.JSON


def test_each_reviewer_sees_the_change_and_its_own_area() -> None:
    model = review_model()

    review(model)

    for reviewer, marker in REVIEWER_MARKERS.items():
        (prompt,) = model.prompts_containing(marker)

        assert "SELECT * FROM orders" in prompt
        assert f"Report only {reviewer} problems" in prompt


def test_merge_tags_each_finding_with_its_reviewer() -> None:
    review = merged_review(security=(INJECTION,), readability=(NAMING,))

    assert review["findings"] == [
        {**INJECTION, "reviewers": ["security"]},
        {**NAMING, "reviewers": ["readability"]},
    ]


def test_merge_combines_a_finding_more_than_one_reviewer_raised() -> None:
    restated = {**INJECTION, "summary": "  CUSTOMER_NAME is interpolated into the SQL query. "}

    review = merged_review(security=(INJECTION,), correctness=(restated,))

    assert review["findings"] == [{**INJECTION, "reviewers": ["security", "correctness"]}]


def test_merge_orders_findings_by_severity() -> None:
    review = merged_review(
        security=(INJECTION,),
        correctness=(SELECT_STAR,),
        readability=(NAMING,),
    )

    findings = review["findings"]
    assert isinstance(findings, list)

    assert [finding["severity"] for finding in findings if isinstance(finding, dict)] == [
        "high",
        "medium",
        "low",
    ]
    assert review["counts"] == {"high": 1, "medium": 1, "low": 1}


@pytest.mark.parametrize(
    ("findings", "verdict"),
    [
        pytest.param({}, "approve", id="approve"),
        pytest.param({"readability": (NAMING,)}, "comment", id="comment"),
        pytest.param({"security": (INJECTION,)}, "request_changes", id="request-changes"),
    ],
)
def test_merge_decides_the_verdict_from_the_worst_finding(
    findings: dict[str, tuple[JsonValue, ...]],
    verdict: str,
) -> None:
    assert merged_review(**findings)["verdict"] == verdict


def test_clean_change_is_approved_without_a_lead_review() -> None:
    model = review_model()

    run, result = review(model)

    assert result == {
        "verdict": "approve",
        "findings": [],
        "counts": {"high": 0, "medium": 0, "low": 0},
        "summary": "No issues found.",
    }

    statuses = {step.step_id: step.status for step in run.steps}
    assert statuses[SUMMARIZE_STEP_ID] is WorkflowStepStatus.SKIPPED
    assert model.prompts_containing(SUMMARY_MARKER) == ()


def test_findings_are_summarized_by_the_lead_reviewer() -> None:
    model = review_model(security=(INJECTION,), readability=(NAMING,))

    _, result = review(model)

    assert result["verdict"] == "request_changes"
    assert result["summary"] == SUMMARY

    (prompt,) = model.prompts_containing(SUMMARY_MARKER)

    assert '"verdict":"request_changes"' in prompt
    assert '"reviewers":["security"]' in prompt
    assert "SELECT * FROM orders" in prompt


def test_benchmark_checks_verdicts_by_schema_and_findings_by_meaning() -> None:
    comparisons = [case.expected.comparison for case in read_benchmark().cases]

    assert comparisons.count(OutcomeComparison.SCHEMA) == 2
    assert comparisons.count(OutcomeComparison.SEMANTIC) == 2


def schema_cases() -> BenchmarkDataset:
    """Return only the benchmark's schema cases, which need no judge."""

    dataset = read_benchmark()

    return BenchmarkDataset.model_validate(
        {
            **dict(dataset),
            "cases": tuple(
                case
                for case in dataset.cases
                if case.expected.comparison is OutcomeComparison.SCHEMA
            ),
        }
    )


def scripted_reviewers(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Script reviewers that flag the injection and approve the rename."""

    change = case.input

    assert isinstance(change, dict)

    diff = change["diff"]
    assert isinstance(diff, str)

    if "SELECT" in diff:
        return review_candidate(review_model(security=(INJECTION,)))

    return review_candidate(review_model())


def blind_reviewers(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Script reviewers that never find anything."""

    return review_candidate(review_model())


@pytest.mark.parametrize(
    ("factory", "passed"),
    [
        pytest.param(scripted_reviewers, 2, id="catches-the-injection"),
        pytest.param(blind_reviewers, 1, id="misses-the-injection"),
    ],
)
def test_benchmark_schema_blocks_only_reviews_that_catch_the_injection(
    factory: Callable[[BenchmarkCase], WorkflowCandidate],
    passed: int,
) -> None:
    result = asyncio.run(WorkflowBenchmarkRunner().run(schema_cases(), factory))

    assert (result.cases_run, result.cases_passed) == (2, passed)
