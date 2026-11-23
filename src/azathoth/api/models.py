"""The values the service API returns (ADR 0120).

The API returns its own models, never Azathoth's internal ones, so the
engine can change beneath it while what callers read stays put. Every model
is frozen, refuses unknown fields, and is its own JSON: a local UI server
sends `model_dump(mode="json")` as it is.
"""

from datetime import datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from azathoth.sensitivity import DataPolicy, Sensitivity

ApiStability = Literal["provisional", "stable"]
"""Whether the API is still provisional, or covered by the 1.x promise."""

API_STABILITY: Final[ApiStability] = "stable"
"""The API's stability in this Azathoth: stable, under the 1.x promise from 1.4.0."""

Backend = Literal["sqlite", "postgres"]
"""The kind of database an instance keeps its state in."""


class ApiModel(BaseModel):
    """Base of every value the service API returns: frozen, closed, and its own JSON."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class InstanceDescription(ApiModel):
    """What one open instance is: its database, and the Azathoth serving it."""

    database: str = Field(
        min_length=1,
        description=(
            "The database as messages name it: an SQLite file's path, or a PostgreSQL "
            "URL without its password."
        ),
    )

    backend: Backend

    azathoth_version: str = Field(
        min_length=1,
    )

    schema_version: int = Field(
        ge=1,
        description="The database schema version this Azathoth uses.",
    )

    api_stability: ApiStability


class Author(ApiModel):
    """Who imported a revision, or added a portfolio entry (ADR 0122)."""

    name: str

    email: str | None


class Revision(ApiModel):
    """One imported revision of a workflow, tool version or benchmark."""

    number: int = Field(
        ge=1,
    )

    content_digest: str = Field(
        description="The sha256 of the revision's canonical JSON.",
    )

    imported_at: datetime | None = Field(
        description="When it was imported, or None for revisions from before 1.1.",
    )

    identical_to: int | None = Field(
        description="The earliest earlier revision with the same content, when it reverted to one.",
    )

    revision_digest: str = Field(
        description=(
            "Identifies this revision wherever it is kept: the sha256 of its lineage, content "
            "digest and parent's revision digest (ADR 0122)."
        ),
    )

    parent_digest: str | None = Field(
        description="The revision digest of the revision it was built on, or None for the first.",
    )

    parent_number: int | None = Field(
        ge=1,
        description="The number of the revision it was built on, or None for the first.",
    )

    author: Author | None = Field(
        description="Who imported it, or None for revisions from before 1.4.",
    )


class WorkflowSummary(ApiModel):
    """One revision of a workflow, as lists and histories show it."""

    id: UUID

    name: str

    version: str

    description: str

    revision: Revision

    command: str = Field(
        description="The `azathoth` command that shows the same workflow.",
    )


class WorkflowDetail(WorkflowSummary):
    """One revision of a workflow with its whole document."""

    latest_number: int = Field(
        ge=1,
        description="The number of the workflow's latest revision.",
    )

    document: dict[str, JsonValue] = Field(
        description="The revision as `azathoth workflow import` accepts it.",
    )


class ToolSummary(ApiModel):
    """One revision of one exact tool version, as lists and histories show it."""

    id: UUID

    version: str

    name: str

    description: str

    revision: Revision

    implementation_count: int = Field(
        ge=0,
    )

    test_case_count: int = Field(
        ge=0,
    )

    command: str = Field(
        description="The `azathoth` command that shows the same tool version.",
    )


class ToolDetail(ToolSummary):
    """One revision of one exact tool version with its whole document."""

    latest_number: int = Field(
        ge=1,
        description="The number of the tool version's latest revision.",
    )

    document: dict[str, JsonValue] = Field(
        description="The revision as `azathoth tool import` accepts it.",
    )


class BenchmarkSummary(ApiModel):
    """One revision of a benchmark dataset, as lists and histories show it."""

    id: UUID

    name: str

    version: str

    description: str

    case_count: int = Field(
        ge=0,
    )

    sensitivity: Sensitivity = Field(
        description=(
            "The most sensitive of its cases' labels, an unlabelled case counting as internal "
            "(ADR 0123)."
        ),
    )

    revision: Revision

    command: str = Field(
        description="The `azathoth` command that shows the same benchmark.",
    )


class BenchmarkDetail(BenchmarkSummary):
    """One revision of a benchmark dataset with its whole document."""

    latest_number: int = Field(
        ge=1,
        description="The number of the benchmark's latest revision.",
    )

    document: dict[str, JsonValue] = Field(
        description="The revision as `azathoth benchmark import` accepts it.",
    )


class GoalSummary(ApiModel):
    """One reusable goal: what a strategy is trying to accomplish (ADR 0133)."""

    id: UUID

    name: str = Field(
        min_length=1,
    )

    description: str = Field(
        min_length=1,
    )

    command: str = Field(
        description="The `azathoth` command that shows it.",
    )


class GoalDetail(GoalSummary):
    """One reusable goal with its success criteria, constraints and document."""

    success_criteria: tuple[str, ...] = Field(
        min_length=1,
        description="What a strategy meeting the goal achieves, in order.",
    )

    constraints: tuple[str, ...] = Field(
        description="What a strategy must not do, in order; none when it has none.",
    )

    document: dict[str, JsonValue] = Field(
        description="The goal as `azathoth goal import` accepts it.",
    )


class GoalImport(ApiModel):
    """What importing one goal document did (ADR 0133).

    A goal is not revised: importing another goal with an ID that is taken
    is a conflict.
    """

    created: bool = Field(
        description=(
            "Whether the goal was kept. False when the document is identical to the goal "
            "already kept under its ID, which `goal` then is."
        ),
    )

    goal: GoalDetail


RevisionChangeKind = Literal["added", "removed", "changed"]
"""How a value differs between two revisions: only after, only before, or in both but unequal."""


class RevisionChange(ApiModel):
    """One value that differs between two revisions' documents (ADR 0133)."""

    kind: RevisionChangeKind

    pointer: str = Field(
        description="Where the value is, as an RFC 6901 JSON Pointer; the empty one is the root.",
    )

    before: JsonValue = Field(
        default=None,
        description="The value before; None when it was added, or when it is withheld.",
    )

    after: JsonValue = Field(
        default=None,
        description="The value after; None when it was removed, or when it is withheld.",
    )

    withheld: bool = Field(
        default=False,
        description=(
            "Whether a restricted case's values were left out of before or after, as None."
        ),
    )


class RevisionComparison(ApiModel):
    """What differs between two revisions of one workflow, tool version or benchmark (ADR 0133).

    The comparison is structural: the two documents, as they export, are
    compared value by value, and a list item by item.
    """

    before: Revision

    after: Revision

    identical: bool = Field(
        description="Whether the two revisions have the same content digest.",
    )

    changes: tuple[RevisionChange, ...] = Field(
        description="Each value that differs, in document order; none when they are identical.",
    )


class DocumentExport(ApiModel):
    """One revision as the document that imports it again, and the file it suggests (ADR 0133).

    `text` is exactly what the export command prints, so importing the
    latest revision's export again appends nothing and importing an earlier
    one's reverts to it (ADR 0122).
    """

    text: str

    file_name: str = Field(
        min_length=1,
        description=(
            "A file name for it, from the component's name, a tool's version and the revision."
        ),
    )

    sensitivity: Sensitivity | None = Field(
        default=None,
        description="A benchmark's label, so a restricted one's export can say so; None otherwise.",
    )


