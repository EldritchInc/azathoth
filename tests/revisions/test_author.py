"""Tests for who a revision is recorded as authored by."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from azathoth.revisions import (
    AUTHOR_VARIABLE,
    Author,
    AuthorError,
    resolve_author,
)


def unreachable_username() -> str:
    raise AssertionError("The OS username was asked for.")


def no_username() -> str:
    raise OSError("No username.")


def test_the_author_variable_is_named() -> None:
    assert AUTHOR_VARIABLE == "AZATHOTH_AUTHOR"


def test_an_author_with_an_email_reads_as_name_and_address() -> None:
    assert str(Author(name="Eris Discordia", email="eris@example.com")) == (
        "Eris Discordia <eris@example.com>"
    )


def test_an_author_without_an_email_reads_as_their_name() -> None:
    assert str(Author(name="eris")) == "eris"


def test_an_author_has_no_email_by_default() -> None:
    assert Author(name="eris").email is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Eris Discordia <eris@example.com>",
            Author(name="Eris Discordia", email="eris@example.com"),
        ),
        ("  Eris   <eris@example.com>  ", Author(name="Eris", email="eris@example.com")),
        ("Eris<eris@example.com>", Author(name="Eris", email="eris@example.com")),
        ("Eris Discordia", Author(name="Eris Discordia")),
        ("  señal  ", Author(name="señal")),
    ],
)
def test_an_author_is_parsed_from_name_and_optional_address(
    text: str,
    expected: Author,
) -> None:
    assert Author.parse(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "<eris@example.com>",
        "Eris <>",
        "Eris <eris>",
        "Eris <eris@>",
        "Eris <@example.com>",
        "Eris <eris@example.com",
        "Eris eris@example.com>",
        "Eris <eris@example.com> trailing",
        "Eris <eris @example.com>",
        "Eris\nDiscordia",
    ],
)
def test_a_malformed_author_is_refused(
    text: str,
) -> None:
    with pytest.raises(AuthorError) as caught:
        Author.parse(text)

    assert str(caught.value) == f'Author {text!r} is not "Name <email>" or "Name".'


def test_an_author_error_is_a_value_error() -> None:
    assert issubclass(AuthorError, ValueError)


@pytest.mark.parametrize(
    "name",
    ["", " Eris", "Eris ", "Eris <x>", "Eris\nDiscordia"],
)
def test_an_author_name_is_trimmed_text_on_one_line(
    name: str,
) -> None:
    with pytest.raises(ValidationError):
        Author(name=name)


@pytest.mark.parametrize(
    "email",
    ["", "eris", "eris@", "@example.com", "eris @example.com", "<eris@example.com>"],
)
def test_an_author_email_is_one_address(
    email: str,
) -> None:
    with pytest.raises(ValidationError):
        Author(name="Eris", email=email)


def test_an_author_is_frozen_and_closed() -> None:
    author = Author(name="Eris")

    field = "name"

    with pytest.raises(ValidationError):
        setattr(author, field, "Discordia")

    with pytest.raises(ValidationError):
        Author.model_validate({"name": "Eris", "handle": "eris"})


def test_the_author_variable_comes_first() -> None:
    author = resolve_author(
        {AUTHOR_VARIABLE: "Eris Discordia <eris@example.com>"},
        username=unreachable_username,
    )

    assert author == Author(name="Eris Discordia", email="eris@example.com")


def test_the_os_username_is_used_when_the_variable_is_unset() -> None:
    assert resolve_author({}, username=lambda: "oren") == Author(name="oren")


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_author_variable_counts_as_unset(
    value: str,
) -> None:
    assert resolve_author({AUTHOR_VARIABLE: value}, username=lambda: "oren") == Author(name="oren")


def test_a_malformed_author_variable_is_refused_rather_than_ignored() -> None:
    with pytest.raises(AuthorError) as caught:
        resolve_author({AUTHOR_VARIABLE: "Eris <eris>"}, username=unreachable_username)

    assert str(caught.value) == (
        'AZATHOTH_AUTHOR is \'Eris <eris>\'; set it to "Name <email>" or "Name".'
    )


def test_the_os_username_is_trimmed() -> None:
    assert resolve_author({}, username=lambda: "  oren  ") == Author(name="oren")


@pytest.mark.parametrize(
    "username",
    [no_username, lambda: "", lambda: "  ", lambda: "a<b>"],
)
def test_no_usable_username_asks_for_the_variable(
    username: Callable[[], str],
) -> None:
    with pytest.raises(AuthorError) as caught:
        resolve_author({}, username=username)

    assert str(caught.value) == (
        'Could not tell who is importing; set AZATHOTH_AUTHOR to "Name <email>" or "Name".'
    )


def test_the_process_environment_is_read_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "Discordia <discordia@example.com>")

    assert resolve_author() == Author(name="Discordia", email="discordia@example.com")
