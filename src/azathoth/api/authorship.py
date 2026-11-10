"""Who an instance records as the author of what it imports (ADR 0122)."""

from collections.abc import Callable

from azathoth.api.errors import InvalidAuthorError
from azathoth.api.models import Author as AuthorView
from azathoth.revisions import Author, AuthorError, resolve_author

AuthorAccess = Callable[[], Author]
"""Returns who is importing now, or raises `InvalidAuthorError`."""


def author_access(
    author: str | None,
) -> AuthorAccess:
    """Return how an instance tells who is importing.

    A given author, as `Name <email>` or `Name`, is parsed once and always
    returned. Without one, the author is resolved at each import, from
    `AZATHOTH_AUTHOR` and then the operating system's username.

    Raises:
        InvalidAuthorError: The given author is not in either form.
    """

    if author is not None:
        try:
            given = Author.parse(author)
        except AuthorError as exc:
            raise InvalidAuthorError(str(exc)) from exc

        return lambda: given

    def resolved() -> Author:
        try:
            return resolve_author()
        except AuthorError as exc:
            raise InvalidAuthorError(str(exc)) from exc

    return resolved


def author_view(
    author: Author | None,
) -> AuthorView | None:
    """Return the API's view of a recorded author, or None when none was recorded."""

    if author is None:
        return None

    return AuthorView(name=author.name, email=author.email)


__all__ = [
    "AuthorAccess",
    "author_access",
    "author_view",
]