class WorkflowImport(ApiModel):
    """What importing one workflow document did (ADR 0122)."""

    created: bool = Field(
        description=(
            "Whether a revision was appended. False when the document is identical to the "
            "revision it builds on, which `workflow` then is."
        ),
    )

    workflow: WorkflowDetail


class ToolImport(ApiModel):
    """What importing one tool document did (ADR 0122)."""

    created: bool = Field(
        description=(
            "Whether a revision was appended. False when the document is identical to the "
            "revision it builds on, which `tool` then is."
        ),
    )

    tool: ToolDetail


class BenchmarkImport(ApiModel):
    """What importing one benchmark document did (ADR 0122)."""

    created: bool = Field(
        description=(
            "Whether a revision was appended. False when the document is identical to the "
            "revision it builds on, which `benchmark` then is."
        ),
    )

    benchmark: BenchmarkDetail


CaseComparison = Literal["exact", "normalized", "semantic", "schema"]
"""How a benchmark case judges a result: equal, normalized, judged, or valid (ADR 0070)."""


CaseSource = Literal["run", "file", "json"]
"""Where a benchmark case came from: a recorded run, a file, or JSON given as it is (ADR 0130)."""


class CitedSegmentSummary(ApiModel):
    """One source segment a case's run must cite (ADR 0117)."""

    source: str

    segment: str


class CaseCitations(ApiModel):
    """What a case's run must cite, and whether a check that did not verify fails it."""

    require: tuple[CitedSegmentSummary, ...]

    on_unverified: Literal["fail", "ignore"] = Field(
        description="`fail` fails the case on any check that did not verify; `ignore` does not.",
    )


class BenchmarkCaseSummary(ApiModel):
    """One case of one benchmark revision, as a list of its cases shows it (ADR 0130)."""

    benchmark_id: UUID

    revision: int = Field(
        ge=1,
        description="The benchmark revision the case was read from.",
    )

    case_id: UUID

    description: str = Field(
        description="What the case expects, in words.",
    )

    comparison: CaseComparison

    sensitivity: Sensitivity = Field(
        description="Its input's label, internal when it has none (ADR 0123).",
    )

    source: CaseSource

    source_run_id: UUID | None = Field(
        description="The recorded run it was made from, when it was made from one.",
    )

    cited: bool = Field(
        description="Whether it names what its run must cite.",
    )

    command: str = Field(
        description="The `azathoth` command that shows the case.",
    )


class BenchmarkCaseDetail(BenchmarkCaseSummary):
    """One benchmark case with its input, what it expects, and where its input came from."""

    input: JsonValue = Field(
        description="What the case's run is given: the content's handle for a PDF or an image.",
    )

    input_provenance: dict[str, JsonValue] | None = Field(
        description=(
            "Where its input was read from and which content it was, for a run's or a file's."
        ),
    )

    expected: JsonValue = Field(
        description="The value the case expects, compared as `comparison` says.",
    )

    citations: CaseCitations | None = Field(
        description="What its run must cite, or None when it names nothing.",
    )

    source_feedback_id: UUID | None = Field(
        description="The judgment whose corrected output it expects, when it was made from one.",
    )

    metadata: dict[str, JsonValue] = Field(
        description="Everything else the case records, as `benchmark case-show` prints it.",
    )


class BenchmarkCaseChange(ApiModel):
    """What adding, editing or removing one case did: the case, and the revision it saved."""

    case: BenchmarkCaseDetail = Field(
        description=(
            "The case as the saved revision holds it, or, once removed, as the revision before "
            "held it."
        ),
    )

    benchmark: BenchmarkSummary = Field(
        description=(
            "The revision the change saved, or the latest when it saved none, being identical."
        ),
    )


ExecutionKind = Literal["run", "compare"]
"""What saved a benchmark execution: `benchmark run`, or `benchmark compare` (ADR 0075)."""


class ScoringPolicySummary(ApiModel):
    """The targets a comparison scored its workflows' latency and cost against."""

    target_latency_seconds: float

    target_cost_usd: float


class CandidateScorecard(ApiModel):
    """How a comparison scored one workflow, each score from 0 to 1."""

    quality_score: float

    reliability_score: float

    latency_score: float

    cost_score: float

    citation_score: float | None = Field(
        description="How well its runs cited, or None when no case named citations.",
    )

    overall_score: float

    rationale: str


class ComparisonTally(ApiModel):
    """How many of one workflow's cases judged by one comparison passed."""

    comparison: CaseComparison

    cases_run: int = Field(
        ge=0,
    )

    cases_passed: int = Field(
        ge=0,
    )


class ExecutionCaseResult(ApiModel):
    """How one case of an execution went for one workflow, and the evidence that judged it."""

    case_id: UUID

    comparison: CaseComparison

    run_id: UUID = Field(
        description="The run the case ran as, kept as any run is.",
    )

    evaluation_id: UUID

    passed: bool

    run_failure: bool = Field(
        description="Whether the run failed without the declared result, which fails the case.",
    )

    score: float | None = Field(
        description="The evaluation's score from 0 to 1, or None when it is no longer kept.",
    )

    reason: str | None = Field(
        description="Why the evaluation judged it so, or None when it is no longer kept.",
    )

    judge_calls: int = Field(
        ge=0,
    )

    judge_cost_usd: float = Field(
        ge=0.0,
        description="What judging it cost, which is never charged to the workflow.",
    )


class ExecutionCandidateSummary(ApiModel):
    """One workflow an execution ran, as a list of executions shows it."""

    candidate_id: UUID

    workflow_id: UUID

    workflow_name: str

    workflow_revision: int | None = Field(
        description="The revision that ran, or None for an execution from before revisions.",
    )

    cases_run: int = Field(
        ge=0,
    )

    cases_passed: int = Field(
        ge=0,
    )

    accuracy: float = Field(
        description="The fraction of its cases that passed.",
    )

    overall_score: float | None = Field(
        description="Its overall score in a comparison, or None in a run, which is not scored.",
    )


class ExecutionCandidate(ExecutionCandidateSummary):
    """One workflow an execution ran, with every case and how it was scored."""

    strategy_ids: tuple[UUID, ...] = Field(
        description="The strategies its steps ran with, which identify what was judged.",
    )

    run_failures: int = Field(
        ge=0,
    )

    judged_semantically: bool = Field(
        description="Whether any of its cases was judged by the judge rotation.",
    )

    judge_calls: int = Field(
        ge=0,
    )

    judge_cost_usd: float = Field(
        ge=0.0,
    )

    tallies: tuple[ComparisonTally, ...] = Field(
        description="Its pass counts by comparison, for each comparison its cases used.",
    )

    scorecard: CandidateScorecard | None = Field(
        description="How a comparison scored it, or None in a run.",
    )

    cases: tuple[ExecutionCaseResult, ...] = Field(
        description="Every case, in the order the benchmark holds them.",
    )


