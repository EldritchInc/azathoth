"""Ordered resolution of name-only workflow value references."""

from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import UUID

from azathoth.workflows.value import (
    WorkflowResultReference,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
)


class WorkflowOutputDeclaringStep(Protocol):
    """A workflow step, specified or executable, that declares outputs."""

    @property
    def id(self) -> UUID:
        """Return the step identifier."""

        ...

    @property
    def outputs(self) -> tuple[WorkflowValueBinding, ...]:
        """Return the values the step declares as outputs."""

        ...


def declaring_step_ids(
    name: str,
    steps: Iterable[WorkflowOutputDeclaringStep],
) -> tuple[UUID, ...]:
    """Return the identifiers of steps declaring an output name, in the given order.

    Callers pass steps in workflow step order, so the returned identifiers
    are the candidate producers of a name-only reference in the order they
    are preferred.
    """

    return tuple(step.id for step in steps if any(output.name == name for output in step.outputs))


def reference_producer_step_ids(
    reference: WorkflowResultReference,
    steps: Iterable[WorkflowOutputDeclaringStep],
) -> tuple[UUID, ...]:
    """Return the candidate producers of a value reference, in preference order.

    An explicit reference has exactly its named producer. A name-only
    reference has every given step that declares the name, in the given
    order.
    """

    if isinstance(
        reference,
        WorkflowValueReference,
    ):
        return (reference.producer_step_id,)

    return declaring_step_ids(
        reference.name,
        steps,
    )


def describe_value_reference(
    reference: WorkflowResultReference,
) -> str:
    """Return the operator-facing description of one value reference."""

    if isinstance(
        reference,
        WorkflowValueReference,
    ):
        return f"step {reference.producer_step_id} output {reference.name}"

    return f"output {reference.name} (first producer in step order)"


def resolve_named_value(
    name: str,
    *,
    producer_step_ids: Sequence[UUID],
    values: Iterable[WorkflowValue],
) -> WorkflowValue | None:
    """Return the value of the first candidate producer that produced it.

    The candidate producers are tried in the order given. A candidate that
    was skipped or failed produced no value and is passed over. Without any
    produced value, the reference does not resolve.
    """

    produced: dict[UUID, WorkflowValue] = {}

    for value in values:
        if value.name == name and value.producer_step_id not in produced:
            produced[value.producer_step_id] = value

    for producer_step_id in producer_step_ids:
        if producer_step_id in produced:
            return produced[producer_step_id]

    return None


__all__ = [
    "WorkflowOutputDeclaringStep",
    "declaring_step_ids",
    "describe_value_reference",
    "reference_producer_step_ids",
    "resolve_named_value",
]
