"""What differs between the SQL of SQLite and of PostgreSQL (ADR 0102).

Statements are written once, with `?` parameters, and tables once, with a
token for each column type the two spell differently.
"""

import re
from enum import StrEnum
from typing import Final


class Dialect(StrEnum):
    """The SQL dialects Azathoth speaks."""

    SQLITE = "sqlite"
    POSTGRES = "postgresql"


TOKENS: Final[dict[str, dict[Dialect, str]]] = {
    "{sequence}": {
        Dialect.SQLITE: "INTEGER PRIMARY KEY AUTOINCREMENT",
        Dialect.POSTGRES: "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
    },
    "{blob}": {
        Dialect.SQLITE: "BLOB",
        Dialect.POSTGRES: "BYTEA",
    },
}
"""The DDL tokens, and what each becomes in each dialect."""

_IDENTIFIER: Final = re.compile(r"[a-z_][a-z0-9_]*")

_LEFTOVER_TOKEN: Final = re.compile(r"\{[a-z_]+\}")


def render(
    statement: str,
    dialect: Dialect,
) -> str:
    """Return one statement in a dialect: its tokens replaced, its parameters placed.

    Raises:
        ValueError: The statement names a token that does not exist.
    """

    rendered = statement

    for token, spellings in TOKENS.items():
        rendered = rendered.replace(token, spellings[dialect])

    leftover = _LEFTOVER_TOKEN.search(rendered)

    if leftover is not None:
        raise ValueError(f"Unknown SQL token {leftover.group()}.")

    if dialect is Dialect.POSTGRES:
        return _postgres_parameters(rendered)

    return rendered


def _postgres_parameters(
    statement: str,
) -> str:
    """Turn `?` parameters into psycopg's `%s`, and escape every literal `%`.

    A `?` or `%` inside a quoted literal or identifier is left as it is,
    apart from the escaping psycopg needs for `%`.
    """

    rendered: list[str] = []
    quote: str | None = None

    for character in statement:
        if quote is not None:
            if character == quote:
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "?":
            rendered.append("%s")
            continue

        rendered.append("%%" if character == "%" else character)

    if quote is not None:
        raise ValueError("A statement ends inside a quoted literal.")

    return "".join(rendered)


def identifier(
    name: str,
) -> str:
    """Return a table name that is safe to place in a statement as it is.

    Raises:
        ValueError: The name is not a lowercase SQL identifier.
    """

    if _IDENTIFIER.fullmatch(name) is None:
        raise ValueError(f"{name!r} is not a table name.")

    return name


__all__ = [
    "TOKENS",
    "Dialect",
    "identifier",
    "render",
]
