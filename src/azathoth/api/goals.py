"""The reusable goals of an instance, through the service API (ADR 0133).

A goal says what a strategy is trying to accomplish. Goals are read and
imported only: none is revised, and importing never replaces one, as
`goal import` never has.
"""

import json
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.browsing import Document, RepositoriesAccess
from azathoth.api.errors import ConflictError, InvalidDocumentError, NotFoundError
from azathoth.api.models import GoalDetail, GoalImport, GoalSummary
from azathoth.goals import Goal, GoalDocumentError, decode_goal_document, encode_goal_document


def _summary(
    goal: Goal,
) -> GoalSummary:
    """Return the API's view of one goal."""

    return GoalSummary(
        id=goal.id,
        name=goal.name,
        description=goal.description,
        command=f"azathoth goal show {goal.id}",
    )


def _detail(
    goal: Goal,
) -> GoalDetail:
    """Return the API's view of one goal, whole."""

    document: dict[str, JsonValue] = json.loads(encode_goal_document(goal))

    return GoalDetail(
        **_summary(goal).model_dump(),
        success_criteria=goal.success_criteria,
        constraints=goal.constraints,
        document=document,
    )


class Goals:
    """The reusable goals of one instance."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Read and import the goals of the repositories `repositories` returns."""

        self._repositories = repositories

    def list(
        self,
    ) -> tuple[GoalSummary, ...]:
        """Return every goal, in the order they were imported.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        return tuple(_summary(goal) for goal in self._repositories().goals.goals())

    def get(
        self,
        goal_id: UUID,
    ) -> GoalDetail:
        """Return one goal with its success criteria and constraints.

        It is the `read_catalog` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No goal has this ID.
        """

        goal = self._repositories().goals.get(goal_id)

        if goal is None:
            raise NotFoundError(f"Goal {goal_id} is not configured.")

        return _detail(goal)

    def import_document(
        self,
        document: Document,
    ) -> GoalImport:
        """Import one goal document, as `goal import` does.

        The document is checked before the instance is touched. It is the
        `import_goal` action (ADR 0133).

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a goal document.
            ConflictError: A goal with its ID already exists.
        """

        text = document if isinstance(document, str) else json.dumps(dict(document))

        try:
            goal = decode_goal_document(text)
        except GoalDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        try:
            self._repositories().goals.save(goal)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

        return GoalImport(goal=_detail(goal))


__all__ = [
    "Goals",
]
