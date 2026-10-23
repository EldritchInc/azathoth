"""Deterministic in-memory persistence for the semantic judge rotation."""

from azathoth.evaluation.judge_repository import JudgeRotationRepository
from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
)


class InMemoryJudgeRotationRepository:
    """Store the semantic judge rotation in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._entries: dict[
            str,
            JudgeEntry,
        ] = {}

    def add(
        self,
        entry: JudgeEntry,
    ) -> None:
        """Append one judge to the end of the rotation.

        Raises:
            ValueError: The judge is already in the rotation.
        """

        if entry.identifier in self._entries:
            raise ValueError(f"Judge {entry.identifier!r} is already in the rotation.")

        self._entries[entry.identifier] = entry

    def get(
        self,
        identifier: str,
    ) -> JudgeEntry | None:
        """Return one judge by provider-qualified identifier."""

        return self._entries.get(identifier)

    def remove(
        self,
        identifier: str,
    ) -> None:
        """Remove one judge from the rotation.

        Raises:
            ValueError: The judge is not in the rotation.
        """

        if identifier not in self._entries:
            raise ValueError(f"Judge {identifier!r} is not in the rotation.")

        del self._entries[identifier]

    def rotation(
        self,
    ) -> JudgeRotation:
        """Return every judge in the order they were added."""

        return JudgeRotation(
            entries=tuple(self._entries.values()),
        )


def require_judge_rotation_repository(
    repository: JudgeRotationRepository,
) -> JudgeRotationRepository:
    """Return a repository after static protocol validation."""

    return repository