class BenchmarkExecutionSummary(ApiModel):
    """One saved run or comparison of a benchmark, as a list of them shows it (ADR 0130)."""

    execution_id: UUID

    benchmark_id: UUID

    benchmark_revision: int | None = Field(
        description=(
            "The benchmark revision it ran, told by its content, or None when no revision "
            "kept holds that content."
        ),
    )

    benchmark_digest: str | None = Field(
        description="The content digest of the benchmark it ran, or None from before 1.1.",
    )

    kind: ExecutionKind

    recorded_at: datetime

    sensitivity: Sensitivity = Field(
        description="The label of the benchmark it ran (ADR 0123).",
    )

    case_count: int = Field(
        ge=0,
    )

    candidates: tuple[ExecutionCandidateSummary, ...] = Field(
        description="Every workflow it ran, best first in a comparison.",
    )

    command: str = Field(
        description="The `azathoth` command that shows it.",
    )


class BenchmarkExecutionDetail(ApiModel):
    """One saved run or comparison of a benchmark with every workflow and case."""

    execution_id: UUID

    benchmark_id: UUID

    benchmark_revision: int | None

    benchmark_digest: str | None

    kind: ExecutionKind

    recorded_at: datetime

    sensitivity: Sensitivity

    case_count: int = Field(
        ge=0,
    )

    scoring_policy: ScoringPolicySummary | None = Field(
        description="What a comparison scored latency and cost against, or None in a run.",
    )

    candidates: tuple[ExecutionCandidate, ...] = Field(
        description="Every workflow it ran, best first in a comparison.",
    )

    command: str


class ModelSummary(ApiModel):
    """One model a configured provider currently serves.

    What its provider does not publish is `None`: Azathoth never guesses a
    context window, an output limit or a price.
    """

    identifier: str = Field(
        description="The provider-qualified identifier, `<provider>/<model>`.",
    )

    provider: str

    model: str

    display_name: str

    input_modalities: tuple[str, ...]

    output_modalities: tuple[str, ...]

    capabilities: tuple[str, ...]

    context_window_tokens: int | None

    maximum_output_tokens: int | None

    input_usd_per_million_tokens: float | None

    output_usd_per_million_tokens: float | None

    authorized: bool = Field(
        description="Whether the model is in this instance's portfolio.",
    )

    command: str = Field(
        description="The `azathoth` command that shows the same model.",
    )


class PortfolioEntry(ApiModel):
    """One model this instance authorizes for selection."""

    identifier: str

    provider: str

    model: str

    content_digest: str = Field(
        description="The sha256 of the entry's canonical JSON (ADR 0122).",
    )

    author: Author | None = Field(
        description="Who authorized it, or None for entries added before 1.4.",
    )

    added_at: datetime | None = Field(
        description="When it was authorized, or None for entries added before 1.4.",
    )

    data_policy: DataPolicy = Field(
        description=(
            "What was declared its provider does with data it is sent; unknown until "
            "declared (ADR 0123)."
        ),
    )

    receives_restricted: bool = Field(
        description=(
            "Whether it may be sent restricted input: only when its provider is declared to "
            "neither retain nor train on data."
        ),
    )

    policy_declared_by: Author | None = Field(
        description="Who declared its data policy, or None when it was never declared.",
    )

    policy_declared_at: datetime | None = Field(
        description="When its data policy was declared, or None when it was never declared.",
    )

    command: str = Field(
        description="The `azathoth` command that shows the model.",
    )


class ProductionStepUsage(ApiModel):
    """One step of a production workflow that uses a model."""

    step_id: UUID

    role: Literal["primary", "substitute"]


class StepAttemptUsage(ApiModel):
    """One attempt of one step of a run that executed a model (ADR 0133)."""

    step_id: UUID

    attempt_number: int = Field(ge=1)


class ModelRunUsage(ApiModel):
    """One kept run that executed a model, and each step attempt that did."""

    run_id: UUID

    started_at: datetime

    steps: tuple[StepAttemptUsage, ...] = Field(min_length=1)


class ModelUsageWorkflow(ApiModel):
    """Everything one workflow does with a model: configured, in production, and run."""

    workflow_id: UUID

    workflow_name: str

    configured: bool = Field(description="Whether the workflow's configuration names the model.")

    production: tuple[ProductionStepUsage, ...] = Field(
        description="Each step of active production that uses it, and the role it holds there.",
    )

    runs: tuple[ModelRunUsage, ...] = Field(
        description="Each kept run that executed it, in the order the runs were kept.",
    )


class ModelUsage(ApiModel):
    """Where one exact model is configured, in production, and executed (ADR 0133).

    A model nothing uses has no workflows, and is not an error.
    """

    identifier: str = Field(min_length=1)

    in_production: bool

    workflows: tuple[ModelUsageWorkflow, ...]


class ToolExecutionUsage(ApiModel):
    """One attempt of one step of a run that executed a tool's implementation."""

    step_id: UUID

    attempt_number: int = Field(ge=1)

    implementation_id: UUID

    tool_version: str

    runtime: str


class ToolRunUsage(ApiModel):
    """One kept run that executed a tool, and each execution of it."""

    run_id: UUID

    started_at: datetime

    executions: tuple[ToolExecutionUsage, ...] = Field(min_length=1)


class ToolUsageWorkflow(ApiModel):
    """Everything one workflow does with a tool: configured, in production, and run."""

    workflow_id: UUID

    workflow_name: str

    configured: bool = Field(description="Whether the workflow's configuration requires the tool.")

    production: bool = Field(description="Whether active production requires it.")

    runs: tuple[ToolRunUsage, ...]


class ToolUsage(ApiModel):
    """Where one tool identity is configured, in production, and executed (ADR 0133)."""

    tool_id: UUID

    tool_names: tuple[str, ...] = Field(
        description=(
            "The names its versions are required by, in order; none for a tool only runs know."
        ),
    )

    in_production: bool

    workflows: tuple[ToolUsageWorkflow, ...]


class ProductionDependent(ApiModel):
    """One workflow whose active production uses a model."""

    workflow_id: UUID

    workflow_name: str

    steps: tuple[ProductionStepUsage, ...]


class PortfolioRemoval(ApiModel):
    """What removing a model from the portfolio did."""

    identifier: str

    dependents: tuple[ProductionDependent, ...] = Field(
        description="The production workflows that still use the model, when removal was forced.",
    )

    command: str = Field(
        description="The `azathoth` command that removes a model the same way.",
    )


class DocumentProblem(ApiModel):
    """One reason a workflow document would be refused (ADR 0121)."""

    message: str = Field(
        description="Why, as importing the document would say.",
    )

    location: tuple[str | int, ...] = Field(
        description=(
            "Where in the document: the keys and indexes leading to the value at fault, "
            "empty when the fault is the whole document's."
        ),
    )

    step_id: UUID | None = Field(
        description="The step the problem is in, when it is in a step whose id is valid.",
    )


class WorkflowCheck(ApiModel):
    """Whether a workflow document would be imported, and every reason it would not."""

    valid: bool = Field(
        description="Whether importing the document would accept it.",
    )

    problems: tuple[DocumentProblem, ...]


StepKind = Literal["prompt", "context_prompt", "tool"]
"""How a step runs: a prompt, a prompt rendered from the context, or a tool."""


class StepReadiness(ApiModel):
    """Whether one step of a workflow document could run here now (ADR 0121)."""

    step_id: UUID

    kind: StepKind

    ready: bool

    models: tuple[str, ...] = Field(
        description=(
            "The models a prompt step could run on, in the order a run tries them; "
            "a run uses the first."
        ),
    )

    tool_id: UUID | None = Field(
        description="The tool a tool step would run, when it can run.",
    )

    tool_version: str | None

    tool_implementation_id: UUID | None = Field(
        description="The implementation of the tool a tool step would run, when it can run.",
    )

    problem: str | None = Field(
        description="Why the step could not run here now, when it could not.",
    )


