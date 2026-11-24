"""Browsing and importing the workflows, tools and benchmarks an instance holds (ADR 0120).

Each namespace reads and writes durable state only: no provider is reached
and no credential is needed. Importing never replaces anything: it appends
the next revision, as the matching `import` command does. Every value names
the `azathoth` command that shows the same thing, built here rather than by
callers.
"""

import json
import re
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Final, TypeVar, cast
from uuid import UUID

from pydantic import JsonValue, ValidationError
from pydantic_core import ErrorDetails

from azathoth.api.authorship import AuthorAccess, author_view
from azathoth.api.benchmark_cases import (
    KEEP,
    Keep,
    case_detail,
    case_from_input,
    case_from_run,
    case_not_found_message,
    case_summary,
    check_not_duplicated,
    citation_expectation,
    comparison_of,
    edited_case,
    required_text,
)
from azathoth.api.benchmark_execution import (
    BenchmarkEventCallback,
    BenchmarkRuntimeAccess,
    Cancellable,
    compare_benchmark,
    run_benchmark,
)
from azathoth.api.benchmark_executions import (
    benchmark_revision,
    execution_detail,
    execution_not_found_message,
    execution_summary,
)
from azathoth.api.comparison import compare_documents, restricted_case_values
from azathoth.api.errors import (
    InvalidArgumentError,
    InvalidDocumentError,
    NotFoundError,
    RevisionNotFoundError,
)
from azathoth.api.files import resolved_file
from azathoth.api.mcp_tools import mcp_document
from azathoth.api.models import (
    BenchmarkCaseChange,
    BenchmarkCaseDetail,
    BenchmarkCaseSummary,
    BenchmarkDetail,
    BenchmarkExecutionDetail,
    BenchmarkExecutionSummary,
    BenchmarkImport,
    BenchmarkSummary,
    CaseCitations,
    CaseComparison,
    ComparisonCount,
    DocumentExport,
    DocumentProblem,
    Revision,
    RevisionComparison,
    RunFile,
    RunInput,
    StandardTool,
    ToolDetail,
    ToolImport,
    ToolSummary,
    ToolUsage,
    WorkflowCheck,
    WorkflowDetail,
    WorkflowImport,
    WorkflowSummary,
)
from azathoth.api.standard_tools import install_standard_tools
from azathoth.api.usage import tool_usage_of
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkDatasetRevision,
    BenchmarkDocumentError,
    decode_benchmark_document,
    earliest_identical_benchmark_revision,
    encode_benchmark_document,
)
from azathoth.inputs import JSON_MEDIA_TYPE, ResolvedInput
from azathoth.persistence.repositories import Repositories
from azathoth.revisions import BaseRevisionError, LineageRecord
from azathoth.sensitivity import Sensitivity
from azathoth.tools import (
    ToolDocumentError,
    ToolDocumentRevision,
    decode_tool_document,
    earliest_identical_tool_revision,
    encode_tool_document,
    supported_tool_runtimes,
    unsupported_runtime_message,
)
from azathoth.tools.mcp_execution import McpConnector
from azathoth.workflows import (
    WorkflowDocumentError,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
    decode_workflow_document,
    earliest_identical_revision,
    encode_workflow_document,
    tool_usage_report,
)

LIMIT_MESSAGE: Final = "A history limit must be at least 1."

RESULT_REQUIRED_MESSAGE: Final = "Workflow document must declare a result."

Document = str | Mapping[str, JsonValue]
"""A document to import: its JSON text, or its JSON values."""

RepositoriesAccess = Callable[[], Repositories]
"""Return an instance's repositories, or raise `InstanceClosedError`."""


AnyRevision = WorkflowSpecificationRevision | ToolDocumentRevision | BenchmarkDatasetRevision
"""A revision of any kind of component."""

RevisionT = TypeVar(
    "RevisionT",
    WorkflowSpecificationRevision,
    ToolDocumentRevision,
    BenchmarkDatasetRevision,
)


LineageView = Mapping[int, LineageRecord]
"""The lineage records of one lineage's revisions, by revision number."""


def _by_number(
    records: Iterable[LineageRecord],
) -> dict[int, LineageRecord]:
    """Return lineage records by the number of the revision each records."""

    return {record.number: record for record in records}


def _revision(
    revision: AnyRevision,
    identical: AnyRevision | None,
    lineage: LineageView,
) -> Revision:
    """Return the API's view of one revision, naming the revision it reverted to and its parent.

    Raises:
        LookupError: The revision's lineage is not recorded.
    """

    record = lineage.get(revision.number)

    if record is None:
        raise LookupError(f"Revision {revision.number} has no lineage record.")

    parent = next(
        (
            candidate
            for candidate in lineage.values()
            if candidate.revision_digest == record.parent_digest
        ),
        None,
    )

    return Revision(
        number=revision.number,
        content_digest=revision.content_digest,
        imported_at=revision.imported_at,
        identical_to=identical.number if identical is not None else None,
        revision_digest=record.revision_digest,
        parent_digest=record.parent_digest,
        parent_number=parent.number if parent is not None else None,
        author=author_view(record.author),
    )


def _newest_first(
    history: Iterable[RevisionT],
    limit: int | None,
) -> tuple[RevisionT, ...]:
    """Return revisions newest first, at most `limit` of them."""

    newest = tuple(reversed(tuple(history)))

    return newest if limit is None else newest[:limit]


def _numbered(
    history: Sequence[RevisionT],
    number: int,
    missing: str,
) -> RevisionT:
    """Return the revision of a history numbered `number`.

    Raises:
        RevisionNotFoundError: The history has no revision with this number,
            said as `missing`.
    """

    selected = next((entry for entry in history if entry.number == number), None)

    if selected is None:
        raise RevisionNotFoundError(missing)

    return selected


def _check_limit(
    limit: int | None,
) -> None:
    """Refuse a history limit below 1.

    Raises:
        InvalidArgumentError: The limit is below 1.
    """

    if limit is not None and limit < 1:
        raise InvalidArgumentError(LIMIT_MESSAGE)


def _encoded(
    document: Document,
) -> str:
    """Return a document to import as JSON text."""

    return document if isinstance(document, str) else json.dumps(dict(document))


