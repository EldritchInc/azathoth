"""The rotation of models that judge semantic cases, through the service API (ADR 0129).

Judges see benchmark data, so a judge must be a model the providers serve
now and the portfolio authorizes, as any model a workflow may select
(ADR 0074). Listing and removing read and write durable state only, so they
reach no provider, and work for a judge whose model is gone.
"""

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.catalog import Models
from azathoth.api.errors import ConflictError, ModelNotAuthorizedError, NotFoundError
from azathoth.api.models import JudgeSummary
from azathoth.evaluation import JudgeEntry
from azathoth.persistence.repositories import Repositories

LIST_COMMAND = "azathoth judge list"
"""The command that lists the rotation, which every judge names."""


class Judges:
    """The models an instance tries, in order, to judge semantic benchmark cases."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        models: Models,
    ) -> None:
        """Keep the rotation in `repositories`, asking `models` what the providers serve."""

        self._repositories = repositories
        self._models = models

    def list(
        self,
    ) -> tuple[JudgeSummary, ...]:
        """Return the rotation, in the order judges are tried.

        No provider is reached.

        It is the `read_portfolio` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
        """

        return _rotation(self._repositories())

    def add(
        self,
        identifier: str,
    ) -> JudgeSummary:
        """Append one model the providers serve and the portfolio authorizes to the rotation.

        It is the `manage_judges` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No configured provider serves it.
            ModelNotAuthorizedError: The portfolio does not authorize it.
            ConflictError: It is already in the rotation.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        model = self._models.get(identifier)
        repositories = self._repositories()

        if repositories.portfolio.get(identifier) is None:
            raise ModelNotAuthorizedError(f"Model {identifier!r} is not authorized.")

        try:
            repositories.judges.add(JudgeEntry(provider=model.provider, model=model.model))
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

        return _judge(repositories, identifier)

    def remove(
        self,
        identifier: str,
    ) -> JudgeSummary:
        """Remove one model from the rotation, and return it as it was there.

        No provider is reached.

        It is the `manage_judges` action (ADR 0134).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: It is not in the rotation.
        """

        repositories = self._repositories()
        removed = _judge(repositories, identifier)

        try:
            repositories.judges.remove(identifier)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc

        return removed


def _rotation(
    repositories: Repositories,
) -> tuple[JudgeSummary, ...]:
    """Return every judge, numbered in the order the rotation tries them."""

    authorized = {entry.identifier for entry in repositories.portfolio.entries()}

    return tuple(
        JudgeSummary(
            identifier=entry.identifier,
            provider=entry.provider,
            model=entry.model,
            position=position,
            authorized=entry.identifier in authorized,
            command=LIST_COMMAND,
        )
        for position, entry in enumerate(repositories.judges.rotation().entries, start=1)
    )


def _judge(
    repositories: Repositories,
    identifier: str,
) -> JudgeSummary:
    """Return one judge of the rotation.

    Raises:
        NotFoundError: It is not in the rotation.
    """

    judge = next(
        (judge for judge in _rotation(repositories) if judge.identifier == identifier),
        None,
    )

    if judge is None:
        raise NotFoundError(f"Judge {identifier!r} is not in the rotation.")

    return judge


__all__ = [
    "LIST_COMMAND",
    "Judges",
]
