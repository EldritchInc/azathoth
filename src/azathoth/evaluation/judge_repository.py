"""Persistence contracts for the semantic judge rotation."""

from typing import Protocol

from azathoth.evaluation.judges import (
    JudgeEntry,
    JudgeRotation,
)


class JudgeRotationRepository(Protocol):
    """Persist and retrieve the ordered semantic judge rotation."""

    def add(
        self,
        entry: JudgeEntry,
    ) -> None:
        """Append one judge to the end of the rotation.

        Raises:
            ValueError: The judge is already in the rotation.
        """

        ...

    def get(
        self,
        identifier: str,
    ) -> JudgeEntry | None:
        """Return one judge by provider-qualified identifier."""

        ...

    def remove(
        self,
        identifier: str,
    ) -> None:
        """Remove one judge from the rotation.

        Raises:
            ValueError: The judge is not in the rotation.
        """

        ...

    def rotation(
        self,
    ) -> JudgeRotation:
        """Return every judge in the order they were added."""

        ...