_NOT_IN_A_NAME: Final = re.compile(r"[^a-z0-9.]+")


def export_name(
    name: str,
    *,
    kind: str,
    revision: int | None,
    version: str | None = None,
) -> str:
    """Return the file name an export suggests, such as `word-count-1.0.0.r3.tool.json`.

    The component's name, and a tool's version, keep their letters, digits
    and dots, lowercased, and anything else between them becomes one dash.
    A document not yet imported has no revision, so its name has none.
    """

    words = [part for part in (name, version) if part is not None]
    stem = "-".join(_NOT_IN_A_NAME.sub("-", part.lower()).strip("-.") for part in words).strip("-")
    numbered = "" if revision is None else f".r{revision}"

    return f"{stem or kind}{numbered}.{kind}.json"


def _document(
    encoded: str,
) -> dict[str, JsonValue]:
    """Return one encoded document as JSON values."""

    decoded: dict[str, JsonValue] = json.loads(encoded)

    return decoded


Location = tuple[str | int, ...]
"""Where in a document a value is: the keys and indexes leading to it."""


def _parsed(
    encoded: str,
) -> JsonValue:
    """Return a document's JSON values, or `None` when it is not JSON."""

    try:
        parsed: JsonValue = json.loads(encoded)
    except ValueError:
        return None

    return parsed


def _child(
    node: JsonValue,
    key: str | int,
) -> tuple[bool, JsonValue]:
    """Return whether a document's node holds a key, and the value it holds there."""

    if isinstance(node, dict) and isinstance(key, str) and key in node:
        return True, node[key]

    if isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
        return True, node[key]

    return False, None


def _is_choice_label(
    key: str | int,
    *,
    last: bool,
) -> bool:
    """Return whether a key a document does not hold names one choice of a union.

    Pydantic labels each choice it tried by its model, or by its validator
    and model; the document's own keys are lower case.
    """

    return isinstance(key, str) and (not last or key[:1].isupper() or "[" in key)


def _split(
    location: Sequence[str | int],
    document: JsonValue,
) -> tuple[Location, tuple[tuple[Location, str], ...]]:
    """Return a location without its choice labels, and each choice it took, where.

    Each choice is named by the error's location up to it, labels and all,
    so that the same union within two different choices is two unions,
    and by the label of the choice judged.
    """

    plain: list[str | int] = []
    choices: list[tuple[Location, str]] = []
    node: JsonValue = document

    for index, key in enumerate(location):
        held, value = _child(node, key)

        if held:
            plain.append(key)
            node = value
        elif isinstance(key, str) and _is_choice_label(key, last=index == len(location) - 1):
            choices.append((tuple(location[:index]), key))
        else:
            plain.append(key)
            node = None

    return tuple(plain), tuple(choices)


Split = tuple[Location, tuple[tuple[Location, str], ...], ErrorDetails]
"""One validation error: where it is without labels, the choices it took, and the error."""


def _nearest_choices(
    errors: Sequence[Split],
) -> list[Split]:
    """Keep the errors of the choice each union most nearly matched.

    The nearest choice lacks the fewest values the document does not have,
    then has the fewest errors. Unions are decided from the innermost out,
    so a choice is judged by the nearest of the choices within it. A tie
    keeps the choice Pydantic tried first.
    """

    kept = list(errors)
    unions = sorted(
        {where for _, choices, _ in kept for where, _ in choices},
        key=len,
        reverse=True,
    )

    for where in unions:
        scores: dict[str, tuple[int, int]] = {}

        for _, choices, error in kept:
            for at, label in choices:
                if at == where:
                    missing, count = scores.get(label, (0, 0))
                    scores[label] = (missing + (error["type"] == "missing"), count + 1)

        if not scores:
            continue

        nearest = min(scores, key=lambda label: scores[label])

        kept = [
            error
            for error in kept
            if all(label == nearest for at, label in error[1] if at == where)
        ]

    return kept


def _follows_from_others(
    location: Location,
    error: ErrorDetails,
    errors: Sequence[Split],
) -> bool:
    """Return whether an error only follows from errors within the value it is about.

    A collection whose items were refused is too short once they are left
    out, which says nothing the items' own problems do not.
    """

    return error["type"] == "too_short" and any(
        len(other) > len(location) and other[: len(location)] == location for other, _, _ in errors
    )


def _step_id(
    location: Location,
    document: JsonValue,
) -> UUID | None:
    """Return the id of the step a location is in, when it is in a step whose id is valid."""

    if len(location) < 2 or location[0] != "steps" or not isinstance(location[1], int):
        return None

    _, steps = _child(document, "steps")
    _, step = _child(steps, location[1])
    _, step_id = _child(step, "id")

    if not isinstance(step_id, str):
        return None

    try:
        return UUID(step_id)
    except ValueError:
        return None


def _problems(
    errors: Sequence[ErrorDetails],
    document: JsonValue,
) -> tuple[DocumentProblem, ...]:
    """Return the problems a document's validation errors are, in order."""

    split = [(*_split(error["loc"], document), error) for error in errors]
    kept = _nearest_choices(split)

    return tuple(
        DocumentProblem(
            message=str(error["msg"]).removeprefix("Value error, "),
            location=location,
            step_id=_step_id(location, document),
        )
        for location, _, error in kept
        if not _follows_from_others(location, error, kept)
    )


