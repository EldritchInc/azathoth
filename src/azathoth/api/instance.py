"""Opening an Azathoth instance through the service API (ADR 0120)."""

from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

import azathoth
from azathoth.api.authorship import author_access
from azathoth.api.browsing import Benchmarks, Tools, Workflows
from azathoth.api.catalog import Models, Portfolio
from azathoth.api.errors import (
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
)
from azathoth.api.invocations import Invocations
from azathoth.api.models import API_STABILITY, InstanceDescription
from azathoth.api.providers import ProviderSettings, language_models, model_directories
from azathoth.api.running import Runs
from azathoth.inputs import S3ContentLocation, S3ContentStore
from azathoth.persistence import (
    SCHEMA_VERSION,
    DatabaseLocation,
    DatabaseSchemaError,
    DatabaseUnavailableError,
    PostgresLocation,
    SQLiteLocation,
    parse_database_location,
)
from azathoth.persistence.repositories import (
    SCHEMA_TABLES,
    Repositories,
    open_repositories,
)
from azathoth.providers import LanguageModelRegistry, ModelCatalog, ProviderModelDirectory
from azathoth.telemetry import NO_TELEMETRY, Telemetry


class Azathoth:
    """One open Azathoth instance: the database every call reads and writes.

    Open one with `azathoth.api.open`, and close it when done, best as a
    context manager. Calls run synchronously on the caller's thread. Once
    closed, every call raises `InstanceClosedError`.

    Operations are grouped by what they act on: `workflows`, `tools`,
    `benchmarks`, `models`, `portfolio`, `runs` and `invocations`.
    """

    def __init__(
        self,
        repositories: Repositories,
        *,
        providers: ProviderSettings | None = None,
        telemetry: Telemetry = NO_TELEMETRY,
        directories: Sequence[ProviderModelDirectory] | None = None,
        language_models: LanguageModelRegistry | None = None,
        author: str | None = None,
    ) -> None:
        """Serve the API over one database's repositories; `open` is the way to make one.

        The providers `providers` turns on are reached through directories
        made the first time models are needed. `directories`, when given,
        are used instead, as tests do, with `language_models` as the models
        runs execute. Runs and invocations are traced by `telemetry`.
        Imports and portfolio additions are recorded as `author`'s, or, without
        it, as `AZATHOTH_AUTHOR`'s or the operating system user's (ADR 0122).

        Raises:
            InvalidAuthorError: `author` is not `Name <email>` or `Name`.
        """

        self._author = author_access(author)

        self._repositories = repositories
        self._providers = providers if providers is not None else ProviderSettings()
        self._directories = tuple(directories) if directories is not None else None
        self._given_language_models = language_models
        self._closed = False
        self._workflows = Workflows(self._open_repositories, self._author)
        self._tools = Tools(self._open_repositories, self._author)
        self._benchmarks = Benchmarks(self._open_repositories, self._author)
        self._models = Models(self._open_repositories, self._model_directories)
        self._portfolio = Portfolio(
            self._open_repositories,
            self._model_directories,
            self._author,
        )
        self._injected = directories is not None
        self._runs = Runs(
            self._open_repositories,
            self._model_directories,
            self._language_models,
            telemetry,
        )
        self._invocations = Invocations(self._open_repositories)

    def __enter__(
        self,
    ) -> "Azathoth":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def closed(
        self,
    ) -> bool:
        """Return whether the instance was closed."""

        return self._closed

    @property
    def workflows(
        self,
    ) -> Workflows:
        """Return the workflows this instance holds."""

        return self._workflows

    @property
    def tools(
        self,
    ) -> Tools:
        """Return the tools this instance holds."""

        return self._tools

    @property
    def benchmarks(
        self,
    ) -> Benchmarks:
        """Return the benchmark datasets this instance holds."""

        return self._benchmarks

    @property
    def models(
        self,
    ) -> Models:
        """Return the models this instance's providers serve now."""

        return self._models

    @property
    def portfolio(
        self,
    ) -> Portfolio:
        """Return the models this instance authorizes for selection."""

        return self._portfolio

    @property
    def runs(
        self,
    ) -> Runs:
        """Return runs of this instance's configured workflows."""

        return self._runs

    @property
    def invocations(
        self,
    ) -> Invocations:
        """Return the invocations of this instance's promoted workflows."""

        return self._invocations

    def describe(
        self,
    ) -> InstanceDescription:
        """Return what this instance is: its database, and the Azathoth serving it.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        location = self._open_repositories().location

        return InstanceDescription(
            database=location.display(),
            backend="postgres" if isinstance(location, PostgresLocation) else "sqlite",
            azathoth_version=azathoth.__version__,
            schema_version=SCHEMA_VERSION,
            api_stability=API_STABILITY,
        )

    def close(
        self,
    ) -> None:
        """Release the database's connection, if it holds one; closing again does nothing."""

        if self._closed:
            return

        self._closed = True
        self._repositories.database.close()

    def _open_repositories(
        self,
    ) -> Repositories:
        """Return the repositories, unless the instance was closed.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        if self._closed:
            raise InstanceClosedError()

        return self._repositories

    def _model_directories(
        self,
    ) -> tuple[ProviderModelDirectory, ...]:
        """Return the directories of the configured providers, made the first time.

        Raises:
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
        """

        if self._directories is None:
            self._directories = model_directories(self._providers)

        return self._directories

    def _language_models(
        self,
        models: ModelCatalog,
    ) -> LanguageModelRegistry:
        """Return the executable models of the configured providers, for the models discovered.

        Raises:
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
        """

        if self._injected:
            return (
                self._given_language_models
                if self._given_language_models is not None
                else LanguageModelRegistry()
            )

        return language_models(self._providers, models)


def open(
    database: DatabaseLocation | str | Path,
    *,
    providers: ProviderSettings | None = None,
    telemetry: Telemetry = NO_TELEMETRY,
    content: S3ContentLocation | None = None,
    author: str | None = None,
) -> Azathoth:
    """Open the Azathoth instance one database holds.

    The database is named as `AZATHOTH_DATABASE` names it: an SQLite file's
    path, or a `postgresql://` URL. Opening never creates or changes a
    database; `azathoth init` does.

    `providers` names the model providers the instance may ask what they
    serve; without it, it asks none. `ProviderSettings.from_environment()`
    reads them as the command line does. No provider is reached, and boto3
    is not imported, until a call needs a provider's models.

    `telemetry` traces runs and invocations, as `AZATHOTH_TRACING` does for
    the command line. `content` names the S3 location that keeps resolved
    content (ADR 0108), as `AZATHOTH_CONTENT_STORE` does; without it,
    content is kept in the database. `author`, as `Name <email>` or `Name`,
    is who imports and portfolio additions are recorded as; without it they
    are `AZATHOTH_AUTHOR`'s, or the operating system user's (ADR 0122).

    Raises:
        InvalidAuthorError: `author` is not `Name <email>` or `Name`.
        InstanceNotFoundError: The SQLite file does not exist.
        InstanceUnavailableError: It is a PostgreSQL database, and the
            `postgres` extra is not installed.
        InstanceSchemaError: The PostgreSQL database does not hold this
            Azathoth's schema.
    """

    author_access(author)

    location = (
        database
        if isinstance(database, SQLiteLocation | PostgresLocation)
        else parse_database_location(database)
    )

    if isinstance(location, SQLiteLocation) and not location.path.is_file():
        raise InstanceNotFoundError(
            f"Database {location.display()} does not exist; run azathoth init."
        )

    try:
        repositories = open_repositories(
            location,
            content=(lambda: S3ContentStore(content)) if content is not None else None,
        )
    except DatabaseUnavailableError as exc:
        raise InstanceUnavailableError(str(exc)) from exc

    if isinstance(location, PostgresLocation):
        try:
            repositories.database.prepare(SCHEMA_TABLES)
        except DatabaseSchemaError as exc:
            raise InstanceSchemaError(str(exc)) from exc

    return Azathoth(repositories, providers=providers, telemetry=telemetry, author=author)


__all__ = [
    "Azathoth",
    "open",
]
