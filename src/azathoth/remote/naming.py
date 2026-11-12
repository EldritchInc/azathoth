"""The remotes an instance names, so a command can say `origin` for its URL (ADR 0126).

A name stands for a remote's URL and the environment variable its token is
read from; the token itself is never kept, only where to find it, as ADR
0119 keeps an MCP server's credentials. Names belong to the instance that
gives them, as a git repository's remotes do, so two instances may give one
remote different names.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict

from azathoth.persistence import Database, Row, SQLiteDatabase, Table, require_text
from azathoth.remote.client import REMOTE_TOKEN_VARIABLE, require_remote_url

REMOTE_NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
"""What a remote's name is made of: letters, digits, `.`, `_` and `-`.

No name holds `:` or `/`, so none is mistaken for a URL.
"""

TOKEN_VARIABLE_PATTERN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""What the name of the variable a remote's token is read from is made of."""

REMOTE_TABLES: Final = (
    Table(
        name="remotes",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                remotes (
                    name TEXT NOT NULL PRIMARY KEY,
                    url TEXT NOT NULL,
                    token_variable TEXT NOT NULL,
                    added_at TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The table the remotes an instance names are kept in (ADR 0126).

Remotes were first named in this version, so there is nothing to backfill.
"""


class RemoteNameError(ValueError):
    """A remote cannot be named, or a name removed, as asked."""


class NamedRemote(BaseModel):
    """One remote this instance names: its URL, and where its token is read from."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str

    url: str

    token_variable: str = REMOTE_TOKEN_VARIABLE

    added_at: AwareDatetime


def require_remote_name(
    name: str,
) -> str:
    """Return a remote's name, or refuse one that is not made of the allowed characters.

    Raises:
        RemoteNameError: The name is empty, too long, or holds another character.
    """

    if REMOTE_NAME_PATTERN.fullmatch(name) is None:
        raise RemoteNameError(
            f"Remote name {name!r} is not one: use 1 to 64 letters, digits, '.', '_' or '-'."
        )

    return name


def require_token_variable(
    variable: str,
) -> str:
    """Return the name of a token's variable, or refuse one that cannot name a variable.

    Raises:
        RemoteNameError: The name is not letters, digits and `_`, or begins
            with a digit.
    """

    if TOKEN_VARIABLE_PATTERN.fullmatch(variable) is None:
        raise RemoteNameError(
            f"Token variable {variable!r} is not an environment variable's name: use letters, "
            "digits and '_', not beginning with a digit."
        )

    return variable


def _named(
    name: str,
    url: str,
    token_variable: str,
    added_at: datetime,
) -> NamedRemote:
    """Return a named remote, refusing a name, URL or variable that is not one.

    Raises:
        RemoteNameError: The name, URL or variable is not one.
    """

    try:
        normalized = require_remote_url(url)
    except ValueError as exc:
        raise RemoteNameError(str(exc)) from None

    return NamedRemote(
        name=require_remote_name(name),
        url=normalized,
        token_variable=require_token_variable(token_variable),
        added_at=added_at,
    )


def _already_named(
    held: NamedRemote,
) -> RemoteNameError:
    """Return the refusal to give a name a remote already has."""

    return RemoteNameError(
        f"Remote {held.name} is already named, for {held.url}; remove it first, or choose "
        "another name."
    )


def _not_named(
    name: str,
) -> RemoteNameError:
    """Return the refusal to remove a name no remote has."""

    return RemoteNameError(f"No remote is named {name!r}.")


class RemoteRepository(Protocol):
    """The remotes one instance names."""

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str = REMOTE_TOKEN_VARIABLE,
    ) -> NamedRemote:
        """Name a remote, and return it as named."""

        ...

    def get(
        self,
        name: str,
    ) -> NamedRemote | None:
        """Return the remote of a name, or None when no remote has it."""

        ...

    def remotes(
        self,
    ) -> tuple[NamedRemote, ...]:
        """Return every remote named, ordered by name."""

        ...

    def remove(
        self,
        name: str,
    ) -> NamedRemote:
        """Forget a name, and return the remote it named."""

        ...


class SqlRemoteRepository:
    """The remotes one instance names, kept in a database."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._database = database
        self._clock = clock
        database.prepare(REMOTE_TABLES)

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str = REMOTE_TOKEN_VARIABLE,
    ) -> NamedRemote:
        """Name a remote, and return it as named, its URL without a trailing `/`.

        Raises:
            RemoteNameError: The name, URL or variable is not one, or a remote
                already has the name.
        """

        remote = _named(name, url, token_variable, self._clock())

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                SELECT {_COLUMNS}
                FROM remotes
                WHERE name = ?
                """,
                (remote.name,),
            )

            if row is not None:
                raise _already_named(_remote(row))

            session.execute(
                """
                INSERT INTO remotes (
                    name,
                    url,
                    token_variable,
                    added_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    remote.name,
                    remote.url,
                    remote.token_variable,
                    remote.added_at.isoformat(),
                ),
            )

        return remote

    def get(
        self,
        name: str,
    ) -> NamedRemote | None:
        """Return the remote of a name, or None when no remote has it."""

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                SELECT {_COLUMNS}
                FROM remotes
                WHERE name = ?
                """,
                (name,),
            )

        return None if row is None else _remote(row)

    def remotes(
        self,
    ) -> tuple[NamedRemote, ...]:
        """Return every remote named, ordered by name."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                f"""
                SELECT {_COLUMNS}
                FROM remotes
                ORDER BY name
                """
            )

        return tuple(_remote(row) for row in rows)

    def remove(
        self,
        name: str,
    ) -> NamedRemote:
        """Forget a name, and return the remote it named.

        Raises:
            RemoteNameError: No remote has the name.
        """

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                SELECT {_COLUMNS}
                FROM remotes
                WHERE name = ?
                """,
                (name,),
            )

            if row is None:
                raise _not_named(name)

            session.execute(
                """
                DELETE FROM remotes
                WHERE name = ?
                """,
                (name,),
            )

        return _remote(row)