class Workflows:
    """The workflows of one instance: every import is a numbered revision."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        author: AuthorAccess,
    ) -> None:
        """Browse the workflows of the repositories `repositories` returns.

        Imports are recorded as the author `author` returns (ADR 0122).
        """

        self._repositories = repositories
        self._author = author

    def list(
        self,
    ) -> tuple[WorkflowSummary, ...]:
        """Return every workflow at its latest revision, in first-import order.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        repository = self._repositories().workflows

        summaries: list[WorkflowSummary] = []

        for specification in repository.specifications():
            history = repository.revisions(specification.metadata.id)

            summaries.append(
                self._summary(
                    history[-1],
                    history,
                    _by_number(repository.lineage(specification.metadata.id)),
                    command=f"azathoth workflow show {specification.metadata.id}",
                )
            )

        return tuple(summaries)

    def get(
        self,
        workflow_id: UUID,
        *,
        revision: int | None = None,
    ) -> WorkflowDetail:
        """Return one revision of a workflow with its document, the latest by default.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No workflow has this ID.
            RevisionNotFoundError: The workflow has no revision with this number.
        """

        history = self._history(workflow_id)

        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(f"Workflow {workflow_id} has no revision {revision}.")

        summary = self._summary(
            selected,
            history,
            self._lineage(workflow_id),
            command=_workflow_command(selected),
        )

        return WorkflowDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_workflow_document(selected.specification)),
        )

    def export(
        self,
        workflow_id: UUID,
        *,
        revision: int | None = None,
    ) -> DocumentExport:
        """Return one revision as the document `workflow export` prints, the latest by default.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No workflow has this ID.
            RevisionNotFoundError: The workflow has no revision with this number.
        """

        history = self._history(workflow_id)
        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(f"Workflow {workflow_id} has no revision {revision}.")

        return DocumentExport(
            text=encode_workflow_document(selected.specification) + "\n",
            file_name=export_name(
                selected.specification.metadata.name, kind="workflow", revision=selected.number
            ),
        )

    def compare_revisions(
        self,
        workflow_id: UUID,
        before: int,
        after: int,
    ) -> RevisionComparison:
        """Return what differs between two revisions of a workflow, as `workflow diff` prints it.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No workflow has this ID.
            RevisionNotFoundError: The workflow has no revision with one of
                these numbers.
        """

        history = self._history(workflow_id)
        lineage = self._lineage(workflow_id)
        old, new = (
            _numbered(history, number, f"Workflow {workflow_id} has no revision {number}.")
            for number in (before, after)
        )

        return compare_documents(
            self._summary(old, history, lineage, command=_workflow_command(old)).revision,
            self._summary(new, history, lineage, command=_workflow_command(new)).revision,
            (
                _document(encode_workflow_document(old.specification)),
                _document(encode_workflow_document(new.specification)),
            ),
        )

    def history(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[WorkflowSummary, ...]:
        """Return a workflow's revisions newest first, at most `limit` of them.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: No workflow has this ID.
        """

        _check_limit(limit)

        history = self._history(workflow_id)
        lineage = self._lineage(workflow_id)

        return tuple(
            self._summary(selected, history, lineage, command=_workflow_command(selected))
            for selected in _newest_first(history, limit)
        )

    def check(
        self,
        document: Document,
    ) -> WorkflowCheck:
        """Return whether importing a workflow document would accept it, and every reason not.

        Nothing is saved and no provider is reached. Each problem says where
        in the document it is, and names its step when it is in one. A step
        is checked as the kind of step it most nearly is, so a prompt step
        missing its model selection is not also told it lacks a tool. A rule
        of the whole workflow, such as that a step depends only on steps in
        it, is checked once every part is valid on its own.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        self._repositories()

        encoded = _encoded(document)

        try:
            specification = WorkflowSpecification.model_validate_json(encoded)
        except ValidationError as exc:
            return WorkflowCheck(
                valid=False,
                problems=_problems(exc.errors(), _parsed(encoded)),
            )

        if specification.result is None:
            return WorkflowCheck(
                valid=False,
                problems=(
                    DocumentProblem(
                        message=RESULT_REQUIRED_MESSAGE,
                        location=("result",),
                        step_id=None,
                    ),
                ),
            )

        return WorkflowCheck(valid=True, problems=())

    def import_document(
        self,
        document: Document,
        *,
        based_on: str | None = None,
    ) -> WorkflowImport:
        """Import one workflow document as its workflow's next revision, as `workflow import` does.

        The revision builds on the one whose revision digest is `based_on`,
        or on the latest without one; built on an earlier one than the
        latest, it forks (ADR 0122). A document identical to the revision it
        builds on appends nothing, and that revision is returned. A workflow
        must declare its result. Nothing is saved when the document is
        refused.

        It is the `import_workflow` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a workflow document, or declares
                no result.
            RevisionNotFoundError: No revision of the workflow has the
                digest `based_on`.
            InvalidAuthorError: Who is importing could not be told.
        """

        try:
            specification = decode_workflow_document(_encoded(document))
        except WorkflowDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        if specification.result is None:
            raise InvalidDocumentError(RESULT_REQUIRED_MESSAGE)

        repository = self._repositories().workflows

        try:
            saved = repository.save_revision(
                specification,
                author=self._author(),
                based_on=based_on,
            )
        except BaseRevisionError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

        return WorkflowImport(
            created=saved.created,
            workflow=self.get(specification.metadata.id, revision=saved.revision.number),
        )

    def _history(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowSpecificationRevision, ...]:
        """Return every revision of a workflow, oldest first.

        Raises:
            NotFoundError: No workflow has this ID.
        """

        history = self._repositories().workflows.revisions(workflow_id)

        if not history:
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        return history

    def _lineage(
        self,
        workflow_id: UUID,
    ) -> dict[int, LineageRecord]:
        """Return the lineage records of a workflow's revisions, by number."""

        return _by_number(self._repositories().workflows.lineage(workflow_id))

    @staticmethod
    def _summary(
        selected: WorkflowSpecificationRevision,
        history: tuple[WorkflowSpecificationRevision, ...],
        lineage: LineageView,
        *,
        command: str,
    ) -> WorkflowSummary:
        """Return the API's view of one workflow revision."""

        metadata = selected.specification.metadata

        return WorkflowSummary(
            id=metadata.id,
            name=metadata.name,
            version=metadata.version,
            description=metadata.description,
            revision=_revision(selected, earliest_identical_revision(history, selected), lineage),
            command=command,
        )


class Tools:
    """The tools of one instance: each exact version has its own numbered revisions."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        author: AuthorAccess,
    ) -> None:
        """Browse the tools of the repositories `repositories` returns.

        Imports are recorded as the author `author` returns (ADR 0122).
        """

        self._repositories = repositories
        self._author = author

    def list(
        self,
    ) -> tuple[ToolSummary, ...]:
        """Return every tool version at its latest revision.

        It is the `read_catalog` action (ADR 0127).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        return self._summaries(None)

    def versions(
        self,
        tool_id: UUID,
    ) -> tuple[ToolSummary, ...]:
        """Return each version of one tool at its latest revision, as `tool versions` lists them.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No version of the tool is configured.
        """

        versions = self._summaries(tool_id)

        if not versions:
            raise NotFoundError(f"Tool {tool_id} is not configured.")

        return versions

    def usage(
        self,
        tool_id: UUID,
    ) -> ToolUsage:
        """Return where one tool identity is configured, in production, and executed.

        Workflows require a tool by name, and run history records its
        identity, so configuration and production match the names any of
        its versions has, and history the identity alone. It is the
        `read_catalog` and `read_runs` actions (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No version of the tool is defined, and no run
                executed it.
        """

        repositories = self._repositories()
        usage = tool_usage_of(
            tool_usage_report(
                tool_id,
                definitions=repositories.tools.definitions(),
                specifications=repositories.workflows.specifications(),
                production_states=repositories.production_states.states(),
                runs=repositories.runs.runs(),
            )
        )

        if not usage.tool_names and not usage.workflows:
            raise NotFoundError(f"Tool {tool_id} is not configured.")

        return usage

    def _summaries(
        self,
        tool_id: UUID | None,
    ) -> tuple[ToolSummary, ...]:
        """Return each tool version at its latest revision, of one tool when it is named."""

        repository = self._repositories().tools

        summaries: list[ToolSummary] = []

        for definition in repository.definitions():
            if tool_id is not None and definition.id != tool_id:
                continue

            history = self._version_history(definition.id, definition.version)

            summaries.append(
                self._summary(
                    history[-1],
                    history,
                    _by_number(repository.document_lineage(definition.id, definition.version)),
                    command=(
                        f"azathoth tool show {definition.id} "
                        f"--version {shlex.quote(definition.version)}"
                    ),
                )
            )

        return tuple(summaries)

    def get(
        self,
        tool_id: UUID,
        version: str,
        *,
        revision: int | None = None,
    ) -> ToolDetail:
        """Return one revision of one exact tool version with its document.

        The latest revision of the version is returned unless another is named.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The tool has no such version.
            RevisionNotFoundError: The version has no revision with this number.
        """

        history = self._version_history(tool_id, version)

        if not history:
            raise NotFoundError(f"Tool {tool_id}@{version} is not configured.")

        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(f"Tool {tool_id}@{version} has no revision {revision}.")

        summary = self._summary(
            selected,
            history,
            _by_number(self._repositories().tools.document_lineage(tool_id, version)),
            command=_tool_command(selected),
        )

        return ToolDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_tool_document(selected.document)),
        )

    def export(
        self,
        tool_id: UUID,
        version: str,
        *,
        revision: int | None = None,
    ) -> DocumentExport:
        """Return one revision of one version as the document `tool export` prints.

        The latest revision of the version is exported unless another is
        named. It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The tool has no such version.
            RevisionNotFoundError: The version has no revision with this number.
        """

        history = self._version_history(tool_id, version)

        if not history:
            raise NotFoundError(f"Tool {tool_id}@{version} is not configured.")

        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(f"Tool {tool_id}@{version} has no revision {revision}.")

        return DocumentExport(
            text=encode_tool_document(selected.document) + "\n",
            file_name=export_name(
                selected.document.definition.name,
                kind="tool",
                revision=selected.number,
                version=version,
            ),
        )

    def compare_revisions(
        self,
        tool_id: UUID,
        version: str,
        before: int,
        after: int,
    ) -> RevisionComparison:
        """Return what differs between two revisions of one exact tool version, as `tool diff` does.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: The tool has no such version.
            RevisionNotFoundError: The version has no revision with one of
                these numbers.
        """

        history = self._version_history(tool_id, version)

        if not history:
            raise NotFoundError(f"Tool {tool_id}@{version} is not configured.")

        lineage = _by_number(self._repositories().tools.document_lineage(tool_id, version))
        old, new = (
            _numbered(history, number, f"Tool {tool_id}@{version} has no revision {number}.")
            for number in (before, after)
        )

        return compare_documents(
            self._summary(old, history, lineage, command=_tool_command(old)).revision,
            self._summary(new, history, lineage, command=_tool_command(new)).revision,
            (
                _document(encode_tool_document(old.document)),
                _document(encode_tool_document(new.document)),
            ),
        )

    def from_mcp(
        self,
        tool: str,
        *,
        url: str | None = None,
        command: Sequence[str] = (),
        authorization: str | None = None,
        grants: Sequence[str] = (),
        timeout_seconds: float | None = None,
        connect: McpConnector | None = None,
    ) -> DocumentExport:
        """Return the document of a tool an MCP server serves, as `tool from-mcp` prints it.

        The server is named by its `url`, or by the `command` that starts it,
        never both. Its implementation is pinned to the schemas the server
        serves now, and keeps `authorization`, the variable naming its
        bearer token, `grants`, the variables a started server is given, and
        `timeout_seconds`; listing is given that timeout, or 30 seconds.
        Nothing is imported: `import_document` keeps the document once a
        person has read it. `connect`, when given, is what the MCP client
        connects to, as tests do. It is the `tool_from_mcp` action, which
        starts a command on the instance's host (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The server is named both ways or neither,
                or the implementation could not be declared.
            NotFoundError: The server serves no tool by this name.
            McpUnavailableError: The server could not be reached or listed,
                or an authorization variable it needs is not set.
        """

        self._repositories()

        document = mcp_document(
            tool=tool,
            url=url,
            command=tuple(command),
            authorization=authorization,
            grants=tuple(grants),
            timeout_seconds=timeout_seconds,
            connect=connect,
        )
        definition = document.definition

        return DocumentExport(
            text=encode_tool_document(document) + "\n",
            file_name=export_name(
                definition.name, kind="tool", revision=None, version=definition.version
            ),
        )

    def history(
        self,
        tool_id: UUID,
        *,
        version: str | None = None,
        limit: int | None = None,
    ) -> tuple[ToolSummary, ...]:
        """Return a tool's revisions newest first, of one version when it is named.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The tool, or the version named, is not configured.
        """

        _check_limit(limit)

        repository = self._repositories().tools
        history = repository.document_revisions(tool_id)

        selected = tuple(
            revision for revision in history if version is None or revision.tool_version == version
        )

        if not selected:
            reference = f"{tool_id}@{version}" if version is not None else str(tool_id)

            raise NotFoundError(f"Tool {reference} is not configured.")

        lineages = {
            revision.tool_version: _by_number(
                repository.document_lineage(tool_id, revision.tool_version)
            )
            for revision in selected
        }

        return tuple(
            self._summary(
                revision,
                history,
                lineages[revision.tool_version],
                command=_tool_command(revision),
            )
            for revision in _newest_first(selected, limit)
        )

    def import_document(
        self,
        document: Document,
        *,
        based_on: str | None = None,
    ) -> ToolImport:
        """Import one tool document as its exact version's next revision, as `tool import` does.

        The revision builds on the one of its tool version whose revision
        digest is `based_on`, or on the latest without one; built on an
        earlier one than the latest, it forks (ADR 0122). A document
        identical to the revision it builds on appends nothing, and that
        revision is returned. A document whose implementations use a runtime
        Azathoth cannot run, or whose artifacts belong to another tool or
        version, is refused and nothing is saved.

        It is the `import_tool` action, and for a process tool the
        `import_process_tool` action too (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a tool document, or cannot be
                imported.
            RevisionNotFoundError: No revision of the tool version has the
                digest `based_on`.
            InvalidAuthorError: Who is importing could not be told.
        """

        try:
            decoded = decode_tool_document(_encoded(document))
        except ToolDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        runtimes = supported_tool_runtimes()

        for implementation in decoded.implementations:
            if implementation.runtime not in runtimes:
                raise InvalidDocumentError(unsupported_runtime_message(implementation))

        repository = self._repositories().tools
        author = self._author()

        try:
            saved = repository.save_document_revision(
                decoded,
                author=author,
                based_on=based_on,
            )
        except BaseRevisionError as exc:
            raise RevisionNotFoundError(str(exc)) from exc
        except ValueError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        revision = saved.revision

        return ToolImport(
            created=saved.created,
            tool=self.get(revision.tool_id, revision.tool_version, revision=revision.number),
        )

    def install_standard(
        self,
    ) -> tuple[StandardTool, ...]:
        """Install the standard tool library, as `tool install-standard` does (ADR 0095).

        A standard tool version not here is imported as its first revision,
        one whose latest revision is the standard document is left alone,
        and one whose latest differs gets the standard document as its next
        revision. Installing again is always safe. The standard tools are
        recorded as written by Azathoth, not by whoever installs them.

        It is the `install_standard_tools` action (ADR 0127).

        Raises:
            InstanceClosedError: The instance was closed.
            ConflictError: A standard tool's artifact belongs to another
                tool or version here.
        """

        return install_standard_tools(self._repositories().tools)

    def _version_history(
        self,
        tool_id: UUID,
        version: str,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return every revision of one exact tool version, oldest first."""

        return tuple(
            revision
            for revision in self._repositories().tools.document_revisions(tool_id)
            if revision.tool_version == version
        )

    @staticmethod
    def _summary(
        selected: ToolDocumentRevision,
        history: tuple[ToolDocumentRevision, ...],
        lineage: LineageView,
        *,
        command: str,
    ) -> ToolSummary:
        """Return the API's view of one tool revision."""

        definition = selected.document.definition

        return ToolSummary(
            id=definition.id,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            revision=_revision(
                selected,
                earliest_identical_tool_revision(history, selected),
                lineage,
            ),
            implementation_count=len(selected.document.implementations),
            test_case_count=len(selected.document.test_cases),
            command=command,
        )


class Benchmarks:
    """The benchmark datasets of one instance: every import is a numbered revision."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        author: AuthorAccess,
        runtime: BenchmarkRuntimeAccess,
    ) -> None:
        """Browse the benchmarks of the repositories `repositories` returns.

        Imports are recorded as the author `author` returns (ADR 0122), and
        benchmarks run in the runtime `runtime` composes, as runs do.
        """

        self._repositories = repositories
        self._author = author
        self._runtime = runtime

    def list(
        self,
    ) -> tuple[BenchmarkSummary, ...]:
        """Return every benchmark at its latest revision.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        repository = self._repositories().benchmarks

        summaries: list[BenchmarkSummary] = []

        for dataset in repository.datasets():
            history = repository.revisions(dataset.id)

            summaries.append(
                self._summary(
                    history[-1],
                    history,
                    _by_number(repository.lineage(dataset.id)),
                    command=f"azathoth benchmark show {dataset.id}",
                )
            )

        return tuple(summaries)

    def get(
        self,
        benchmark_id: UUID,
        *,
        revision: int | None = None,
    ) -> BenchmarkDetail:
        """Return one revision of a benchmark with its document, the latest by default.

        It is the `read_catalog` action, and for a restricted benchmark the
        `read_restricted` action too (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID.
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        history = self._history(benchmark_id)
        selected = self._selected(benchmark_id, history, revision)

        summary = self._summary(
            selected,
            history,
            _by_number(self._repositories().benchmarks.lineage(benchmark_id)),
            command=_benchmark_command(selected),
        )

        dataset = selected.dataset

        return BenchmarkDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_benchmark_document(dataset)),
            cited_cases=sum(case.expected.citations is not None for case in dataset.cases),
            comparisons=tuple(
                ComparisonCount(comparison=comparison.value, cases=count)
                for comparison, count in dataset.comparison_counts().items()
            ),
        )

    def export(
        self,
        benchmark_id: UUID,
        *,
        revision: int | None = None,
    ) -> DocumentExport:
        """Return one revision as the document `benchmark export` prints, the latest by default.

        It is the `read_catalog` action, and for a restricted benchmark the
        `read_restricted` action too (ADR 0133); its label is told, so a
        caller can say the export holds restricted data.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID.
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        history = self._history(benchmark_id)
        selected = self._selected(benchmark_id, history, revision)

        return DocumentExport(
            text=encode_benchmark_document(selected.dataset) + "\n",
            file_name=export_name(
                selected.dataset.name, kind="benchmark", revision=selected.number
            ),
            sensitivity=selected.dataset.sensitivity,
        )

    def cases(
        self,
        benchmark_id: UUID,
        *,
        revision: int | None = None,
    ) -> tuple[BenchmarkCaseSummary, ...]:
        """Return every case of one revision of a benchmark, in order, the latest by default.

        It is the `read_catalog` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID.
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        selected = self._selected(benchmark_id, self._history(benchmark_id), revision)

        return tuple(case_summary(selected, case) for case in selected.dataset.cases)

    def case(
        self,
        benchmark_id: UUID,
        case_id: UUID,
        *,
        revision: int | None = None,
    ) -> BenchmarkCaseDetail:
        """Return one case of one revision of a benchmark with its input and expected value.

        It is the `read_catalog` action, and for a restricted case the
        `read_restricted` action too (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID, or the revision holds no
                case with this ID.
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        selected = self._selected(benchmark_id, self._history(benchmark_id), revision)

        return case_detail(selected, self._held(selected, case_id))

    def create(
        self,
        name: str,
        description: str,
        *,
        version: str = "1.0.0",
    ) -> BenchmarkImport:
        """Create a benchmark with a new ID and no cases, as its revision 1.

        It is the `edit_benchmark` action (ADR 0130). A benchmark with no
        cases cannot be run until one is added.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The name, the description or the version is blank.
            InvalidAuthorError: Who is creating it could not be told.
        """

        dataset = BenchmarkDataset(
            name=required_text(name, "A benchmark's name"),
            description=required_text(description, "A benchmark's description"),
            version=required_text(version, "A benchmark's version"),
        )
        saved = self._repositories().benchmarks.save_revision(dataset, author=self._author())

        return BenchmarkImport(
            created=saved.created,
            benchmark=self.get(dataset.id, revision=saved.revision.number),
        )

    def add_case(
        self,
        benchmark_id: UUID,
        *,
        run_id: UUID | None = None,
        input: RunInput | None = None,
        file: RunFile | None = None,
        file_uri: str | None = None,
        comparison: CaseComparison,
        expected: JsonValue | Keep = KEEP,
        description: str | None = None,
        citations: CaseCitations | None = None,
        sensitivity: Sensitivity | None = None,
    ) -> BenchmarkCaseChange:
        """Append one case to a benchmark's latest revision, as its next revision.

        A case is made from exactly one of a recorded run (`run_id`), JSON
        (`input`) or a file (`file`, with the `file_uri` it was read from,
        if any), as `benchmark add-case` makes it (ADR 0086). A run's case
        replays the input it received and expects the value given, or else
        the corrected output of its latest bad judgment (ADR 0129). Any
        other case needs an expected value; JSON null is one, so `KEEP`
        gives none. A case is labelled as given, or as its run was, and
        never lower (ADR 0123).

        It is the `edit_benchmark` action, and when the case is made from a
        run the `read_runs` action too, and when the case is made from a run
        of restricted input the `read_restricted` action too (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID, or no run was kept with
                `run_id`.
            InvalidArgumentError: The case names no source or more than one,
                or Azathoth would refuse it, as `benchmark add-case` does.
            ContentUnavailableError: The content store no longer holds the
                content the run received.
            ConflictError: The benchmark already has this case.
            InvalidAuthorError: Who is adding it could not be told.
        """

        latest = self._history(benchmark_id)[-1]

        if sum(source is not None for source in (run_id, input, file)) != 1:
            raise InvalidArgumentError(
                "A case is made from exactly one of a run, JSON input and a file."
            )

        if file_uri is not None and file is None:
            raise InvalidArgumentError(
                "A file_uri names where a file was read from: give the file too."
            )

        judged_by = comparison_of(comparison)
        expectation = citation_expectation(citations)
        repositories = self._repositories()

        if run_id is not None:
            case = case_from_run(
                repositories,
                run_id,
                comparison=judged_by,
                expected=expected,
                description=description,
                citations=expectation,
                sensitivity=sensitivity,
            )
        else:
            case = case_from_input(
                (
                    resolved_file(file, repositories.content, uri=file_uri)
                    if file is not None
                    else ResolvedInput(
                        value=cast(RunInput, input).payload,
                        media_type=JSON_MEDIA_TYPE,
                    )
                ),
                comparison=judged_by,
                expected=expected,
                description=description,
                citations=expectation,
                sensitivity=sensitivity,
            )

        cases = (*latest.dataset.cases, case)

        check_not_duplicated(benchmark_id, cases, case)

        saved = self._save_cases(latest, cases)

        return BenchmarkCaseChange(
            case=case_detail(saved, case),
            benchmark=self._revision_summary(benchmark_id, saved),
        )

    def update_case(
        self,
        benchmark_id: UUID,
        case_id: UUID,
        *,
        comparison: CaseComparison | None = None,
        expected: JsonValue | Keep = KEEP,
        description: str | None = None,
        citations: CaseCitations | None | Keep = KEEP,
        sensitivity: Sensitivity | None = None,
    ) -> BenchmarkCaseChange:
        """Change what one case of a benchmark's latest revision expects, as its next revision.

        Only what is given changes: its comparison, its expected value (JSON
        null too, so `KEEP` leaves it), its description, what its run must
        cite (`None` clears it, `KEEP` leaves it) and its label, which may
        rise but never fall. Its ID, its input and where it came from stay.
        An edit that leaves the case as it was saves nothing. It is the
        `edit_benchmark` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID, or its latest revision
                holds no case with this ID.
            InvalidArgumentError: The edit changes nothing, or would make a
                case Azathoth refuses, or a lower label than the case's.
            ConflictError: Another case would then be the same case.
            InvalidAuthorError: Who is editing it could not be told.
        """

        latest = self._history(benchmark_id)[-1]
        edited = edited_case(
            self._held(latest, case_id),
            comparison=comparison,
            expected=expected,
            description=description,
            citations=citations,
            sensitivity=sensitivity,
        )
        cases = tuple(edited if case.id == case_id else case for case in latest.dataset.cases)

        check_not_duplicated(benchmark_id, cases, edited)

        saved = self._save_cases(latest, cases)

        return BenchmarkCaseChange(
            case=case_detail(saved, edited),
            benchmark=self._revision_summary(benchmark_id, saved),
        )

    def remove_case(
        self,
        benchmark_id: UUID,
        case_id: UUID,
    ) -> BenchmarkCaseChange:
        """Save a benchmark's next revision without one case of its latest.

        Every earlier revision still holds the case, so every execution that
        ran it can still be read. It is the `edit_benchmark` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID, or its latest revision
                holds no case with this ID.
            InvalidAuthorError: Who is removing it could not be told.
        """

        latest = self._history(benchmark_id)[-1]
        removed = self._held(latest, case_id)
        saved = self._save_cases(
            latest,
            tuple(case for case in latest.dataset.cases if case.id != case_id),
        )

        return BenchmarkCaseChange(
            case=case_detail(latest, removed),
            benchmark=self._revision_summary(benchmark_id, saved),
        )

    def executions(
        self,
        benchmark_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[BenchmarkExecutionSummary, ...]:
        """Return a benchmark's saved runs and comparisons, newest first, at most `limit`.

        Executions of a benchmark since removed stay readable, as `benchmark
        executions` lists them. It is the `read_runs` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The benchmark is neither configured nor has any
                saved execution.
        """

        _check_limit(limit)

        repositories = self._repositories()
        saved = repositories.benchmark_executions.executions_for_benchmark(benchmark_id)
        history = repositories.benchmarks.revisions(benchmark_id)

        if not saved and not history:
            raise NotFoundError(f"Benchmark dataset {benchmark_id} is not configured.")

        newest_first = sorted(
            reversed(saved),
            key=lambda execution: execution.recorded_at,
            reverse=True,
        )

        return tuple(
            execution_summary(execution, revision=benchmark_revision(history, execution))
            for execution in newest_first[:limit]
        )

    def execution(
        self,
        execution_id: UUID,
    ) -> BenchmarkExecutionDetail:
        """Return one saved run or comparison with every workflow, best first, and every case.

        Each case carries its evaluation's score and reason while the
        evaluation is kept, and each workflow the totals its case runs
        measured while every one of them is kept (ADR 0140). It is the
        `read_runs` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No execution was saved with this ID.
        """

        repositories = self._repositories()
        saved = repositories.benchmark_executions.get(execution_id)

        if saved is None:
            raise NotFoundError(execution_not_found_message(execution_id))

        evaluations = {
            case.evaluation_id: evaluation
            for candidate in saved.candidates
            for case in candidate.cases
            if (evaluation := repositories.run_evaluations.get(case.evaluation_id)) is not None
        }
        runs = {
            case.run_id: run
            for candidate in saved.candidates
            for case in candidate.cases
            if (run := repositories.runs.get(case.run_id)) is not None
        }

        return execution_detail(
            saved,
            revision=benchmark_revision(
                repositories.benchmarks.revisions(saved.benchmark_id), saved
            ),
            evaluations=evaluations,
            runs=runs,
        )

    def run(
        self,
        benchmark_id: UUID,
        workflow_id: UUID,
        *,
        on_event: BenchmarkEventCallback | None = None,
        cancel: Cancellable | None = None,
    ) -> BenchmarkExecutionDetail:
        """Run one configured workflow against a benchmark's latest revision, as `benchmark run`.

        Everything is checked before any case runs. `on_event` hears each
        case start and finish, on the caller's thread, and `cancel` is
        checked between cases: a cancelled benchmark keeps the case runs it
        finished and records no execution. It is the `run_benchmark` action
        (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark or workflow has the ID.
            InvalidArgumentError: The benchmark has no cases, a comparison
                cannot be evaluated, or the workflow declares no result.
            JudgeUnavailableError: A semantic case has no usable judge, or a
                judge failed.
            RunNotStartedError: The workflow cannot be generated.
            WorkflowResultMissingError: A run did not produce its declared result.
            RunCancelledError: `cancel` asked it to stop.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
        """

        return self.execution(
            run_benchmark(
                self._repositories(),
                self._runtime,
                benchmark_id,
                workflow_id,
                on_event=on_event,
                cancel=cancel,
            )
        )

    def compare(
        self,
        benchmark_id: UUID,
        workflow_ids: Sequence[UUID],
        *,
        target_latency_seconds: float,
        target_cost_usd: float,
        on_event: BenchmarkEventCallback | None = None,
        cancel: Cancellable | None = None,
    ) -> BenchmarkExecutionDetail:
        """Compare configured workflows against a benchmark, ranked, as `benchmark compare`.

        It needs two distinct workflows or more, each scored against the
        latency and cost targets given, and is told and cancelled as `run`
        is. It is the `run_benchmark` action (ADR 0130).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark or workflow has the ID.
            InvalidArgumentError: Fewer than two distinct workflows, a target
                that is not positive, or a benchmark that cannot run.
            JudgeUnavailableError: A semantic case has no usable judge, or a
                judge failed.
            RunNotStartedError: A workflow cannot be generated.
            WorkflowResultMissingError: A run did not produce its declared result.
            RunCancelledError: `cancel` asked it to stop.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
        """

        return self.execution(
            compare_benchmark(
                self._repositories(),
                self._runtime,
                benchmark_id,
                tuple(workflow_ids),
                target_latency_seconds=target_latency_seconds,
                target_cost_usd=target_cost_usd,
                on_event=on_event,
                cancel=cancel,
            )
        )

    def _save_cases(
        self,
        latest: BenchmarkDatasetRevision,
        cases: tuple[BenchmarkCase, ...],
    ) -> BenchmarkDatasetRevision:
        """Save the latest revision's dataset with `cases` as the benchmark's next revision.

        A dataset identical to the latest saves nothing, and the latest is returned.

        Raises:
            InvalidAuthorError: Who is saving it could not be told.
        """

        dataset = latest.dataset

        return (
            self._repositories()
            .benchmarks.save_revision(
                BenchmarkDataset(
                    id=dataset.id,
                    name=dataset.name,
                    description=dataset.description,
                    version=dataset.version,
                    cases=cases,
                ),
                author=self._author(),
            )
            .revision
        )

    def _revision_summary(
        self,
        benchmark_id: UUID,
        selected: BenchmarkDatasetRevision,
    ) -> BenchmarkSummary:
        """Return the API's view of one revision of a benchmark, with its history and lineage."""

        return self._summary(
            selected,
            self._history(benchmark_id),
            _by_number(self._repositories().benchmarks.lineage(benchmark_id)),
            command=_benchmark_command(selected),
        )

    @staticmethod
    def _held(
        selected: BenchmarkDatasetRevision,
        case_id: UUID,
    ) -> BenchmarkCase:
        """Return the case of a revision with this ID.

        Raises:
            NotFoundError: The revision holds no case with this ID.
        """

        found = next((case for case in selected.dataset.cases if case.id == case_id), None)

        if found is None:
            raise NotFoundError(case_not_found_message(selected.dataset_id, case_id))

        return found

    def compare_revisions(
        self,
        benchmark_id: UUID,
        before: int,
        after: int,
        *,
        include_restricted: bool = True,
    ) -> RevisionComparison:
        """Return what differs between two revisions of a benchmark, as `benchmark diff` does.

        A restricted case's input and expected value are told only with
        `include_restricted`; without it, each change leaves them out as
        `None` and says so.

        It is the `read_catalog` action, and for a restricted case the
        `read_restricted` action too (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID.
            RevisionNotFoundError: The benchmark has no revision with one of
                these numbers.
        """

        history = self._history(benchmark_id)
        lineage = _by_number(self._repositories().benchmarks.lineage(benchmark_id))
        old, new = (
            _numbered(
                history, number, f"Benchmark dataset {benchmark_id} has no revision {number}."
            )
            for number in (before, after)
        )

        return compare_documents(
            self._summary(old, history, lineage, command=_benchmark_command(old)).revision,
            self._summary(new, history, lineage, command=_benchmark_command(new)).revision,
            (
                _document(encode_benchmark_document(old.dataset)),
                _document(encode_benchmark_document(new.dataset)),
            ),
            withheld=(
                ((), ())
                if include_restricted
                else (restricted_case_values(old.dataset), restricted_case_values(new.dataset))
            ),
        )

    def history(
        self,
        benchmark_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[BenchmarkSummary, ...]:
        """Return a benchmark's revisions newest first, at most `limit` of them.

        It is the `read_catalog` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: No benchmark has this ID.
        """

        _check_limit(limit)

        history = self._history(benchmark_id)
        lineage = _by_number(self._repositories().benchmarks.lineage(benchmark_id))

        return tuple(
            self._summary(selected, history, lineage, command=_benchmark_command(selected))
            for selected in _newest_first(history, limit)
        )

    def import_document(
        self,
        document: Document,
        *,
        based_on: str | None = None,
    ) -> BenchmarkImport:
        """Import one benchmark document as its dataset's next revision, as `benchmark import` does.

        The revision builds on the one whose revision digest is `based_on`,
        or on the latest without one; built on an earlier one than the
        latest, it forks (ADR 0122). A document identical to the revision it
        builds on appends nothing, and that revision is returned.

        It is the `import_benchmark` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a benchmark document.
            RevisionNotFoundError: No revision of the benchmark has the
                digest `based_on`.
            InvalidAuthorError: Who is importing could not be told.
        """

        try:
            dataset = decode_benchmark_document(_encoded(document))
        except BenchmarkDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        repository = self._repositories().benchmarks

        try:
            saved = repository.save_revision(
                dataset,
                author=self._author(),
                based_on=based_on,
            )
        except BaseRevisionError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

        return BenchmarkImport(
            created=saved.created,
            benchmark=self.get(dataset.id, revision=saved.revision.number),
        )

    def _history(
        self,
        benchmark_id: UUID,
    ) -> tuple[BenchmarkDatasetRevision, ...]:
        """Return every revision of a benchmark, oldest first.

        Raises:
            NotFoundError: No benchmark has this ID.
        """

        history = self._repositories().benchmarks.revisions(benchmark_id)

        if not history:
            raise NotFoundError(f"Benchmark dataset {benchmark_id} is not configured.")

        return history

    @staticmethod
    def _selected(
        benchmark_id: UUID,
        history: tuple[BenchmarkDatasetRevision, ...],
        revision: int | None,
    ) -> BenchmarkDatasetRevision:
        """Return the revision numbered `revision` of a history, the latest without one.

        Raises:
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(
                f"Benchmark dataset {benchmark_id} has no revision {revision}."
            )

        return selected

    @staticmethod
    def _summary(
        selected: BenchmarkDatasetRevision,
        history: tuple[BenchmarkDatasetRevision, ...],
        lineage: LineageView,
        *,
        command: str,
    ) -> BenchmarkSummary:
        """Return the API's view of one benchmark revision."""

        dataset = selected.dataset

        return BenchmarkSummary(
            id=dataset.id,
            name=dataset.name,
            version=dataset.version,
            description=dataset.description,
            case_count=len(dataset.cases),
            sensitivity=dataset.sensitivity,
            revision=_revision(
                selected,
                earliest_identical_benchmark_revision(history, selected),
                lineage,
            ),
            command=command,
        )


def _workflow_command(
    selected: WorkflowSpecificationRevision,
) -> str:
    """Return the command that shows one exact workflow revision."""

    return f"azathoth workflow show {selected.workflow_id} --revision {selected.number}"


def _tool_command(
    selected: ToolDocumentRevision,
) -> str:
    """Return the command that prints one exact tool revision.

    `tool show` cannot select a revision, so this is `tool export`.
    """

    return (
        f"azathoth tool export {selected.tool_id} --version {shlex.quote(selected.tool_version)} "
        f"--revision {selected.number}"
    )


def _benchmark_command(
    selected: BenchmarkDatasetRevision,
) -> str:
    """Return the command that shows one exact benchmark revision."""

    return f"azathoth benchmark show {selected.dataset_id} --revision {selected.number}"


__all__ = [
    "LIMIT_MESSAGE",
    "RESULT_REQUIRED_MESSAGE",
    "Benchmarks",
    "Document",
    "RepositoriesAccess",
    "Tools",
    "Workflows",
]