class WorkflowReadiness(ApiModel):
    """Whether every step of a workflow document could run here now."""

    ready: bool

    steps: tuple[StepReadiness, ...] = Field(
        description="Every step, in the document's order.",
    )


class RunInput(ApiModel):
    """The input a run is given; a run given none starts with an empty context.

    Wrapping the payload keeps a JSON null, which is input, apart from no
    input at all.
    """

    payload: JsonValue


class RunFile(ApiModel):
    """A file a run or an invocation is given as its input (ADR 0121).

    It is accepted as the command line's `--input-file` accepts one (ADR
    0112): JSON and `text/*` content is decoded into the value the workflow
    receives, and a PDF, PNG, JPEG or WebP is kept in the content store by
    its digest and given to the workflow as a content handle. Content that
    is not its media type is refused before anything runs or is kept.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    content: bytes = Field(
        description="The file's bytes; as JSON, in base64.",
    )

    media_type: str = Field(
        description="The content's media type, such as application/pdf or text/plain.",
    )


class RunError(ApiModel):
    """Why a finished run has no result, as `azathoth workflow run` reports it."""

    code: Literal["workflow_execution_failed", "result_not_produced"]

    step_id: UUID | None = Field(
        description="The step that halted the run, when one did.",
    )

    exception_type: str | None

    message: str


class RunResult(ApiModel):
    """One finished run, which is kept whether it succeeded or failed."""

    run_id: UUID

    workflow_id: UUID

    workflow_revision: int | None

    succeeded: bool = Field(
        description="Whether the run finished with its declared result, or without one declared.",
    )

    has_result: bool = Field(
        description="Whether `result` holds the declared result, so a null result is not absence.",
    )

    result: JsonValue = None

    error: RunError | None

    warnings: tuple[str, ...] = Field(
        description="What went wrong beside the run, such as an event callback that raised.",
    )

    started_at: datetime

    completed_at: datetime

    command: str = Field(
        description="The `azathoth` command that shows the run.",
    )


class InvocationError(ApiModel):
    """Why an invocation did not succeed, as `azathoth job run` reports it."""

    code: str = Field(
        description="A production code, such as `workflow_not_deployed`, or an envelope code.",
    )

    message: str

    metadata: dict[str, JsonValue]


class InvocationOutcome(ApiModel):
    """How one invocation of a promoted workflow ended, under its idempotency key.

    `succeeded` and `failed` report an invocation with its outcome;
    `rejected` means no invocation was made for the request; `incomplete`
    means the key's invocation is still running elsewhere.
    """

    status: Literal["succeeded", "failed", "rejected", "incomplete"]

    replayed: bool = Field(
        description="Whether an earlier request under the same key made the invocation.",
    )

    idempotency_key: str

    invocation_id: UUID | None

    result: JsonValue = None

    error: InvocationError | None

    warnings: tuple[str, ...]

    command: str | None = Field(
        description="The `azathoth` command that shows the invocation, when there is one.",
    )


class JudgeSummary(ApiModel):
    """One model of the rotation that judges semantic cases, in its place (ADR 0129)."""

    identifier: str

    provider: str

    model: str

    position: int = Field(
        ge=1,
        description="Its place in the rotation, from 1: the order judges are tried.",
    )

    authorized: bool = Field(
        description=(
            "Whether the portfolio still authorizes it; one that no longer does is kept "
            "until it is removed, and is never asked to judge."
        ),
    )

    command: str = Field(
        description="The `azathoth` command that lists the rotation.",
    )


class InvocationSummary(ApiModel):
    """One invocation of a promoted workflow, as `azathoth workflow invocations` lists it."""

    invocation_id: UUID

    workflow_id: UUID

    created_at: datetime

    status: Literal["succeeded", "failed", "incomplete"] = Field(
        description="How it ended, or `incomplete` while it has no outcome.",
    )

    caller_metadata: dict[str, JsonValue] = Field(
        description="What its caller recorded with it, such as who or what called.",
    )

    sensitivity: Sensitivity = Field(
        description="The label its input was given, internal when none was (ADR 0123).",
    )

    run_id: UUID | None = Field(
        description="The run that executed it, once it has one.",
    )

    command: str = Field(
        description="The `azathoth` command that shows it.",
    )

    error_code: str | None = Field(
        default=None,
        description="The production code of a failed one's error, such as `timeout` (ADR 0140).",
    )


class ProductionStepModels(ApiModel):
    """The models production runs one prompt step on, in the order it tries them (ADR 0063)."""

    step_id: UUID

    primary: str = Field(
        description="The provider-qualified model the step is pinned to.",
    )

    substitutes: tuple[str, ...] = Field(
        description="The models production approved in its place, tried in order.",
    )


class ProductionRevisionSummary(ApiModel):
    """One production revision of a workflow: a promotion, or a rollback (ADR 0128)."""

    revision_id: UUID

    workflow_id: UUID

    workflow_revision: int | None = Field(
        ge=1,
        description=(
            "The workflow revision that was promoted, or None for production promoted "
            "before revisions were numbered."
        ),
    )

    created_at: datetime

    author: Author | None = Field(
        description="Who promoted or rolled back, or None for revisions from before 1.5.",
    )

    restores: UUID | None = Field(
        description="The earlier production revision a rollback restored, or None.",
    )

    active: bool = Field(
        description="Whether its state is the one production runs now.",
    )

    steps: tuple[ProductionStepModels, ...] = Field(
        description="Each prompt step's models, in the workflow's order.",
    )


class ProductionEmission(ApiModel):
    """One value a workflow's production returns, and where in its run it is read (ADR 0140)."""

    name: str

    source: str = Field(
        description="Where the value is read, as `azathoth workflow production` describes it.",
    )


class ProductionState(ApiModel):
    """What a workflow's production runs now, as `azathoth workflow production` shows it."""

    workflow_id: UUID

    workflow_name: str

    workflow_revision: int | None = Field(
        ge=1,
        description="The workflow revision in production, or None when it was never numbered.",
    )

    revision: ProductionRevisionSummary | None = Field(
        description=(
            "The production revision that made it active, or None when it was set without one."
        ),
    )

    steps: tuple[ProductionStepModels, ...]

    input_schema: JsonValue = Field(
        default=None,
        description="The JSON Schema every invocation's input is checked against, if any.",
    )

    output_schema: JsonValue = Field(
        default=None,
        description="The JSON Schema every invocation's result is checked against, if any.",
    )

    command: str = Field(
        description="The `azathoth` command that shows it.",
    )

    emissions: tuple[ProductionEmission, ...] = Field(
        default=(),
        description="What every invocation returns, in the order it is declared (ADR 0140).",
    )


class RunStep(ApiModel):
    """One step of a finished run, as an invocation's evidence shows it."""

    step_id: UUID

    status: Literal["executed", "failed", "skipped"]

    attempts: int = Field(
        ge=0,
    )

    confidence: float | None


