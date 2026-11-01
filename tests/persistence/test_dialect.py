"""Tests for writing SQL once for both databases (ADR 0102)."""

import pytest

from azathoth.persistence import Dialect
from azathoth.persistence.dialect import TOKENS, identifier, render

TABLE = """
CREATE TABLE IF NOT EXISTS things (
    sequence {sequence},
    content {blob} NOT NULL
)
"""


def test_tokens_become_each_dialects_types() -> None:
    assert render(TABLE, Dialect.SQLITE) == (
        "\nCREATE TABLE IF NOT EXISTS things (\n"
        "    sequence INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    content BLOB NOT NULL\n)\n"
    )
    assert render(TABLE, Dialect.POSTGRES) == (
        "\nCREATE TABLE IF NOT EXISTS things (\n"
        "    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n"
        "    content BYTEA NOT NULL\n)\n"
    )


def test_every_token_has_a_spelling_in_every_dialect() -> None:
    for spellings in TOKENS.values():
        assert set(spellings) == set(Dialect)


def test_an_unknown_token_is_refused() -> None:
    with pytest.raises(ValueError, match=r"Unknown SQL token \{json\}"):
        render("CREATE TABLE t (payload {json})", Dialect.SQLITE)


def test_sqlite_keeps_question_mark_parameters() -> None:
    statement = "SELECT payload FROM t WHERE id = ? AND name LIKE ?"

    assert render(statement, Dialect.SQLITE) == statement


def test_postgresql_takes_percent_s_parameters() -> None:
    assert (
        render("SELECT payload FROM t WHERE id = ? AND n = ?", Dialect.POSTGRES)
        == "SELECT payload FROM t WHERE id = %s AND n = %s"
    )


def test_postgresql_escapes_every_literal_percent() -> None:
    assert render("SELECT 'a%b' WHERE x LIKE ?", Dialect.POSTGRES) == (
        "SELECT 'a%%b' WHERE x LIKE %s"
    )


def test_a_question_mark_inside_a_literal_is_not_a_parameter() -> None:
    assert render("""SELECT 'why?', "odd?" FROM t WHERE id = ?""", Dialect.POSTGRES) == (
        """SELECT 'why?', "odd?" FROM t WHERE id = %s"""
    )


def test_a_doubled_quote_stays_inside_its_literal() -> None:
    assert render("SELECT 'it''s?' WHERE id = ?", Dialect.POSTGRES) == (
        "SELECT 'it''s?' WHERE id = %s"
    )


def test_an_unterminated_literal_is_refused() -> None:
    with pytest.raises(ValueError, match="ends inside a quoted literal"):
        render("SELECT 'open", Dialect.POSTGRES)


@pytest.mark.parametrize("name", ["workflow_runs", "azathoth_schema", "t1"])
def test_table_names_are_lowercase_identifiers(
    name: str,
) -> None:
    assert identifier(name) == name


@pytest.mark.parametrize("name", ["Runs", "runs; DROP TABLE x", "1runs", "", "a-b"])
def test_anything_else_is_not_a_table_name(
    name: str,
) -> None:
    with pytest.raises(ValueError, match="is not a table name"):
        identifier(name)
