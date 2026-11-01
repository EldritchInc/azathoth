"""Reading the values of a row as the types a repository stored (ADR 0102)."""


def require_text(
    value: object,
    message: str,
) -> str:
    """Return a value that must be text.

    Raises:
        TypeError: It is not text; the message says what was expected.
    """

    if not isinstance(value, str):
        raise TypeError(message)

    return value


def require_integer(
    value: object,
    message: str,
) -> int:
    """Return a value that must be an integer.

    Raises:
        TypeError: It is not an integer; the message says what was expected.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(message)

    return value


__all__ = [
    "require_integer",
    "require_text",
]
