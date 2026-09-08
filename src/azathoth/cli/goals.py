"""Durable goal inspection commands for the Azathoth CLI."""

import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.goals import (
    Goal,
    GoalDocumentError,
    SQLiteGoalRepository,
    decode_goal_document,
)


def list_goals() -> int:
    """List durable reusable goals."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteGoalRepository(
        configuration.database,
    )

    for goal in repository.goals():
        print(f"{goal.id}  {goal.name}")

    return 0


def show_goal(
    goal_id: UUID,
) -> int:
    """Show one durable reusable goal."""

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteGoalRepository(
        configuration.database,
    )

    goal = repository.get(
        goal_id,
    )

    if goal is None:
        print(
            f"Goal {goal_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    _print_goal(
        goal,
    )

    return 0


def _print_goal(
    goal: Goal,
) -> None:
    """Render one durable descriptive objective."""

    print(f"ID: {goal.id}")
    print(f"Name: {goal.name}")
    print(f"Description: {goal.description}")

    print("Success Criteria:")

    for criterion in goal.success_criteria:
        print(f"  - {criterion}")

    print("Constraints:")

    if not goal.constraints:
        print("  None")

        return

    for constraint in goal.constraints:
        print(f"  - {constraint}")


def import_goal(
    document_path: Path,
) -> int:
    """Import one durable reusable goal from a JSON document."""

    try:
        document = document_path.read_text(
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"Unable to read goal document {document_path}: {exc}",
            file=sys.stderr,
        )

        return 1

    try:
        goal = decode_goal_document(
            document,
        )
    except GoalDocumentError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    repository = SQLiteGoalRepository(
        configuration.database,
    )

    try:
        repository.save(
            goal,
        )
    except ValueError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(f"Imported goal {goal.id}.")

    return 0


__all__ = [
    "import_goal",
    "list_goals",
    "show_goal",
]
