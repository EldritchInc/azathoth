"""How an instance's lineages relate to a remote's, and what a push warns of (ADR 0125).

A lineage's relation is read from two chains of revision digests: the
latest revision's ancestry here, and its ancestry at the remote, each
oldest first. A push warns, never refuses, of what would stop its documents
from running at the remote: credentials the remote does not set, a child
workflow the remote runs at another revision, and a model the remote has
not authorized.
"""

from collections.abc import Container, Iterator, Mapping, Sequence
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from azathoth.prompting import PROMPT_SPECIFICATIONS, FixedModelSelection
from azathoth.remote.closure import child_workflow_id
from azathoth.revisions import Lineage
from azathoth.tools import ToolDocument
from azathoth.workflows import WorkflowSpecification


class Relation(StrEnum):
    """How a lineage here relates to the same lineage at a remote."""

    IN_SYNC = "in_sync"
    AHEAD = "ahead"
    BEHIND = "behind"
    DIVERGED = "diverged"
    LOCAL_ONLY = "local_only"
    REMOTE_ONLY = "remote_only"


def relation(
    local: Sequence[str],
    remote: Sequence[str],
) -> Relation:
    """Return how a lineage relates, from each side's chain of revision digests.

    Ahead means the remote's latest revision is one this instance's latest
    was reached by, so a push moves the remote forward; behind is the
    reverse, so a pull moves this instance forward; diverged is neither.

    Raises:
        ValueError: Neither side holds a revision of the lineage.
    """

    if not local and not remote:
        raise ValueError("Neither side holds a revision of the lineage.")

    if not remote:
        return Relation.LOCAL_ONLY

    if not local:
        return Relation.REMOTE_ONLY

    if local[-1] == remote[-1]:
        return Relation.IN_SYNC

    if remote[-1] in local:
        return Relation.AHEAD

    if local[-1] in remote:
        return Relation.BEHIND

    return Relation.DIVERGED


class ComponentStatus(BaseModel):
    """One workflow, tool version or benchmark, as each side holds it.

    A side's digest and number are its latest revision's, or None where it
    holds none. A workflow's `remote_production_digest` is the revision in
    production at the remote, or None where it is not in production there.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineage: Lineage

    relation: Relation

    local_digest: str | None = None

    local_number: int | None = None

    remote_digest: str | None = None

    remote_number: int | None = None

    remote_production_digest: str | None = None


class ModelStatus(BaseModel):
    """Whether one model is authorized here, and at the remote.

    `authorized_remotely` is None when the remote's portfolio is not known.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identifier: str

    authorized_locally: bool

    authorized_remotely: bool | None = None


class RemoteStatus(BaseModel):
    """What this instance and a remote hold, and how each component relates.

    When the remote is not reached, its side of each component is unknown,
    each component is related as this instance alone holds it, and models
    are read from the last snapshot of its portfolio, taken at
    `portfolio_synced_at`.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    remote: str

    reachable: bool

    components: tuple[ComponentStatus, ...] = ()

    models: tuple[ModelStatus, ...] = ()

    portfolio_synced_at: AwareDatetime | None = None


def credential_names(
    document: ToolDocument,
) -> tuple[str, ...]:
    """Return the environment variables a tool document's implementations need, each once.

    They are each process implementation's environment grants, a grant
    ending in `*` covering every variable it begins, and each MCP
    implementation's `authorization` variable (ADR 0099, ADR 0119). Only
    names are read; no value ever is.
    """

    names: dict[str, None] = {}

    for implementation in document.implementations:
        names.update(dict.fromkeys(implementation.environment))

        if implementation.mcp is not None:
            authorization = implementation.mcp.credentials.authorization

            if authorization is not None:
                names[authorization] = None

    return tuple(names)


def missing_credential_warning(
    lineage: Lineage,
    name: str,
) -> str:
    """Return the warning that a pushed tool needs a variable the remote does not set."""

    return (
        f"Tool {lineage.id}@{lineage.version} needs {name}, which is not set at the remote; "
        "its steps fail there until it is."
    )


def child_drift_warnings(
    specification: WorkflowSpecification,
    *,
    local_latest: Mapping[UUID, str],
    remote_production: Mapping[UUID, str | None],
) -> tuple[str, ...]:
    """Return a warning for each child workflow the remote would run at another revision.

    A child is invoked, so it runs its production revision (ADR 0084): a parent tested
    here against the child's latest revision runs at the remote against
    whatever is in production there. A child not in production at the
    remote cannot run there at all. Children named only when their step
    runs cannot be checked.
    """

    workflow = specification.metadata.id
    warnings: list[str] = []

    for step in specification.steps:
        child = child_workflow_id(step)

        if not isinstance(child, UUID):
            continue

        here = local_latest.get(child)
        running = remote_production.get(child)

        if running is None:
            warnings.append(
                f"Step {step.id} of workflow {workflow} runs workflow {child}, which is not in "
                "production at the remote; it cannot run there until the child is promoted."
            )
        elif here is not None and running != here:
            warnings.append(
                f"Step {step.id} of workflow {workflow} runs workflow {child}, which is in "
                f"production at the remote as revision {running}, not {here}, the latest here."
            )

    return tuple(warnings)


def fixed_models(
    specification: WorkflowSpecification,
) -> Iterator[tuple[UUID, str]]:
    """Yield each prompt step's ID and the model it fixes, for steps that fix one."""

    for step in specification.steps:
        strategy = step.specification

        if isinstance(strategy, PROMPT_SPECIFICATIONS) and isinstance(
            strategy.model_selection, FixedModelSelection
        ):
            yield step.id, strategy.model_selection.identifier


def unapproved_model_warnings(
    specification: WorkflowSpecification,
    *,
    authorized: Container[str],
) -> tuple[str, ...]:
    """Return a warning for each model a step fixes that the remote has not authorized.

    A step that chooses its model by requirements is not checked: which
    model it runs on is decided by the remote's portfolio when it runs.
    """

    return tuple(
        f"Step {step_id} of workflow {specification.metadata.id} uses model {identifier}, "
        "which the remote has not authorized; it cannot run there until the remote's "
        "portfolio holds it."
        for step_id, identifier in fixed_models(specification)
        if identifier not in authorized
    )


__all__ = [
    "ComponentStatus",
    "ModelStatus",
    "Relation",
    "RemoteStatus",
    "child_drift_warnings",
    "credential_names",
    "fixed_models",
    "missing_credential_warning",
    "relation",
    "unapproved_model_warnings",
]
