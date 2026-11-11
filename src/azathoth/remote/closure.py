"""Everything a pushed document needs at the remote, gathered from local repositories (ADR 0124).

A push sends the latest revision of each document it is given, with the
revisions it was reached by, and what that revision needs to run there: the
tool versions its tool steps resolve to here, the child workflows its
`run_workflow`, `map_workflow` and `loop_workflow` steps name as constants,
and the content its benchmark cases hold. Dependencies come before the
documents that need them, and each lineage's revisions oldest first.

Production state and the model portfolio are an instance's own, so a
closure never holds them.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.evaluation import BenchmarkDataset, BenchmarkRepository
from azathoth.inputs import ContentRef, content_ref_from_value
from azathoth.remote.records import ContentRecord, RevisionRecord
from azathoth.revisions import Lineage, LineageRecord, RevisionKind, json_digest
from azathoth.sensitivity import Sensitivity, effective_sensitivity, most_sensitive
from azathoth.tools import ToolMatcher, ToolRepository
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowConstantValue,
    WorkflowRepository,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

CHILD_WORKFLOW_INPUTS: Final = {
    "run_workflow": "call",
    "map_workflow": "settings",
    "loop_workflow": "settings",
}
"""The standard tools that start a child workflow, and the input that names it."""

RUNTIME: Final = "runtime"
"""What `child_workflow_id` returns for a child named only when its step runs."""


class Closure(BaseModel):
    """What a push of some documents sends, and what it could not gather.

    `unresolved` says, one sentence each, what the documents need that this
    instance could not supply, or that cannot be known before they run.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    revisions: tuple[RevisionRecord, ...] = ()

    content: tuple[ContentRecord, ...] = ()

    unresolved: tuple[str, ...] = ()


def ancestry(
    records: Iterable[LineageRecord],
) -> tuple[LineageRecord, ...]:
    """Return the latest revision of a lineage and the revisions it was reached by, oldest first.

    A revision saved on an earlier one forks its lineage; only the latest's
    own ancestors are part of its history.
    """

    history = tuple(records)
    by_digest = {record.revision_digest: record for record in history}
    latest = max(history, key=lambda record: record.number, default=None)
    chain: list[LineageRecord] = []

    while latest is not None:
        chain.append(latest)
        latest = None if latest.parent_digest is None else by_digest.get(latest.parent_digest)

    return tuple(reversed(chain))


def content_refs(
    value: JsonValue,
) -> Iterator[ContentRef]:
    """Yield every content handle in a JSON value, in document order."""

    ref = content_ref_from_value(value)

    if ref is not None:
        yield ref
    elif isinstance(value, dict):
        for member in value.values():
            yield from content_refs(member)
    elif isinstance(value, list):
        for item in value:
            yield from content_refs(item)


def child_workflow_id(
    step: WorkflowStepSpecification,
) -> UUID | Literal["runtime"] | None:
    """Return the child workflow a step starts, None for none, or `"runtime"` if bound later.

    Only a constant names a child before the step runs; one bound to a
    value is known only once the workflow runs.
    """

    specification = step.specification

    if not isinstance(specification, ToolStepSpecification):
        return None

    name = CHILD_WORKFLOW_INPUTS.get(specification.requirement.name)

    if name is None:
        return None

    for binding in step.inputs:
        if binding.name != name:
            continue

        source = binding.source

        if not isinstance(source, WorkflowConstantValue) or not isinstance(source.value, dict):
            return RUNTIME

        named = source.value.get("workflow_id")

        try:
            return UUID(named) if isinstance(named, str) else RUNTIME
        except ValueError:
            return RUNTIME

    return RUNTIME


