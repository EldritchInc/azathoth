"""Provider models and the local portfolio (ADR 0120).

Listing models asks every configured provider what it serves now, records
what changed, and returns the result. The portfolio, the models this
instance authorizes for selection, is read from the database alone.
"""

import asyncio
import shlex
from collections.abc import Callable, Mapping
from enum import StrEnum

from pydantic import JsonValue, ValidationError

from azathoth.api.authorship import AuthorAccess, author_view
from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.errors import (
    ConflictError,
    InvalidArgumentError,
    ModelInUseError,
    NotFoundError,
    ProviderUnavailableError,
)
from azathoth.api.models import (
    ModelSummary,
    PortfolioEntry,
    PortfolioRemoval,
    ProductionDependent,
    ProductionStepUsage,
)
from azathoth.persistence.repositories import Repositories
from azathoth.providers import (
    ModelCatalog,
    ModelDiscoveryError,
    ModelMetadata,
    ModelPortfolioEntry,
    ModelPortfolioLoader,
    ModelQuery,
    ModelRequirements,
    PolicyDeclaration,
    PortfolioProvenance,
    ProviderModelCatalogSynchronizer,
    ProviderModelDirectory,
    ProviderModelObserver,
    model_catalog_for_portfolio,
)
from azathoth.sensitivity import UNKNOWN_DATA_POLICY, DataPolicy, Sensitivity, may_receive
from azathoth.workflows import WorkflowProductionModelUsageRole, model_usage_report

DirectoriesAccess = Callable[[], tuple[ProviderModelDirectory, ...]]
"""Return the directories of an instance's providers, made the first time they are needed."""


def discover(
    repositories: Repositories,
    directories: tuple[ProviderModelDirectory, ...],
) -> ModelCatalog:
    """Ask every provider what it serves now, record what changed, and return the catalog.

    Raises:
        ProviderUnavailableError: A provider could not be asked.
    """

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=tuple(
            ProviderModelObserver(
                directory=directory,
                repository=repositories.provider_observations,
            )
            for directory in directories
        )
    )

    try:
        return asyncio.run(synchronizer.synchronize())
    except ModelDiscoveryError as exc:
        raise ProviderUnavailableError(str(exc)) from exc


def _show_command(
    identifier: str,
) -> str:
    """Return the command that shows one model."""

    return f"azathoth model show {shlex.quote(identifier)}"


def _summary(
    model: ModelMetadata,
    *,
    authorized: bool,
) -> ModelSummary:
    """Return the API's view of one model a provider serves."""

    pricing = model.pricing

    return ModelSummary(
        identifier=model.identifier,
        provider=model.provider,
        model=model.model,
        display_name=model.display_name,
        input_modalities=tuple(sorted(value.value for value in model.input_modalities)),
        output_modalities=tuple(sorted(value.value for value in model.output_modalities)),
        capabilities=tuple(sorted(value.value for value in model.capabilities)),
        context_window_tokens=model.context_window_tokens,
        maximum_output_tokens=model.maximum_output_tokens,
        input_usd_per_million_tokens=(
            pricing.input_usd_per_million_tokens if pricing is not None else None
        ),
        output_usd_per_million_tokens=(
            pricing.output_usd_per_million_tokens if pricing is not None else None
        ),
        authorized=authorized,
        command=_show_command(model.identifier),
    )


def _entry(
    entry: ModelPortfolioEntry,
    provenance: PortfolioProvenance | None,
    declaration: PolicyDeclaration | None,
) -> PortfolioEntry:
    """Return the API's view of one portfolio entry, who added it and who declared its policy.

    See ADR 0122 and ADR 0123.

    Raises:
        LookupError: The entry's provenance is not recorded.
    """

    if provenance is None:
        raise LookupError(f"Model portfolio entry {entry.identifier!r} has no provenance.")

    return PortfolioEntry(
        identifier=entry.identifier,
        provider=entry.provider,
        model=entry.model,
        content_digest=provenance.content_digest,
        author=author_view(provenance.author),
        added_at=provenance.added_at,
        data_policy=entry.data_policy,
        receives_restricted=entry.data_policy.private,
        policy_declared_by=None if declaration is None else author_view(declaration.author),
        policy_declared_at=None if declaration is None else declaration.declared_at,
        command=_show_command(entry.identifier),
    )


def _receives(
    entry: ModelPortfolioEntry | None,
    sensitivity: Sensitivity | None,
) -> bool:
    """Return whether a portfolio entry's model may receive input with a label (ADR 0123)."""

    return may_receive(None if entry is None else entry.data_policy, sensitivity)


