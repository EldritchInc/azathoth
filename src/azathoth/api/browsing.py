"""Browsing and importing the workflows, tools and benchmarks an instance holds (ADR 0120).

Each namespace reads and writes durable state only: no provider is reached
and no credential is needed. Importing never replaces anything: it appends
the next revision, as the matching `import` command does. Every value names
the `azathoth` command that shows the same thing, built here rather than by
callers.
"""

import json
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Final, TypeVar
from uuid import UUID

from pydantic import JsonValue, ValidationError
from pydantic_core import ErrorDetails

from azathoth.api.authorship import AuthorAccess
from azathoth.api.errors import (
    InvalidArgumentError,
    InvalidDocumentError,
    NotFoundError,
    RevisionNotFoundError,
)
from azathoth.api.models import (
    BenchmarkDetail,
    BenchmarkImport,
    BenchmarkSummary,
    DocumentProblem,
    Revision,
    ToolDetail,
    ToolImport,
    ToolSummary,
    WorkflowCheck,
    WorkflowDetail,
    WorkflowImport,
    WorkflowSummary,
)
from azathoth.evaluation import (
    BenchmarkDatasetRevision,
    BenchmarkDocumentError,
    decode_benchmark_document,
    earliest_identical_benchmark_revision,
    encode_benchmark_document,
)
from azathoth.persistence.repositories import Repositories
from azathoth.revisions import BaseRevisionError
from azathoth.tools import (
    ToolDocumentError,
    ToolDocumentRevision,
    decode_tool_document,
    earliest_identical_tool_revision,
    encode_tool_document,
    supported_tool_runtimes,
    unsupported_runtime_message,
)
from azathoth.workflows import (
    WorkflowDocumentError,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
    decode_workflow_document,
    earliest_identical_revision,
    encode_workflow_document,
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


def _revision(
    revision: AnyRevision,
    identical: AnyRevision | None,
) -> Revision:
    """Return the API's view of one revision, naming the revision it reverted to."""

    return Revision(
        number=revision.number,
        content_digest=revision.content_digest,
        imported_at=revision.imported_at,
        identical_to=identical.number if identical is not None else None,
    )


def _newest_first(
    history: Iterable[RevisionT],
    limit: int | None,
) -> tuple[RevisionT, ...]:
    """Return revisions newest first, at most `limit` of them."""

    newest = tuple(reversed(tuple(history)))

    return newest if limit is None else newest[:limit]


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

        summary = self._summary(selected, history, command=_workflow_command(selected))

        return WorkflowDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_workflow_document(selected.specification)),
        )

    def history(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[WorkflowSummary, ...]:
        """Return a workflow's revisions newest first, at most `limit` of them.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: No workflow has this ID.
        """

        _check_limit(limit)

        history = self._history(workflow_id)

        return tuple(
            self._summary(selected, history, command=_workflow_command(selected))
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

    @staticmethod
    def _summary(
        selected: WorkflowSpecificationRevision,
        history: tuple[WorkflowSpecificationRevision, ...],
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
            revision=_revision(selected, earliest_identical_revision(history, selected)),
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

        Raises:
            InstanceClosedError: The instance was closed.
        """

        repository = self._repositories().tools

        summaries: list[ToolSummary] = []

        for definition in repository.definitions():
            history = self._version_history(definition.id, definition.version)

            summaries.append(
                self._summary(
                    history[-1],
                    history,
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

        summary = self._summary(selected, history, command=_tool_command(selected))

        return ToolDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_tool_document(selected.document)),
        )

    def history(
        self,
        tool_id: UUID,
        *,
        version: str | None = None,
        limit: int | None = None,
    ) -> tuple[ToolSummary, ...]:
        """Return a tool's revisions newest first, of one version when it is named.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The tool, or the version named, is not configured.
        """

        _check_limit(limit)

        history = self._repositories().tools.document_revisions(tool_id)

        selected = tuple(
            revision for revision in history if version is None or revision.tool_version == version
        )

        if not selected:
            reference = f"{tool_id}@{version}" if version is not None else str(tool_id)

            raise NotFoundError(f"Tool {reference} is not configured.")

        return tuple(
            self._summary(revision, history, command=_tool_command(revision))
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
            revision=_revision(selected, earliest_identical_tool_revision(history, selected)),
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
    ) -> None:
        """Browse the benchmarks of the repositories `repositories` returns.

        Imports are recorded as the author `author` returns (ADR 0122).
        """

        self._repositories = repositories
        self._author = author

    def list(
        self,
    ) -> tuple[BenchmarkSummary, ...]:
        """Return every benchmark at its latest revision.

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

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No benchmark has this ID.
            RevisionNotFoundError: The benchmark has no revision with this number.
        """

        history = self._history(benchmark_id)

        selected = (
            history[-1]
            if revision is None
            else next((entry for entry in history if entry.number == revision), None)
        )

        if selected is None:
            raise RevisionNotFoundError(
                f"Benchmark dataset {benchmark_id} has no revision {revision}."
            )

        summary = self._summary(selected, history, command=_benchmark_command(selected))

        return BenchmarkDetail(
            **summary.model_dump(),
            latest_number=history[-1].number,
            document=_document(encode_benchmark_document(selected.dataset)),
        )

    def history(
        self,
        benchmark_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[BenchmarkSummary, ...]:
        """Return a benchmark's revisions newest first, at most `limit` of them.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: No benchmark has this ID.
        """

        _check_limit(limit)

        history = self._history(benchmark_id)

        return tuple(
            self._summary(selected, history, command=_benchmark_command(selected))
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
    def _summary(
        selected: BenchmarkDatasetRevision,
        history: tuple[BenchmarkDatasetRevision, ...],
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
            revision=_revision(selected, earliest_identical_benchmark_revision(history, selected)),
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