class InvocationRun(ApiModel):
    """The run behind one invocation.

    A run that has not finished names only its ID and how often it was
    resumed: `finished` is false, and it has no steps.
    """

    run_id: UUID

    finished: bool

    resumes: int = Field(
        ge=0,
    )

    workflow_revision: int | None = None

    started_at: datetime | None = None

    completed_at: datetime | None = None

    halted: bool | None = None

    steps: tuple[RunStep, ...] = ()


class Annotations(ApiModel):
    """A run's verified citations, as a W3C Web Annotation collection (ADRs 0117 and 0129)."""

    subject_id: UUID = Field(
        description="The run or invocation asked about.",
    )

    run_id: UUID = Field(
        description="The run whose cited steps kept the citations: an invocation's run.",
    )

    collection: dict[str, JsonValue] = Field(
        description="The annotation collection, exactly as `azathoth run annotations` prints it.",
    )

    items: tuple[dict[str, JsonValue], ...] = Field(
        description="The collection's annotations, in the order the run's steps checked them.",
    )

    command: str = Field(
        description="The `azathoth` command that prints the collection.",
    )


class InterruptedRun(ApiModel):
    """A run that started and never finished, as its journal records it (ADR 0129)."""

    run_id: UUID

    workflow_id: UUID

    workflow_name: str = Field(
        description="The workflow's name in the revision the run started from.",
    )

    workflow_revision: int | None = Field(
        description="The revision it started from, or None for a run from before revisions.",
    )

    invocation_id: UUID | None = Field(
        description="The production invocation it executes, when it executes one.",
    )

    started_at: datetime

    last_recorded_at: datetime = Field(
        description="When its journal last recorded anything: how far it got.",
    )

    resumes: int = Field(
        ge=0,
        description="How often it was resumed and stopped again.",
    )

    command: str = Field(
        description="The `azathoth` command that resumes it: its invocation's, when it has one.",
    )


ChildStatus = Literal["succeeded", "failed", "unfinished"]
"""How a child run ended, or that no finished run is kept for it yet (ADR 0129)."""


class RunChildSummary(ApiModel):
    """One run a step of another run started, and how it ended (ADRs 0105 and 0129)."""

    child_run_id: UUID

    child_workflow_id: UUID

    child_invocation_id: UUID | None = Field(
        description="The invocation the child executed, when it was started by invoking one.",
    )

    parent_run_id: UUID

    parent_step_id: UUID = Field(
        description="The step of the parent run that started the child.",
    )

    parent_attempt: int = Field(
        ge=1,
        description="The attempt of that step that started it.",
    )

    depth: int = Field(
        ge=1,
        description="How far below the run that started the whole tree it is: 1 for a child.",
    )

    started_at: datetime = Field(
        description="When the child was indexed, as it started.",
    )

    status: ChildStatus = Field(
        description=(
            "How it ended, judged as `runs.get` judges it, or `unfinished` while no finished "
            "run is kept for it."
        ),
    )

    command: str | None = Field(
        description="The `azathoth` command that shows the child, once it finished.",
    )


FeedbackDisposition = Literal["good", "bad"]
"""How a person judged a run (ADR 0068)."""


class RunFeedback(ApiModel):
    """One immutable judgment of a kept run (ADRs 0068 and 0129)."""

    feedback_id: UUID

    run_id: UUID

    disposition: FeedbackDisposition

    reason: str | None = Field(
        description="Why the run was judged so; a bad judgment always has one.",
    )

    corrected_output: JsonValue = Field(
        description="What the run should have produced, given only with a bad judgment.",
    )

    created_at: datetime

    command: str = Field(
        description="The `azathoth` command that shows the run judged.",
    )


RunSource = Literal["configured", "benchmark", "experiment", "production"]
"""What made a kept run: a run asked for, a benchmark's case, an optimization's, or production."""


class RunSummary(ApiModel):
    """One kept run of a workflow, as a list of its runs shows it (ADR 0121)."""

    run_id: UUID

    workflow_id: UUID

    workflow_name: str = Field(
        description="The workflow's name in the revision that ran.",
    )

    workflow_revision: int | None = Field(
        description="The revision that ran, or None for a run recorded before revisions.",
    )

    invocation_id: UUID | None = Field(
        description="The production invocation the run executed, when it executed one.",
    )

    succeeded: bool = Field(
        description="Whether the run finished with its declared result, or without one declared.",
    )

    error: RunError | None

    sensitivity: Sensitivity = Field(
        description=(
            "The run's label: the most sensitive of its input's and its parent run's, internal "
            "when neither is labelled (ADR 0123)."
        ),
    )

    started_at: datetime

    completed_at: datetime

    command: str = Field(
        description="The `azathoth` command that shows the run.",
    )

    feedback: FeedbackDisposition | None = Field(
        default=None,
        description="The run's latest judgment, or None when it was never judged (ADR 0129).",
    )

    source: RunSource = Field(
        default="configured",
        description=(
            "What made the run: `production` for an invocation's, `experiment` for an "
            "optimization's, `benchmark` for a benchmark case's, and otherwise `configured` "
            "(ADR 0140)."
        ),
    )


class StepMetrics(ApiModel):
    """What a step's strategy measured as it ran; what it did not measure is None."""

    provider: str | None

    model: str | None

    prompt_tokens: int | None

    completion_tokens: int | None

    total_tokens: int | None

    latency_ms: int | None

    estimated_cost_usd: float | None


class StepFailure(ApiModel):
    """One attempt of a step that failed."""

    attempt: int = Field(
        ge=1,
    )

    exception_type: str

    message: str


class StepResource(ApiModel):
    """One resource an executed step's strategy used, such as a model it called (ADR 0140)."""

    kind: str

    identifier: str

    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="What the strategy recorded of the resource, by name.",
    )


class RunStepDetail(RunStep):
    """One step of a kept run, with what it produced and every attempt that failed."""

    layer: int = Field(
        ge=0,
        description="The dependency layer the step ran in.",
    )

    started_at: datetime | None = Field(
        description="When its first attempt started; None for a step that never ran.",
    )

    completed_at: datetime | None = Field(
        description="When its last attempt finished; None for a step that never ran.",
    )

    strategy: str | None = Field(
        description="The name of the strategy an executed step ran: its prompt, or its tool.",
    )

    metrics: StepMetrics | None

    output: JsonValue = Field(
        default=None,
        description="What an executed step's strategy returned; None for any other.",
    )

    values: dict[str, JsonValue] = Field(
        description="The values the step added to the run's context, by name.",
    )

    failures: tuple[StepFailure, ...] = Field(
        description="Each attempt that failed, in order; a failed step's last is its failure.",
    )

    resources: tuple[StepResource, ...] = Field(
        default=(),
        description="The resources an executed step's strategy used, in the order it named them.",
    )


class RunLineage(ApiModel):
    """Where a run a step of another run started came from (ADRs 0104 and 0140)."""

    depth: int = Field(
        ge=0,
        description="How far below its root run it is: 1 for a run its root's step started.",
    )

    parent_workflow_id: UUID

    parent_run_id: UUID

    parent_step_id: UUID

    parent_attempt: int = Field(
        ge=1,
        description="The attempt of the parent step that started it.",
    )

    root_workflow_id: UUID

    root_run_id: UUID


class EvaluationEvidence(ApiModel):
    """One piece of what an evaluator judged by."""

    label: str

    value: JsonValue