def _requirements(
    requirements: Mapping[str, JsonValue],
) -> ModelRequirements:
    """Return a step's model requirements as Azathoth reads them.

    Raises:
        InvalidArgumentError: A requirement is unknown, or not valid.
    """

    unknown = next(
        (name for name in requirements if name not in ModelRequirements.model_fields), None
    )

    if unknown is not None:
        raise InvalidArgumentError(f"Unknown model requirement {unknown!r}.")

    try:
        return ModelRequirements.model_validate(dict(requirements))
    except ValidationError as exc:
        error = exc.errors()[0]
        name = error["loc"][0] if error["loc"] else "requirements"

        raise InvalidArgumentError(
            f"Model requirement {name!r} is not valid: {error['msg']}."
        ) from exc


def _unavailable(
    identifier: str,
) -> NotFoundError:
    """Return the error for a model no configured provider serves."""

    return NotFoundError(f"Model {identifier!r} is not currently available.")


class MatchScope(StrEnum):
    """Which models `models.matching` matches: the portfolio's, or every one served (ADR 0124)."""

    PORTFOLIO = "portfolio"
    CATALOG = "catalog"


def _scope(
    scope: MatchScope | str,
) -> MatchScope:
    """Return a match scope, or refuse one that is not.

    Raises:
        InvalidArgumentError: The scope is neither the portfolio nor the catalog.
    """

    try:
        return MatchScope(scope)
    except ValueError:
        raise InvalidArgumentError(
            f"Match scope {str(scope)!r} is not 'portfolio' or 'catalog'."
        ) from None


class Models:
    """The models an instance's providers serve now."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        directories: DirectoriesAccess,
    ) -> None:
        """Browse the models the providers `directories` returns serve."""

        self._repositories = repositories
        self._directories = directories

    def list(
        self,
    ) -> tuple[ModelSummary, ...]:
        """Return every model the configured providers serve now, provider by provider.

        Raises:
            InstanceClosedError: The instance was closed.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        repositories = self._repositories()
        catalog = discover(repositories, self._directories())
        authorized = {entry.identifier for entry in repositories.portfolio.entries()}

        return tuple(
            _summary(model, authorized=model.identifier in authorized) for model in catalog.models
        )

    def get(
        self,
        identifier: str,
    ) -> ModelSummary:
        """Return one model a configured provider serves now.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No configured provider serves it.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        model = next((model for model in self.list() if model.identifier == identifier), None)

        if model is None:
            raise _unavailable(identifier)

        return model

    def matching(
        self,
        requirements: Mapping[str, JsonValue],
        *,
        sensitivity: Sensitivity | None = None,
        scope: MatchScope | str = MatchScope.PORTFOLIO,
    ) -> tuple[ModelSummary, ...]:
        """Return the models that meet a step's model requirements (ADR 0121).

        By default, only the portfolio's models match, in the order a run
        tries them; a served model outside the portfolio never matches. With
        `scope="catalog"`, every model the configured providers serve
        matches, provider by provider, each marked `authorized` or not: the
        models a pulled workflow's steps could run on once authorized here
        (ADR 0124).

        With `sensitivity`, only the models that may receive input so
        labelled match: for restricted input, those declared to neither
        retain nor train on data (ADR 0123). A model outside the portfolio
        has no declared policy, so it never matches restricted input.

        The requirements are a step's `requirements`, as its document holds
        them; one left out is its default, so a step reads and writes text
        unless it says otherwise. A model matches as a run matches it, by
        `ModelQuery.matches`.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: A requirement is unknown, or not valid, or
                the scope is neither `portfolio` nor `catalog`.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        parsed = _requirements(requirements)
        chosen = _scope(scope)
        repositories = self._repositories()
        portfolio = ModelPortfolioLoader(repositories.portfolio).load_portfolio()
        served = discover(repositories, self._directories())
        catalog = (
            served
            if chosen is MatchScope.CATALOG
            else model_catalog_for_portfolio(catalog=served, portfolio=portfolio)
        )

        return tuple(
            _summary(model, authorized=portfolio.get(model.identifier) is not None)
            for model in catalog.find(ModelQuery.from_requirements(parsed))
            if _receives(portfolio.get(model.identifier), sensitivity)
        )


