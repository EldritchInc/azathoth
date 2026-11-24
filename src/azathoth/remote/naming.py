"""The remotes an instance names, so a command can say `origin` for its URL (ADR 0126).

A name stands for a remote's URL and where its token comes from: the
environment variable it is read from, or the command that prints it (ADR
0141). The token itself is never kept, only where to find it, as ADR 0119
keeps an MCP server's credentials. Names belong to the instance that gives
them, as a git repository's remotes do, so two instances may give one
remote different names.
"""

import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from azathoth.persistence import Database, Row, SQLiteDatabase, Table, require_text
from azathoth.remote.client import REMOTE_TOKEN_VARIABLE, require_remote_url
from azathoth.remote.token_commands import TokenCommandError, require_token_command

REMOTE_NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
"""What a remote's name is made of: letters, digits, `_` and `-`.

No name holds `:`, `/` or `.`, so none is mistaken for a URL or a host.
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
A remote whose token a command prints keeps an empty `token_variable`.
"""

REMOTE_TOKEN_COMMAND_TABLES: Final = (
    Table(
        name="remote_token_commands",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                remote_token_commands (
                    name TEXT NOT NULL PRIMARY KEY,
                    command TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The table of the commands named remotes' tokens are printed by (ADR 0141).

Each row's `name` is a remote's in `remotes`, and its `command` the JSON
array of the command's arguments. Commands were first named in this
version, so there is nothing to backfill.
"""

BOTH_TOKEN_SOURCES_MESSAGE: Final = "Give a remote a token variable or a token command, not both."
"""Why naming a remote with both a token variable and a token command is refused."""


class RemoteNameError(ValueError):
    """A remote cannot be named, or a name removed, as asked."""


class RemoteAlreadyNamedError(RemoteNameError):
    """A remote already has the name another was to be given."""


class RemoteNotNamedError(RemoteNameError):
    """No remote has the name a removal gives."""


class NamedRemote(BaseModel):
    """One remote this instance names: its URL, and where its token comes from.

    Its token is read from `token_variable`, or printed by `token_command`,
    run as its arguments (ADR 0141); exactly one of them is given.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str

    url: str

    token_variable: str | None = REMOTE_TOKEN_VARIABLE

    token_command: tuple[str, ...] | None = None

    added_at: AwareDatetime

    @model_validator(mode="after")
    def _one_token_source(
        self,
    ) -> Self:
        """Refuse a remote whose token comes from both a variable and a command, or neither."""

        if (self.token_variable is None) == (self.token_command is None):
            raise ValueError(
                "A named remote's token comes from a token variable or a token command, "
                "exactly one."
            )

        return self


def require_remote_name(
    name: str,
) -> str:
    """Return a remote's name, or refuse one that is not made of the allowed characters.

    Raises:
        RemoteNameError: The name is empty, too long, or holds another character.
    """

    if REMOTE_NAME_PATTERN.fullmatch(name) is None:
        raise RemoteNameError(
            f"Remote name {name!r} is not one: use 1 to 64 letters, digits, '_' or '-'."
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
    token_variable: str | None,
    token_command: Sequence[str] | None,
    added_at: datetime,
) -> NamedRemote:
    """Return a named remote, refusing a name, URL, variable or command that is not one.

    With neither a variable nor a command, its token is read from
    `REMOTE_TOKEN_VARIABLE`.

    Raises:
        RemoteNameError: The name, URL, variable or command is not one, or
            both a variable and a command are given.
    """

    try:
        normalized = require_remote_url(url)
    except ValueError as exc:
        raise RemoteNameError(str(exc)) from None

    named = require_remote_name(name)

    if token_variable is not None and token_command is not None:
        raise RemoteNameError(BOTH_TOKEN_SOURCES_MESSAGE)

    if token_command is not None:
        try:
            command = require_token_command(token_command)
        except TokenCommandError as exc:
            raise RemoteNameError(str(exc)) from None

        return NamedRemote(
            name=named,
            url=normalized,
            token_variable=None,
            token_command=command,
            added_at=added_at,
        )

    return NamedRemote(
        name=named,
        url=normalized,
        token_variable=require_token_variable(
            REMOTE_TOKEN_VARIABLE if token_variable is None else token_variable
        ),
        added_at=added_at,
    )


def _already_named(
    held: NamedRemote,
) -> RemoteAlreadyNamedError:
    """Return the refusal to give a name a remote already has."""

    return RemoteAlreadyNamedError(
        f"Remote {held.name} is already named, for {held.url}; remove it first, or choose "
        "another name."
    )


def _not_named(
    name: str,
) -> RemoteNotNamedError:
    """Return the refusal to remove a name no remote has."""

    return RemoteNotNamedError(f"No remote is named {name!r}.")


class RemoteRepository(Protocol):
    """The remotes one instance names."""

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str | None = None,
        token_command: Sequence[str] | None = None,
    ) -> NamedRemote:
        """Name a remote, its token read from a variable or printed by a command, and return it.

        With neither, its token is read from `REMOTE_TOKEN_VARIABLE`.
        """

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
        database.prepare((*REMOTE_TABLES, *REMOTE_TOKEN_COMMAND_TABLES))

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str | None = None,
        token_command: Sequence[str] | None = None,
    ) -> NamedRemote:
        """Name a remote, and return it as named, its URL without a trailing `/`.

        Its token is read from `token_variable`, or printed by
        `token_command`; with neither, it is read from
        `REMOTE_TOKEN_VARIABLE`.

        Raises:
            RemoteNameError: The name, URL, variable or command is not one,
                or both a variable and a command are given.
            RemoteAlreadyNamedError: A remote already has the name.
        """

        remote = _named(name, url, token_variable, token_command, self._clock())

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                {_SELECTED}
                WHERE remotes.name = ?
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
                    remote.token_variable or "",
                    remote.added_at.isoformat(),
                ),
            )

            if remote.token_command is not None:
                session.execute(
                    """
                    INSERT INTO remote_token_commands (
                        name,
                        command
                    )
                    VALUES (?, ?)
                    """,
                    (remote.name, json.dumps(list(remote.token_command))),
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
                {_SELECTED}
                WHERE remotes.name = ?
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
                {_SELECTED}
                ORDER BY remotes.name
                """
            )

        return tuple(_remote(row) for row in rows)

    def remove(
        self,
        name: str,
    ) -> NamedRemote:
        """Forget a name, and return the remote it named.

        Raises:
            RemoteNotNamedError: No remote has the name.
        """

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                {_SELECTED}
                WHERE remotes.name = ?
                """,
                (name,),
            )

            if row is None:
                raise _not_named(name)

            session.execute(
                """
                DELETE FROM remote_token_commands
                WHERE name = ?
                """,
                (name,),
            )
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
        token_variable: str | None = None,
        token_command: Sequence[str] | None = None,
    ) -> NamedRemote:
        """Name a remote, and return it as named, its URL without a trailing `/`.

        Its token is read from `token_variable`, or printed by
        `token_command`; with neither, it is read from
        `REMOTE_TOKEN_VARIABLE`.

        Raises:
            RemoteNameError: The name, URL, variable or command is not one,
                or both a variable and a command are given.
            RemoteAlreadyNamedError: A remote already has the name.
        """

        remote = _named(name, url, token_variable, token_command, self._clock())
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
            RemoteNotNamedError: No remote has the name.
        """

        removed = self._remotes.pop(name, None)

        if removed is None:
            raise _not_named(name)

        return removed


_SELECTED: Final = """
    SELECT
        remotes.name,
        remotes.url,
        remotes.token_variable,
        remotes.added_at,
        remote_token_commands.command
    FROM remotes
    LEFT JOIN remote_token_commands
        ON remote_token_commands.name = remotes.name