class RunEvaluation(ApiModel):
    """One evaluator's judgment of a kept run, as it was recorded (ADR 0140)."""

    evaluation_id: UUID

    evaluated_at: datetime

    evaluator_name: str

    evaluator_version: str

    status: str = Field(
        description="What the evaluator concluded, such as `passed` or `failed`.",
    )

    score: float

    threshold: float

    reason: str

    evidence: tuple[EvaluationEvidence, ...]


class RunDetail(RunSummary):
    """One kept run with its input, its result and each of its steps."""

    has_result: bool = Field(
        description="Whether `result` holds the declared result, so a null result is not absence.",
    )

    result: JsonValue = None

    has_input: bool = Field(
        description="Whether `input` holds the run's input, so a null input is not absence.",
    )

    input: JsonValue = None

    resumes: int = Field(
        ge=0,
        description="How often another process resumed the run.",
    )

    steps: tuple[RunStepDetail, ...] = Field(
        description="Every step, in the order the run recorded them.",
    )

    lineage: RunLineage | None = Field(
        default=None,
        description="Where a run another run's step started came from; None for any other run.",
    )

    evaluations: tuple[RunEvaluation, ...] = Field(
        default=(),
        description="Every evaluator judgment of the run, in the order they were recorded.",
    )


class StepTrial(ApiModel):
    """One step of a workflow document, tried alone and kept nowhere (ADR 0121)."""

    step: RunStepDetail

    warnings: tuple[str, ...] = Field(
        description="What went wrong beside the step, such as an event callback that raised.",
    )


class CitationRecord(ApiModel):
    """The checks one cited step of a run kept, in the content store (ADRs 0116 and 0140)."""

    step_id: UUID

    record: str = Field(
        description="The digest the record is kept under.",
    )

    checks: tuple[dict[str, JsonValue], ...] | None = Field(
        description="Each check, in the order the step's reply held them; None when not kept.",
    )


class InvocationDetail(ApiModel):
    """One invocation as it was recorded: its input, who made it, its outcome and its run."""

    invocation_id: UUID

    workflow_id: UUID

    created_at: datetime

    status: Literal["succeeded", "failed", "incomplete"]

    result: JsonValue = None

    error: InvocationError | None

    idempotency_key: str | None

    input: JsonValue

    sensitivity: Sensitivity = Field(
        description=(
            "The invocation's label: the most sensitive of its input's and its parent run's, "
            "internal when neither is labelled (ADR 0123)."
        ),
    )

    caller_metadata: dict[str, JsonValue]

    run: InvocationRun | None

    command: str = Field(
        description="The `azathoth` command that shows the invocation.",
    )

    request_digest: str | None = Field(
        default=None,
        description="The digest of the request a keyed invocation was made under (ADR 0097).",
    )

    lineage: RunLineage | None = Field(
        default=None,
        description="Where one a step of another run made came from; None for any other.",
    )

    input_provenance: dict[str, JsonValue] | None = Field(
        default=None,
        description="Where its input was read from, when it was read (ADR 0112).",
    )

    citations: tuple[CitationRecord, ...] = Field(
        default=(),
        description="The checks each cited step of its run kept, in the order it kept them.",
    )


class StandardTool(ApiModel):
    """One tool of the standard library, as initializing a database, or installing it, left it."""

    name: str

    version: str

    revision: int = Field(
        ge=1,
        description="The revision of the tool version that is now current.",
    )

    installed: bool = Field(
        description="Whether installing imported it, rather than finding it already there.",
    )

    identical_to: int | None = Field(
        default=None,
        ge=1,
        description="An earlier revision with the same content as the one installed, if any.",
    )


class Initialization(ApiModel):
    """What initializing a database did, as `azathoth init` reports it."""

    database: str

    outcome: Literal["created", "upgraded", "current"]

    tools: tuple[StandardTool, ...]


class RunStarted(ApiModel):
    """A run is about to start."""

    type: Literal["run_started"] = "run_started"

    workflow_id: UUID

    run_id: UUID | None = Field(
        default=None,
        description=(
            "The run, named before it starts: the new run of `runs.run`, or the run a resume "
            "goes on with. An invocation's run is named through its invocation, so it is None "
            "for one (ADR 0139)."
        ),
    )


class StepStarted(ApiModel):
    """A step began its first attempt; retries never start it again."""

    type: Literal["step_started"] = "step_started"

    step_id: UUID

    layer: int = Field(
        ge=0,
        description="The dependency layer the step runs in; steps of one layer run together.",
    )

    message: str | None


class StepFinished(ApiModel):
    """A step reached its final status."""

    type: Literal["step_finished"] = "step_finished"

    step_id: UUID

    layer: int = Field(
        ge=0,
    )

    status: Literal["executed", "failed", "skipped"]

    failure: str | None = Field(
        description="The message of a failed step's final attempt.",
    )

    confidence: float | None

    emits_values: bool = Field(
        default=False,
        description=(
            "Whether the step declares that it emits its values, as `--output jsonl` shows "
            "them (ADR 0140)."
        ),
    )


class ContextChanged(ApiModel):
    """A step added values to the run's context: the names it declared, with their values."""

    type: Literal["context_changed"] = "context_changed"

    step_id: UUID

    values: dict[str, JsonValue]


class RunFinished(ApiModel):
    """A run finished and was kept."""

    type: Literal["run_finished"] = "run_finished"

    run_id: UUID

    succeeded: bool


class InvocationFinished(ApiModel):
    """An invocation reached its outcome, whether it ran, replayed or was refused."""

    type: Literal["invocation_finished"] = "invocation_finished"

    invocation_id: UUID | None = Field(
        description="The invocation, or None when the request was rejected before one was made.",
    )

    status: Literal["succeeded", "failed", "rejected", "incomplete"]


class ExperimentHeader(ApiModel):
    """What every view of one recorded optimization experiment carries (ADR 0131)."""

    experiment_id: UUID

    workflow_id: UUID

    workflow_name: str = Field(
        description="The workflow's name, as its winning candidate recorded it.",
    )

    recorded_at: datetime

    benchmark_id: UUID | None = Field(
        description="The benchmark its candidates ran, or None from before benchmark optimization.",
    )

    benchmark_digest: str | None = Field(
        description="The content digest of the benchmark it ran, or None when not recorded.",
    )

    benchmark_revision: int | None = Field(
        description=(
            "The latest benchmark revision holding the content it ran, or None when none does."
        ),
    )

    sensitivity: Sensitivity = Field(
        description="The label of the benchmark it ran, internal when it has none (ADR 0123).",
    )

    candidate_count: int = Field(
        ge=1,
    )

    case_count: int = Field(
        ge=1,
        description="How many cases each candidate was judged on.",
    )

    winner_observation_id: UUID

    command: str = Field(
        description="The `azathoth` command that shows it.",
    )


class ExperimentSummary(ExperimentHeader):
    """One recorded experiment, as a workflow's list shows it (ADR 0131)."""

    winner_score: float = Field(
        description="Its winning candidate's overall score.",
    )


class ExperimentCase(ApiModel):
    """How one case went for one candidate of an experiment."""

    case_id: UUID | None = Field(
        description="The benchmark case, or None from before benchmark optimization.",
    )

    run_id: UUID = Field(
        description="The run the case ran as, kept as any run is.",
    )

    evaluation_id: UUID

    passed: bool | None = Field(
        description="Whether it passed, or None when it was not recorded.",
    )

    judge_calls: int = Field(
        ge=0,
    )

    judge_cost_usd: float = Field(
        ge=0.0,
        description="What judging it cost, which is never charged to the candidate.",
    )


