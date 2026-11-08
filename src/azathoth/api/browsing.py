"""Browsing and importing the workflows, tools and benchmarks an instance holds (ADR 0120).

Each namespace reads and writes durable state only: no provider is reached
and no credential is needed. Importing never replaces anything: it appends
the next revision, as the matching `import` command does. Every value names
the `azathoth` command that shows the same thing, built here rather than by
callers.
"""

import json
import shlex
from collections.abc import Callable, Iterable, Mapping
from typing import Final, TypeVar
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.errors import (
    InvalidArgumentError,
    InvalidDocumentError,
    NotFoundError,
    RevisionNotFoundError,
)
from azathoth.api.models import (
    BenchmarkDetail,
    BenchmarkSummary,
    Revision,
    ToolDetail,
    ToolSummary,
    WorkflowDetail,
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


class Workflows:
    """The workflows of one instance: every import is a numbered revision."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Browse the workflows of the repositories `repositories` returns."""

        self._repositories = repositories

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

    def import_document(
        self,
        document: Document,
    ) -> WorkflowDetail:
        """Import one workflow document as its workflow's next revision, as `workflow import` does.

        A workflow must declare its result. Nothing is saved when the
        document is refused.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a workflow document, or declares
                no result.
        """

        try:
            specification = decode_workflow_document(_encoded(document))
        except WorkflowDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        if specification.result is None:
            raise InvalidDocumentError(RESULT_REQUIRED_MESSAGE)

        revision = self._repositories().workflows.save(specification)

        return self.get(specification.metadata.id, revision=revision.number)

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
    ) -> None:
        """Browse the tools of the repositories `repositories` returns."""

        self._repositories = repositories

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
    ) -> ToolDetail:
        """Import one tool document as its exact version's next revision, as `tool import` does.

        A document whose implementations use a runtime Azathoth cannot run,
        or whose artifacts belong to another tool or version, is refused and
        nothing is saved.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a tool document, or cannot be
                imported.
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

        try:
            revision = repository.save_document(decoded)
        except ValueError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        return self.get(revision.tool_id, revision.tool_version, revision=revision.number)

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
    ) -> None:
        """Browse the benchmarks of the repositories `repositories` returns."""

        self._repositories = repositories

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
    ) -> BenchmarkDetail:
        """Import one benchmark document as its dataset's next revision, as `benchmark import` does.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a benchmark document.
        """

        try:
            dataset = decode_benchmark_document(_encoded(document))
        except BenchmarkDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        revision = self._repositories().benchmarks.save(dataset)

        return self.get(dataset.id, revision=revision.number)

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
