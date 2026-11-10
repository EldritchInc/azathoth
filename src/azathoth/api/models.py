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

ApiStability = Literal["provisional", "stable"]
"""Whether the API is still provisional, or covered by the 1.x promise."""

API_STABILITY: Final[ApiStability] = "provisional"
"""The API's stability in this Azathoth: provisional until 1.4.0 final."""

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

    command: str = Field(
        description="The `azathoth` command that shows the model.",
    )


class ProductionStepUsage(ApiModel):
    """One step of a production workflow that uses a model."""

    step_id: UUID

    role: Literal["primary", "substitute"]


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

    content: bytes

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

    started_at: datetime

    completed_at: datetime

    command: str = Field(
        description="The `azathoth` command that shows the run.",
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

    caller_metadata: dict[str, JsonValue]

    run: InvocationRun | None

    command: str = Field(
        description="The `azathoth` command that shows the invocation.",
    )


class StandardTool(ApiModel):
    """One tool of the standard library, as initializing a database left it."""

    name: str

    version: str

    revision: int = Field(
        ge=1,
        description="The revision of the tool version that is now current.",
    )

    installed: bool = Field(
        description="Whether initializing imported it, rather than finding it already there.",
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
    "Backend",
    "BenchmarkDetail",
    "BenchmarkSummary",
    "ContextChanged",
    "DocumentProblem",
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
    "RunEvent",
    "RunFile",
    "RunFinished",
    "RunInput",
    "RunResult",
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
    "StepStarted",
    "ToolDetail",
    "ToolSummary",
    "WorkflowCheck",
    "WorkflowDetail",
    "WorkflowReadiness",
    "WorkflowSummary",
    "parse_run_event",
]
