"""The bearer tokens a remote's owner issues, kept as digests (ADR 0124).

A token is shown once, when it is created; the remote keeps only its sha256
digest, so a database that leaks holds no token that works. A revoked token
stays in the table, so whoever reads it can still tell which name it had,
and when it stopped working. With the core's policy every token is the
owner's: whoever holds one may do anything the owner may.
"""

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from azathoth.persistence import Database, Row, Session, SQLiteDatabase, Table, require_text
from azathoth.remote.seams import Principal
from azathoth.revisions import Author

TOKEN_PREFIX: Final = "azr_"
"""What every remote token begins with, so a leaked one is easy to recognize."""

TOKEN_NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
"""What a token's name is made of: letters, digits, `.`, `_` and `-`."""

BEARER_SCHEME: Final = "bearer"
"""The `Authorization` scheme a token is sent with, compared without case."""

REMOTE_TOKEN_TABLES: Final = (
    Table(
        name="remote_tokens",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                remote_tokens (
                    sequence {sequence},
                    id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    digest TEXT NOT NULL UNIQUE,
                    author_name TEXT,
                    author_email TEXT,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                remote_tokens_name
            ON remote_tokens (
                name
            )
            """,
        ),
    ),
)
"""The table a remote keeps its tokens' digests in (ADR 0124).

Tokens were first issued in this version, so there is nothing to backfill.
"""


class RemoteTokenError(ValueError):
    """A token cannot be created or revoked as asked."""


class RemoteToken(BaseModel):
    """One token a remote issued: its name, who created it and when, and when it was revoked."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    id: UUID

    name: str = Field(
        pattern=TOKEN_NAME_PATTERN.pattern,
    )

    author: Author | None = None

    created_at: AwareDatetime

    revoked_at: AwareDatetime | None = None

    @property
    def active(
        self,
    ) -> bool:
        """Return whether the token still authenticates."""

        return self.revoked_at is None


class IssuedToken(BaseModel):
    """A token just created, and its secret, which is never kept or shown again."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    token: RemoteToken

    secret: str = Field(
        min_length=len(TOKEN_PREFIX) + 1,
    )


def token_digest(
    secret: str,
) -> str:
    """Return the sha256 hex digest a remote keeps of one token."""

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_token_secret() -> str:
    """Return a new token: the prefix, then 256 random bits, URL-safe."""

    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def require_token_name(
    name: str,
) -> str:
    """Return a token name, or refuse one that is not made of the allowed characters.

    Raises:
        RemoteTokenError: The name is empty, too long, or holds another character.
    """

    if TOKEN_NAME_PATTERN.fullmatch(name) is None:
        raise RemoteTokenError(
            f"Remote token name {name!r} is not one: use 1 to 64 letters, digits, '.', '_' or '-'."
        )

    return name


class RemoteTokenRepository(Protocol):
    """The tokens one remote issued."""

    def create(
        self,
        name: str,
        *,
        author: Author | None = None,
    ) -> IssuedToken:
        """Issue a token under a name no active token has, and return it with its secret."""

        ...

    def tokens(
        self,
        *,
        include_revoked: bool = False,
    ) -> tuple[RemoteToken, ...]:
        """Return the active tokens, or every token, oldest first."""

        ...

    def revoke(
        self,
        name: str,
    ) -> RemoteToken:
        """Revoke the active token of a name, and return it revoked."""

        ...

    def find(
        self,
        secret: str,
    ) -> RemoteToken | None:
        """Return the active token a secret is, or None."""

        ...


class SqlRemoteTokenRepository:
    """The tokens one remote issued, kept as digests in a database."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_secret: Callable[[], str] = new_token_secret,
    ) -> None:
        self._database = database
        self._clock = clock
        self._new_secret = new_secret
        database.prepare(REMOTE_TOKEN_TABLES)

    def create(
        self,
        name: str,
        *,
        author: Author | None = None,
    ) -> IssuedToken:
        """Issue a token under a name no active token has, and return it with its secret.

        Raises:
            RemoteTokenError: The name is not one, or an active token has it.
        """

        token = RemoteToken(
            id=uuid4(),
            name=require_token_name(name),
            author=author,
            created_at=self._clock(),
        )
        secret = self._new_secret()

        with self._database.transaction() as session:
            if _active_row(session, name) is not None:
                raise RemoteTokenError(
                    f"A remote token named {name!r} already exists; revoke it first, or choose "
                    "another name."
                )

            session.execute(
                """
                INSERT INTO remote_tokens (
                    id,
                    name,
                    digest,
                    author_name,
                    author_email,
                    created_at,
                    revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    str(token.id),
                    token.name,
                    token_digest(secret),
                    None if author is None else author.name,
                    None if author is None else author.email,
                    token.created_at.isoformat(),
                ),
            )

        return IssuedToken(token=token, secret=secret)

    def tokens(
        self,
        *,
        include_revoked: bool = False,
    ) -> tuple[RemoteToken, ...]:
        """Return the active tokens, or every token, oldest first."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                f"""
                SELECT {_COLUMNS}
                FROM remote_tokens
                ORDER BY sequence
                """
            )

        held = tuple(_token(row) for row in rows)

        return held if include_revoked else tuple(token for token in held if token.active)

    def revoke(
        self,
        name: str,
    ) -> RemoteToken:
        """Revoke the active token of a name, and return it revoked.

        Raises:
            RemoteTokenError: No active token has the name.
        """

        revoked_at = self._clock()

        with self._database.transaction() as session:
            row = _active_row(session, name)

            if row is None:
                raise RemoteTokenError(f"No remote token is named {name!r}.")

            token = _token(row).model_copy(update={"revoked_at": revoked_at})

            session.execute(
                """
                UPDATE remote_tokens
                SET revoked_at = ?
                WHERE id = ?
                """,
                (revoked_at.isoformat(), str(token.id)),
            )

        return token

    def find(
        self,
        secret: str,
    ) -> RemoteToken | None:
        """Return the active token a secret is, or None, looking it up by its digest."""

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                SELECT {_COLUMNS}
                FROM remote_tokens
                WHERE digest = ? AND revoked_at IS NULL
                """,
                (token_digest(secret),),
            )

        return None if row is None else _token(row)


class SQLiteRemoteTokenRepository(SqlRemoteTokenRepository):
    """The tokens one remote issued, kept as digests in SQLite."""

    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_secret: Callable[[], str] = new_token_secret,
    ) -> None:
        super().__init__(SQLiteDatabase(database), clock=clock, new_secret=new_secret)


class TokenAuthenticator:
    """The core's authenticator: an active token the remote issued is its owner."""

    def __init__(
        self,
        tokens: RemoteTokenRepository,
    ) -> None:
        self._tokens = tokens

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        """Return the owner, named as their token, for a `Bearer` header of an active token."""

        if authorization is None:
            return None

        scheme, _, secret = authorization.strip().partition(" ")
        secret = secret.strip()

        if scheme.lower() != BEARER_SCHEME or not secret.startswith(TOKEN_PREFIX):
            return None

        token = self._tokens.find(secret)

        return None if token is None else Principal(name=token.name, owner=True)


_COLUMNS: Final = "id, name, author_name, author_email, created_at, revoked_at"
"""The columns a token is read from, in the order `_token` reads them."""


def _active_row(
    session: Session,
    name: str,
) -> Row | None:
    """Return the row of the active token of a name, or None."""

    rows = session.fetchall(
        f"""
        SELECT {_COLUMNS}
        FROM remote_tokens
        WHERE name = ? AND revoked_at IS NULL
        """,
        (name,),
    )

    return rows[0] if rows else None


def _token(
    row: Row,
) -> RemoteToken:
    """Return the token one row holds."""

    name = row[2]
    email = row[3]
    revoked = row[5]

    return RemoteToken(
        id=UUID(require_text(row[0], "A remote token ID was not text.")),
        name=require_text(row[1], "A remote token name was not text."),
        author=(
            None
            if name is None
            else Author(
                name=require_text(name, "A remote token author name was not text."),
                email=(
                    None
                    if email is None
                    else require_text(email, "A remote token author email was not text.")
                ),
            )
        ),
        created_at=datetime.fromisoformat(
            require_text(row[4], "A remote token creation time was not text.")
        ),
        revoked_at=(
            None
            if revoked is None
            else datetime.fromisoformat(
                require_text(revoked, "A remote token revocation time was not text.")
            )
        ),
    )


__all__ = [
    "BEARER_SCHEME",
    "REMOTE_TOKEN_TABLES",
    "TOKEN_NAME_PATTERN",
    "TOKEN_PREFIX",
    "IssuedToken",
    "RemoteToken",
    "RemoteTokenError",
    "RemoteTokenRepository",
    "SQLiteRemoteTokenRepository",
    "SqlRemoteTokenRepository",
    "TokenAuthenticator",
    "new_token_secret",
    "require_token_name",
    "token_digest",
]