class Portfolio:
    """The models this instance authorizes for selection."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        directories: DirectoriesAccess,
        author: AuthorAccess,
    ) -> None:
        """Keep the portfolio of the repositories `repositories` returns.

        Additions are recorded as the author `author` returns (ADR 0122).
        """

        self._repositories = repositories
        self._directories = directories
        self._author = author

    def list(
        self,
    ) -> tuple[PortfolioEntry, ...]:
        """Return every authorized model, in the order it was authorized.

        No provider is asked.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        portfolio = self._repositories().portfolio

        return tuple(
            _entry(
                entry,
                portfolio.provenance(entry.identifier),
                portfolio.policy_declaration(entry.identifier),
            )
            for entry in portfolio.entries()
        )

    def add(
        self,
        identifier: str,
        *,
        data_policy: DataPolicy = UNKNOWN_DATA_POLICY,
    ) -> PortfolioEntry:
        """Authorize one model a configured provider serves now.

        `data_policy` declares what its provider does with data it is sent,
        as `azathoth model authorize --no-retention --no-training` does;
        unknown unless declared (ADR 0123).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No configured provider serves it.
            ConflictError: It is already authorized.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
            InvalidAuthorError: Who is adding it could not be told.
        """

        repositories = self._repositories()
        model = discover(repositories, self._directories()).get(identifier)

        if model is None:
            raise _unavailable(identifier)

        if repositories.portfolio.get(identifier) is not None:
            raise ConflictError(f"Model {identifier!r} is already authorized.")

        entry = ModelPortfolioEntry(
            provider=model.provider,
            model=model.model,
            data_policy=data_policy,
        )

        repositories.portfolio.save(entry, author=self._author())

        return _entry(
            entry,
            repositories.portfolio.provenance(entry.identifier),
            repositories.portfolio.policy_declaration(entry.identifier),
        )

    def set_data_policy(
        self,
        identifier: str,
        data_policy: DataPolicy,
    ) -> PortfolioEntry:
        """Declare what one authorized model's provider does with data (ADR 0123).

        The policy replaces the one declared, as `azathoth model policy`
        does. Only a model declared to neither retain nor train on data may
        be sent restricted input. The entry keeps its place and provenance,
        and no provider is asked. Who declares it, as the author the
        instance records, and when, are recorded.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: It is not authorized.
            InvalidAuthorError: Who is declaring it could not be told.
        """

        portfolio = self._repositories().portfolio

        if portfolio.get(identifier) is None:
            raise NotFoundError(f"Model {identifier!r} is not authorized.")

        entry = portfolio.set_data_policy(identifier, data_policy, author=self._author())

        return _entry(
            entry, portfolio.provenance(identifier), portfolio.policy_declaration(identifier)
        )

    def remove(
        self,
        identifier: str,
        *,
        force: bool = False,
    ) -> PortfolioRemoval:
        """Remove one model from the portfolio, as `azathoth model deauthorize` does.

        A model active production uses is kept unless `force` is set; forced,
        it is removed and the workflows that use it are returned. A semantic
        judge is always kept: it must leave the judge rotation first. No
        provider is asked.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: It is not authorized.
            ConflictError: It is a semantic judge.
            ModelInUseError: Active production uses it, and `force` is not set.
        """

        repositories = self._repositories()

        if repositories.portfolio.get(identifier) is None:
            raise NotFoundError(f"Model {identifier!r} is not authorized.")

        if repositories.judges.get(identifier) is not None:
            raise ConflictError(
                f"Model {identifier!r} is a semantic judge and was not deauthorized; "
                f"remove it from the rotation first with: "
                f"azathoth judge remove {shlex.quote(identifier)}"
            )

        report = model_usage_report(
            identifier,
            specifications=(),
            production_states=repositories.production_states.states(),
            runs=(),
        )

        dependents = tuple(
            ProductionDependent(
                workflow_id=entry.workflow.id,
                workflow_name=entry.workflow.name,
                steps=tuple(
                    ProductionStepUsage(
                        step_id=usage.step_id,
                        role=(
                            "primary"
                            if usage.role is WorkflowProductionModelUsageRole.PRIMARY
                            else "substitute"
                        ),
                    )
                    for usage in entry.production
                ),
            )
            for entry in report.production_workflows
        )

        if dependents and not force:
            raise ModelInUseError(
                f"Model {identifier!r} is used by active production and was not deauthorized.",
                dependents=dependents,
            )

        repositories.portfolio.delete(identifier)

        command = f"azathoth model deauthorize {shlex.quote(identifier)}"

        return PortfolioRemoval(
            identifier=identifier,
            dependents=dependents,
            command=f"{command} --force" if dependents else command,
        )


__all__ = [
    "DirectoriesAccess",
    "MatchScope",
    "Models",
    "Portfolio",
    "discover",
]