class ExperimentStep(ApiModel):
    """One step of a candidate, as its first case's run ran it."""

    step_id: UUID

    strategy_id: UUID | None = Field(
        description="The strategy the step ran, or None for a step that did not run.",
    )

    model: str | None = Field(
        description="The provider-qualified model it ran on, or None for a step with no model.",
    )


class ExperimentCandidate(ApiModel):
    """One candidate of an experiment, in its place in the ranking."""

    observation_id: UUID

    rank: int = Field(
        ge=1,
        description="Its place in the ranking, from 1 for the winner.",
    )

    workflow_revision: int | None = Field(
        description="The workflow revision it was generated from, or None when not recorded.",
    )

    strategy_ids: tuple[UUID, ...] = Field(
        description="The strategies its steps ran with, which identify the candidate.",
    )

    steps: tuple[ExperimentStep, ...] = Field(
        description=(
            "Each step, with the model it ran on, while its first case's run is kept; "
            "empty once it is not."
        ),
    )

    cases_run: int = Field(
        ge=1,
    )

    cases_passed: int | None = Field(
        description="How many of its cases passed, or None when any outcome is unknown.",
    )

    scorecard: CandidateScorecard

    judge_calls: int = Field(
        ge=0,
    )

    judge_cost_usd: float = Field(
        ge=0.0,
    )

    cases: tuple[ExperimentCase, ...] = Field(
        description="Every case it was judged on, in the order it ran them.",
    )


class ExperimentDetail(ExperimentHeader):
    """One recorded experiment, with every candidate in rank order (ADR 0131)."""

    candidates: tuple[ExperimentCandidate, ...] = Field(
        description="Every candidate, best first.",
    )


ComparisonBaseline = Literal["production", "configured"]
"""What an experiment's winner is compared against: what production runs, or what is configured."""


class ComparedStep(ApiModel):
    """One step of the winner and of the baseline, each with the model it ran on."""

    step_id: UUID

    winner_model: str | None

    baseline_model: str | None

    differs: bool = Field(
        description="Whether the two ran the step on different models.",
    )


class ComparedCase(ApiModel):
    """One case, as the winner and the baseline did on it."""

    case_id: UUID | None

    winner_passed: bool | None

    baseline_passed: bool | None

    winner_score: float | None = Field(
        description="The winner's evaluation score, or None once the evaluation is not kept.",
    )

    baseline_score: float | None


class RunCosts(ApiModel):
    """What one candidate's case runs cost and took, each the mean over the runs still kept."""

    runs: int = Field(
        ge=0,
        description="How many of its case runs are kept, and so measured.",
    )

    cost_usd: float | None = Field(
        description="The mean cost of a run, or None when any kept run's cost is unknown.",
    )

    latency_seconds: float | None = Field(
        description="The mean time a run took, or None when no run is kept.",
    )


class Savings(ApiModel):
    """What the winner saves per run on the benchmark, measured: a negative saving is a cost."""

    cost_usd: float | None = Field(
        description="The baseline's mean cost less the winner's, or None when either is unknown.",
    )

    cost_percent: float | None = Field(
        description="That saving as a percentage of the baseline's cost, or None when undefined.",
    )

    latency_seconds: float | None = Field(
        description="The baseline's mean time less the winner's, or None when either is unknown.",
    )

    latency_percent: float | None = Field(
        description="That saving as a percentage of the baseline's time, or None when undefined.",
    )


class SavingsProjection(ApiModel):
    """The saving per run multiplied by production's recent invocations: a projection, not a fact.

    The benchmark's cases may not resemble production's inputs, and the next
    window may not resemble the last.
    """

    window_days: int = Field(
        ge=1,
        description="How many days of production invocations it counts.",
    )

    since: datetime = Field(
        description="When that window began.",
    )

    invocations: int = Field(
        ge=1,
        description="How many invocations production made of the workflow in the window.",
    )

    cost_usd: float | None = Field(
        description="What the window's invocations would have saved, or None when unknown.",
    )

    latency_seconds: float | None = Field(
        description="The time they would have saved, in seconds, or None when unknown.",
    )


class Promotability(ApiModel):
    """Whether an experiment's winner can still be promoted, and why not when it cannot (ADR 0131).

    It is what `production.promote` would decide, asked without saving
    anything: the winner rebuilt from the workflow's latest revision with the
    models authorized now.
    """

    experiment_id: UUID

    workflow_id: UUID

    promotable: bool

    code: str | None = Field(
        description="The code `production.promote` would refuse with, or None when it would not.",
    )

    reason: str | None = Field(
        description="Why it would refuse, or None when it would not.",
    )

    command: str = Field(
        description="The `azathoth workflow promote` command that promotes the winner.",
    )


class ExperimentComparison(ApiModel):
    """An experiment's winner set beside what promoting it would replace (ADR 0131)."""

    experiment_id: UUID

    workflow_id: UUID

    baseline: ComparisonBaseline | None = Field(
        description="What the winner is compared against, or None when there is nothing to.",
    )

    reason: str | None = Field(
        description="Why nothing is compared, or None when something is.",
    )

    winner: ExperimentCandidate

    baseline_candidate: ExperimentCandidate | None

    steps: tuple[ComparedStep, ...] = Field(
        description="Each step either side's kept run ran, in the winner's order.",
    )

    cases: tuple[ComparedCase, ...] = Field(
        description="Every case, in the order the candidates ran them.",
    )

    winner_runs: RunCosts

    baseline_runs: RunCosts | None

    command: str = Field(
        description="The `azathoth workflow promote` command that promotes the winner.",
    )

    savings: Savings | None = Field(
        description="What the winner saves per run, measured on the benchmark, or None.",
    )

    projection: SavingsProjection | None = Field(
        description=(
            "The saving over production's invocations in the last 30 days, or None without any."
        ),
    )


class CaseStarted(ApiModel):
    """One case of a benchmark is about to run as one workflow (ADR 0130)."""

    type: Literal["case_started"] = "case_started"

    case_id: UUID

    workflow_id: UUID

    index: int = Field(
        ge=1,
        description="Its place among the workflow's cases, from 1.",
    )

    total: int = Field(
        ge=1,
        description="How many cases the workflow runs.",
    )


class CaseFinished(ApiModel):
    """One case of a benchmark ran as one workflow, and was judged."""

    type: Literal["case_finished"] = "case_finished"

    case_id: UUID

    workflow_id: UUID

    run_id: UUID = Field(
        description="The run the case ran as, kept as any run is.",
    )

    passed: bool

    score: float = Field(
        description="The evaluation's score, from 0 to 1.",
    )


BenchmarkEvent = Annotated[
    CaseStarted | CaseFinished,
    Field(discriminator="type"),
]
"""One event of a benchmark execution, told apart by its `type`."""


class GenerationStarted(ApiModel):
    """One generation of an optimization session is about to run its candidates (ADR 0131)."""

    type: Literal["generation_started"] = "generation_started"

    generation: int = Field(
        ge=1,
        description="Its number, from 1; the final evaluation is numbered after the last.",
    )

    candidates: int = Field(
        ge=1,
        description="How many candidates it runs.",
    )

    final: bool = Field(
        description="Whether it is the final evaluation of the last generation's proposals.",
    )