"""
"""The query a named remote is read by, its columns in the order `_remote` reads them."""


def _command(
    held: object,
) -> tuple[str, ...]:
    """Return the token command a row holds as its JSON array of arguments."""

    arguments: object = json.loads(require_text(held, "A remote's token command was not text."))

    if not isinstance(arguments, list) or not all(isinstance(each, str) for each in arguments):
        raise ValueError("A remote's token command was not a list of arguments.")

    return tuple(str(each) for each in arguments)


def _remote(
    row: Row,
) -> NamedRemote:
    """Return the named remote one row holds."""

    command = None if row[4] is None else _command(row[4])

    return NamedRemote(
        name=require_text(row[0], "A remote's name was not text."),
        url=require_text(row[1], "A remote's URL was not text."),
        token_variable=(
            None
            if command is not None
            else require_text(row[2], "A remote's token variable was not text.")
        ),
        token_command=command,
        added_at=datetime.fromisoformat(
            require_text(row[3], "When a remote was named was not text.")
        ),
    )


__all__ = [
    "BOTH_TOKEN_SOURCES_MESSAGE",
    "REMOTE_NAME_PATTERN",
    "REMOTE_TABLES",
    "REMOTE_TOKEN_COMMAND_TABLES",
    "TOKEN_VARIABLE_PATTERN",
    "InMemoryRemoteRepository",
    "NamedRemote",
    "RemoteAlreadyNamedError",
    "RemoteNameError",
    "RemoteNotNamedError",
    "RemoteRepository",
    "SQLiteRemoteRepository",
    "SqlRemoteRepository",
    "require_remote_name",
    "require_token_variable",
]