@dataclass
class _Gathering:
    """The state of one closure as it is gathered."""

    workflows: WorkflowRepository
    tools: ToolRepository
    benchmarks: BenchmarkRepository
    visited: set[Lineage] = field(default_factory=set)
    revisions: list[RevisionRecord] = field(default_factory=list)
    content: dict[str, tuple[ContentRef, list[Sensitivity]]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

    def gather(
        self,
        lineage: Lineage,
    ) -> None:
        """Gather one lineage and, first, everything its latest revision needs."""

        if lineage in self.visited:
            return

        self.visited.add(lineage)
        chain = ancestry(self._lineage(lineage))

        if not chain:
            self.unresolved.append(f"This instance holds no {lineage}.")
            return

        documents: list[tuple[LineageRecord, BaseModel, str]] = []

        for record in chain:
            held = self._revision(lineage, record.number)

            if held is None:
                self.unresolved.append(
                    f"This instance holds no revision {record.number} of {lineage}."
                )
                return

            documents.append((record, held[0], held[1]))

        latest = documents[-1][1]

        if isinstance(latest, WorkflowSpecification):
            self._needs_of_workflow(latest)

        for record, document, digest in documents:
            dump = document.model_dump(mode="json")

            if json_digest(dump) != digest:
                self.unresolved.append(
                    f"Revision {record.number} of {lineage} no longer serializes to its content "
                    f"digest {digest}, so it cannot be pushed."
                )
                return

            if isinstance(document, BenchmarkDataset):
                self._content_of_benchmark(document)

        self.revisions.extend(
            RevisionRecord(
                lineage=lineage,
                revision_digest=record.revision_digest,
                parent_digest=record.parent_digest,
                content_digest=digest,
                author=record.author,
                document=document.model_dump(mode="json"),
            )
            for record, document, digest in documents
        )

    def _lineage(
        self,
        lineage: Lineage,
    ) -> tuple[LineageRecord, ...]:
        """Return every lineage record of one lineage."""

        if lineage.kind is RevisionKind.WORKFLOW:
            return self.workflows.lineage(lineage.id)

        if lineage.kind is RevisionKind.TOOL:
            assert lineage.version is not None

            return self.tools.document_lineage(lineage.id, lineage.version)

        return self.benchmarks.lineage(lineage.id)

    def _revision(
        self,
        lineage: Lineage,
        number: int,
    ) -> tuple[BaseModel, str] | None:
        """Return one numbered revision's document and content digest, or None."""

        if lineage.kind is RevisionKind.WORKFLOW:
            workflow = self.workflows.revision(lineage.id, number)

            return None if workflow is None else (workflow.specification, workflow.content_digest)

        if lineage.kind is RevisionKind.TOOL:
            assert lineage.version is not None
            tool = self.tools.document_revision(lineage.id, lineage.version, number)

            return None if tool is None else (tool.document, tool.content_digest)

        benchmark = self.benchmarks.revision(lineage.id, number)

        return None if benchmark is None else (benchmark.dataset, benchmark.content_digest)

    def _needs_of_workflow(
        self,
        specification: WorkflowSpecification,
    ) -> None:
        """Gather the tool versions and child workflows one specification's steps need."""

        workflow = specification.metadata.id
        definitions = self.tools.definitions()

        for step in specification.steps:
            if not isinstance(step.specification, ToolStepSpecification):
                continue

            requirement = step.specification.requirement
            matched = [
                definition
                for definition in definitions
                if ToolMatcher.matches(definition, requirement)
            ]

            if not matched:
                version = "of any version" if requirement.version is None else requirement.version
                self.unresolved.append(
                    f"Step {step.id} of workflow {workflow} requires tool {requirement.name} "
                    f"{version}, which this instance does not hold."
                )

            for definition in matched:
                self.gather(
                    Lineage(kind=RevisionKind.TOOL, id=definition.id, version=definition.version)
                )

            child = child_workflow_id(step)

            if child == RUNTIME:
                self.unresolved.append(
                    f"Step {step.id} of workflow {workflow} names its child workflow only when "
                    "it runs, so no child is pushed with it."
                )
            elif isinstance(child, UUID):
                self._child(step, workflow, Lineage(kind=RevisionKind.WORKFLOW, id=child))

    def _child(
        self,
        step: WorkflowStepSpecification,
        workflow: UUID,
        child: Lineage,
    ) -> None:
        """Gather a child workflow a step starts, or name it once when it is not held."""

        if child in self.visited:
            return

        if self.workflows.lineage(child.id):
            self.gather(child)
            return

        self.visited.add(child)
        self.unresolved.append(
            f"Step {step.id} of workflow {workflow} runs workflow {child.id}, which this "
            "instance does not hold."
        )

    def _content_of_benchmark(
        self,
        dataset: BenchmarkDataset,
    ) -> None:
        """Gather the content every case of one benchmark revision holds, with the case's label."""

        for case in dataset.cases:
            for ref in content_refs(case.input):
                _, labels = self.content.setdefault(ref.digest, (ref, []))
                labels.append(effective_sensitivity(case.sensitivity))


def closure(
    roots: Iterable[Lineage],
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
) -> Closure:
    """Return what a push of some documents sends: each one's history, and what it needs.

    Each content record is labelled as the most sensitive case that holds
    it.
    """

    gathering = _Gathering(workflows=workflows, tools=tools, benchmarks=benchmarks)

    for root in roots:
        gathering.gather(root)

    return Closure(
        revisions=tuple(gathering.revisions),
        content=tuple(
            ContentRecord(content=ref, sensitivity=most_sensitive(labels))
            for ref, labels in gathering.content.values()
        ),
        unresolved=tuple(gathering.unresolved),
    )


__all__ = [
    "CHILD_WORKFLOW_INPUTS",
    "RUNTIME",
    "Closure",
    "ancestry",
    "child_workflow_id",
    "closure",
    "content_refs",
]