class CandidateFinished(ApiModel):
    """One candidate of a generation ran every case, and was scored."""

    type: Literal["candidate_finished"] = "candidate_finished"

    generation: int = Field(
        ge=1,
    )

    workflow_id: UUID

    strategy_ids: tuple[UUID, ...] = Field(
        description="The strategies its steps ran with, which identify the candidate.",
    )

    cases_run: int = Field(
        ge=0,
    )

    cases_passed: int = Field(
        ge=0,
    )

    overall_score: float


class GenerationFinished(ApiModel):
    """One generation's experiment was recorded, and its winner chosen."""

    type: Literal["generation_finished"] = "generation_finished"

    generation: int = Field(
        ge=1,
    )

    experiment_id: UUID = Field(
        description="The experiment that measured it, which `experiments.get` reads.",
    )

    winner_strategy_ids: tuple[UUID, ...]

    winner_score: float = Field(
        description="Its winner's overall score.",
    )

    proposed: int = Field(
        ge=0,
        description="How many candidates it proposes for the next generation; 0 after the final.",
    )


OptimizationEvent = Annotated[
    GenerationStarted | CandidateFinished | GenerationFinished,
    Field(discriminator="type"),
]
"""One event of an optimization session, told apart by its `type`."""


class OptimizationGeneration(ApiModel):
    """One generation of a session: the experiment that measured it, and what it proposed."""

    generation: int = Field(
        ge=1,
    )

    experiment_id: UUID

    winner_strategy_ids: tuple[UUID, ...]

    winner_score: float

    proposed: int = Field(
        ge=0,
        description="How many candidates it proposed for the next generation.",
    )


class OptimizationSummary(ApiModel):
    """What one optimization session measured, and which experiment holds its winner (ADR 0131)."""

    workflow_id: UUID

    benchmark_id: UUID

    generations: tuple[OptimizationGeneration, ...] = Field(
        min_length=1,
    )

    final_experiment_id: UUID | None = Field(
        description="The final evaluation's experiment (ADR 0091), or None when it did not run.",
    )

    final_skipped: str | None = Field(
        description="Why the final evaluation did not run, or None when it ran.",
    )

    winning_experiment_id: UUID = Field(
        description="The experiment whose winner is the session's winner, to compare and promote.",
    )

    judge_calls: int = Field(
        ge=0,
        description="Every judge call of every experiment, never charged to a candidate.",
    )

    judge_cost_usd: float = Field(
        ge=0.0,
    )

    command: str = Field(
        description="The `azathoth` command that shows the winning experiment.",
    )


SpendPeriod = Literal["day", "week", "month"]
"""How long each period of a spend report is (ADR 0132)."""

SpendGroup = Literal["workflow", "model", "provider", "source"]
"""What a spend report's spend is grouped by within each period."""


class SpendTotals(ApiModel):
    """What some model calls cost, billed and estimated apart (ADR 0132).

    Billed dollars are what a provider reported it charged; estimated ones
    Azathoth computed from a configured price. They are never added into
    one figure. An unpriced call is counted, never taken for free.
    """

    billed_usd: float = Field(ge=0.0)

    estimated_usd: float = Field(ge=0.0)

    calls: int = Field(ge=0)

    unpriced_calls: int = Field(
        ge=0,
        description="How many of the calls have no known cost.",
    )


class SpendGroupTotals(SpendTotals):
    """What one group's calls cost: a workflow's, a model's, a provider's or a source's."""

    key: str = Field(
        min_length=1,
        description=(
            "The group: a workflow's ID, `provider/model`, a provider, or a source, "
            "`unknown` where none is recorded."
        ),
    )

    label: str = Field(
        min_length=1,
        description="What the group is called: a workflow's name, or else its key.",
    )


class SpendPeriodTotals(ApiModel):
    """One period of a spend report, cut to the report's range at either end."""

    start: datetime

    end: datetime

    totals: SpendTotals

    groups: tuple[SpendGroupTotals, ...] = ()


class SpendReport(ApiModel):
    """What an instance spent from `since` up to `until`, period by period (ADR 0132).

    Every time is told in the report's time zone, with its offset. Every
    period of the range is listed, spent in or not.
    """

    since: datetime

    until: datetime

    time_zone: str = Field(min_length=1)

    period: SpendPeriod

    group: SpendGroup

    workflow_id: UUID | None = Field(
        description="The one workflow whose spend is reported, or None for every workflow.",
    )

    periods: tuple[SpendPeriodTotals, ...]

    groups: tuple[SpendGroupTotals, ...] = Field(
        description="Each group's spend over every period.",
    )

    totals: SpendTotals

    command: str = Field(
        description="The `azathoth spend` command that prints this report.",
    )


RunEvent = Annotated[
    RunStarted | StepStarted | StepFinished | ContextChanged | RunFinished | InvocationFinished,
    Field(discriminator="type"),
]
"""One event of a run, told apart by its `type`."""

_RUN_EVENT: TypeAdapter[RunEvent] = TypeAdapter(RunEvent)


def parse_run_event(
    data: str | bytes,
) -> RunEvent:
    """Return the run event one JSON document holds, as a client receiving events reads it."""

    return _RUN_EVENT.validate_json(data)


__all__ = [
    "API_STABILITY",
    "ApiModel",
    "ApiStability",
    "Author",
    "Backend",
    "BenchmarkDetail",
    "BenchmarkImport",
    "BenchmarkSummary",
    "ContextChanged",
    "DocumentProblem",
    "EvaluationEvidence",
    "Initialization",
    "InstanceDescription",
    "InvocationDetail",
    "InvocationError",
    "InvocationFinished",
    "InvocationOutcome",
    "InvocationRun",
    "ModelSummary",
    "PortfolioEntry",
    "PortfolioRemoval",
    "ProductionDependent",
    "ProductionStepUsage",
    "Revision",
    "RunDetail",
    "RunError",
    "RunEvaluation",
    "RunEvent",
    "RunFile",
    "RunFinished",
    "RunInput",
    "RunLineage",
    "RunResult",
    "RunSource",
    "RunStarted",
    "RunStep",
    "RunStepDetail",
    "RunSummary",
    "StandardTool",
    "StepFailure",
    "StepFinished",
    "StepKind",
    "StepMetrics",
    "StepReadiness",
    "StepResource",
    "StepStarted",
    "StepTrial",
    "ToolDetail",
    "ToolImport",
    "ToolSummary",
    "WorkflowCheck",
    "WorkflowDetail",
    "WorkflowImport",
    "WorkflowReadiness",
    "WorkflowSummary",
    "parse_run_event",
    "SpendGroup",
    "SpendGroupTotals",
    "SpendPeriod",
    "SpendPeriodTotals",
    "SpendReport",
    "SpendTotals",
    "DocumentExport",
    "GoalDetail",
    "GoalImport",
    "GoalSummary",
    "RevisionChange",
    "RevisionChangeKind",
    "RevisionComparison",
    "ModelRunUsage",
    "ModelUsage",
    "ModelUsageWorkflow",
    "StepAttemptUsage",
    "ToolExecutionUsage",
    "ToolRunUsage",
    "ToolUsage",
    "ToolUsageWorkflow",
]
