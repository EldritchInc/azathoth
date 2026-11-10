"""Who a revision is recorded as authored by (ADR 0122)."""

import getpass
import os
import re
from collections.abc import Callable, Mapping
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

AUTHOR_VARIABLE: Final = "AZATHOTH_AUTHOR"
"""The environment variable naming who imports, as `Name <email>` or `Name`."""

AUTHOR_NAME_PATTERN: Final = r"^[^<>\s](?:[^<>\r\n]*[^<>\s])?$"
"""One line of text without angle brackets or surrounding whitespace."""

AUTHOR_EMAIL_PATTERN: Final = r"^[^@\s<>]+@[^@\s<>]+$"
"""One address: text, an `@`, and text, without whitespace or angle brackets."""

_AUTHOR_TEXT: Final = re.compile(r"\s*(?P<name>[^<>]*?)\s*(?:<(?P<email>[^<>]*)>)?\s*")


class AuthorError(ValueError):
    """Who is importing could not be told, or was given in the wrong form."""


class Author(BaseModel):
    """The person a revision is recorded as authored by.

    An author is recorded with each new revision. It is never part of a
    digest, so the same work imported by two people is the same content.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str = Field(
        pattern=AUTHOR_NAME_PATTERN,
    )

    email: str | None = Field(
        default=None,
        pattern=AUTHOR_EMAIL_PATTERN,
    )

    def __str__(
        self,
    ) -> str:
        """Return the author as `Name <email>`, or `Name` without an email."""

        if self.email is None:
            return self.name

        return f"{self.name} <{self.email}>"

    @classmethod
    def parse(
        cls,
        text: str,
    ) -> "Author":
        """Return the author written as `Name <email>` or `Name`.

        Whitespace around the name and the address is ignored.

        Raises:
            AuthorError: The text is not in either form.
        """

        match = _AUTHOR_TEXT.fullmatch(text)

        try:
            if match is None:
                raise ValueError(text)

            return cls(
                name=match.group("name"),
                email=match.group("email"),
            )
        except (ValueError, ValidationError) as exc:
            raise AuthorError(f'Author {text!r} is not "Name <email>" or "Name".') from exc


def resolve_author(
    environment: Mapping[str, str] | None = None,
    *,
    username: Callable[[], str] = getpass.getuser,
) -> Author:
    """Return who is importing, from the first of these that is set.

    1. `AZATHOTH_AUTHOR`, as `Name <email>` or `Name`. Empty or blank counts
       as unset.
    2. The operating system's username, without an email.

    `environment` defaults to the process environment.

    Raises:
        AuthorError: `AZATHOTH_AUTHOR` is malformed, or it is unset and
            there is no usable username.
    """

    variables = os.environ if environment is None else environment

    value = variables.get(AUTHOR_VARIABLE, "")

    if value.strip():
        try:
            return Author.parse(value)
        except AuthorError as exc:
            raise AuthorError(
                f'{AUTHOR_VARIABLE} is {value!r}; set it to "Name <email>" or "Name".'
            ) from exc

    try:
        return Author(name=username().strip())
    except (OSError, KeyError, ValidationError) as exc:
        raise AuthorError(
            f'Could not tell who is importing; set {AUTHOR_VARIABLE} to "Name <email>" or "Name".'
        ) from exc


__all__ = [
    "AUTHOR_EMAIL_PATTERN",
    "AUTHOR_NAME_PATTERN",
    "AUTHOR_VARIABLE",
    "Author",
    "AuthorError",
    "resolve_author",
]