class SQLiteRemoteRepository(SqlRemoteRepository):
    """The remotes one instance names, kept in SQLite."""

    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(SQLiteDatabase(database), clock=clock)


class InMemoryRemoteRepository:
    """The remotes one instance names, kept in memory, as tests keep them."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._remotes: dict[str, NamedRemote] = {}

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str = REMOTE_TOKEN_VARIABLE,
    ) -> NamedRemote:
        """Name a remote, and return it as named, its URL without a trailing `/`.

        Raises:
            RemoteNameError: The name, URL or variable is not one, or a remote
                already has the name.
        """

        remote = _named(name, url, token_variable, self._clock())
        held = self._remotes.get(remote.name)

        if held is not None:
            raise _already_named(held)

        self._remotes[remote.name] = remote

        return remote

    def get(
        self,
        name: str,
    ) -> NamedRemote | None:
        """Return the remote of a name, or None when no remote has it."""

        return self._remotes.get(name)

    def remotes(
        self,
    ) -> tuple[NamedRemote, ...]:
        """Return every remote named, ordered by name."""

        return tuple(self._remotes[name] for name in sorted(self._remotes))

    def remove(
        self,
        name: str,
    ) -> NamedRemote:
        """Forget a name, and return the remote it named.

        Raises:
            RemoteNameError: No remote has the name.
        """

        removed = self._remotes.pop(name, None)

        if removed is None:
            raise _not_named(name)

        return removed


_COLUMNS: Final = "name, url, token_variable, added_at"
"""The columns a named remote is read from, in the order `_remote` reads them."""


def _remote(
    row: Row,
) -> NamedRemote:
    """Return the named remote one row holds."""

    return NamedRemote(
        name=require_text(row[0], "A remote's name was not text."),
        url=require_text(row[1], "A remote's URL was not text."),
        token_variable=require_text(row[2], "A remote's token variable was not text."),
        added_at=datetime.fromisoformat(
            require_text(row[3], "When a remote was named was not text.")
        ),
    )


__all__ = [
    "REMOTE_NAME_PATTERN",
    "REMOTE_TABLES",
    "TOKEN_VARIABLE_PATTERN",
    "InMemoryRemoteRepository",
    "NamedRemote",
    "RemoteNameError",
    "RemoteRepository",
    "SQLiteRemoteRepository",
    "SqlRemoteRepository",
    "require_remote_name",
    "require_token_variable",
]
