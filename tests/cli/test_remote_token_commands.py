"""Tests for the commands that issue, list and revoke a remote's tokens (ADR 0124)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import build_parser, main
from azathoth.cli.remote import TOKEN_SHOWN_ONCE_NOTE, token_line
from azathoth.remote import RemoteToken, SQLiteRemoteTokenRepository, TokenAuthenticator
from azathoth.revisions import AUTHOR_VARIABLE, Author
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_workflow_run import configure_database

ERIS = Author(name="Eris", email="eris@example.com")


def run(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an empty database, as Eris, with no runtime to load."""

    database = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTHOR_VARIABLE, str(ERIS))
    forbid_runtime(monkeypatch)

    return database


# Parsing


def test_the_token_actions_parse() -> None:
    parser = build_parser()

    created = parser.parse_args(("remote", "token", "create", "laptop"))
    listed = parser.parse_args(("remote", "token", "list", "--all"))
    revoked = parser.parse_args(("remote", "token", "revoke", "laptop"))

    assert (created.remote_action, created.remote_token_action) == ("token", "create")
    assert created.remote_token_name == "laptop"
    assert (listed.remote_token_action, listed.remote_token_all) == ("list", True)
    assert parser.parse_args(("remote", "token", "list")).remote_token_all is False
    assert (revoked.remote_token_action, revoked.remote_token_name) == ("revoke", "laptop")


@pytest.mark.parametrize("action", ["create", "revoke"])
def test_a_token_name_is_required(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("remote", "token", action))

    assert raised.value.code == 2
    assert "NAME" in capsys.readouterr().err


@pytest.mark.parametrize("arguments", [("remote",), ("remote", "token")])
def test_a_command_not_given_in_full_prints_help(
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    status, out, err = run(capsys, *arguments)

    assert (status, err) == (0, "")
    assert out.startswith("usage: azathoth")


def test_the_cli_dispatches_each_token_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def create(name: str) -> int:
        calls.append(("create", name))
        return 0

    def listed(*, include_revoked: bool) -> int:
        calls.append(("list", include_revoked))
        return 0

    def revoke(name: str) -> int:
        calls.append(("revoke", name))
        return 0

    monkeypatch.setattr(application, "create_remote_token", create)
    monkeypatch.setattr(application, "list_remote_tokens", listed)
    monkeypatch.setattr(application, "revoke_remote_token", revoke)

    assert main(("remote", "token", "create", "ci")) == 0
    assert main(("remote", "token", "list")) == 0
    assert main(("remote", "token", "list", "--all")) == 0
    assert main(("remote", "token", "revoke", "ci")) == 0
    assert calls == [("create", "ci"), ("list", False), ("list", True), ("revoke", "ci")]


# Creating


def test_a_created_token_is_shown_once_and_reaches_the_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = run(capsys, "remote", "token", "create", "laptop")
    tokens = SQLiteRemoteTokenRepository(database)
    (token,) = tokens.tokens()
    secret = out.splitlines()[1].removeprefix("Token: ")

    assert (status, err) == (0, "")
    assert out == f"Created remote token laptop.\nToken: {secret}\n{TOKEN_SHOWN_ONCE_NOTE}\n"
    assert secret.startswith("azr_")
    assert token.author == ERIS
    assert TokenAuthenticator(tokens).authenticate(f"Bearer {secret}") is not None
    assert TOKEN_SHOWN_ONCE_NOTE == (
        "Keep the token now: this remote keeps only its digest, and cannot show it again."
    )


def test_a_taken_or_malformed_name_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(capsys, "remote", "token", "create", "laptop")

    assert run(capsys, "remote", "token", "create", "laptop") == (
        1,
        "",
        "A remote token named 'laptop' already exists; revoke it first, or choose another name.\n",
    )
    assert run(capsys, "remote", "token", "create", "my laptop") == (
        1,
        "",
        "Remote token name 'my laptop' is not one: use 1 to 64 letters, digits, '.', '_' or '-'.\n",
    )


def test_creating_a_token_needs_to_know_who_creates_it(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(AUTHOR_VARIABLE, "<nobody>")

    status, out, err = run(capsys, "remote", "token", "create", "laptop")

    assert (status, out) == (1, "")
    assert err == 'AZATHOTH_AUTHOR is \'<nobody>\'; set it to "Name <email>" or "Name".\n'
    assert SQLiteRemoteTokenRepository(database).tokens(include_revoked=True) == ()


# Listing and revoking


def test_tokens_are_listed_and_revoked(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(capsys, "remote", "token", "create", "laptop")
    run(capsys, "remote", "token", "create", "ci")

    tokens = SQLiteRemoteTokenRepository(database)
    laptop, ci = tokens.tokens()

    assert run(capsys, "remote", "token", "list") == (
        0,
        f"{token_line(laptop)}\n{token_line(ci)}\n",
        "",
    )
    assert token_line(laptop) == (
        f"laptop  {laptop.created_at.isoformat()}  by Eris <eris@example.com>"
    )
    assert run(capsys, "remote", "token", "revoke", "laptop") == (
        0,
        "Revoked remote token laptop.\n",
        "",
    )

    (revoked, still) = tokens.tokens(include_revoked=True)

    assert revoked.revoked_at is not None
    assert run(capsys, "remote", "token", "list") == (0, f"{token_line(ci)}\n", "")
    assert run(capsys, "remote", "token", "list", "--all") == (
        0,
        f"{token_line(revoked)}\n{token_line(still)}\n",
        "",
    )
    assert token_line(revoked).endswith(f"  revoked {revoked.revoked_at.isoformat()}")


def test_a_token_without_an_author_names_none() -> None:
    created = datetime(2026, 11, 10, 21, 0, tzinfo=UTC)

    assert (
        token_line(RemoteToken(id=UUID(int=1), name="ci", created_at=created))
        == "ci  2026-11-10T21:00:00+00:00"
    )


def test_revoking_an_unknown_name_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(capsys, "remote", "token", "revoke", "laptop") == (
        1,
        "",
        "No remote token is named 'laptop'.\n",
    )


def test_the_guide_quotes_the_token_messages_exactly(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    readme = (Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md").read_text(
        encoding="utf-8"
    )
    created = run(capsys, "remote", "token", "create", "laptop")[1]
    secret = created.splitlines()[1].removeprefix("Token: azr_")
    messages = [
        *created.replace(secret, "<SECRET>").splitlines(),
        run(capsys, "remote", "token", "create", "laptop")[2],
        run(capsys, "remote", "token", "create", "my laptop")[2].replace("my laptop", "laptop"),
        run(capsys, "remote", "token", "revoke", "laptop")[1],
        run(capsys, "remote", "token", "revoke", "laptop")[2],
    ]

    for message in messages:
        documented = message.strip().replace("laptop", "<NAME>")

        assert f"\n{documented}\n" in readme
