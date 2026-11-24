"""Tests for `azathoth remote add`, `list` and `remove`, and pushing to a name (ADRs 0126, 0141)."""

import shlex
from pathlib import Path

import pytest

import azathoth.cli.application as application
from azathoth.cli import build_parser, main
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import REMOTE_TOKEN_VARIABLE, PortfolioResponse
from azathoth.revisions import AUTHOR_VARIABLE
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_remote_sync_commands import reach
from tests.cli.test_remote_token_commands import ERIS, run
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_closure import PARENT_ID, child, parent
from tests.remote.test_server import Remote
from tests.remote.test_token_commands import printing_in_turn, python, runs

URL = "http://remote.test"

STAGING = "https://staging.example.com"

SHARED_TOKEN = "AZATHOTH_SHARED_TOKEN"

GUIDE = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

GCLOUD = "gcloud auth print-identity-token --audiences 'https://team example'"


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at a database holding a child workflow and two revisions of its parent."""

    configured = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTHOR_VARIABLE, str(ERIS))
    forbid_runtime(monkeypatch)
    held = open_repositories(configured)
    held.workflows.save(child())
    held.workflows.save(parent())
    held.workflows.save(parent("Counts again."))

    return configured


# Parsing


def test_a_remote_is_added_with_a_name_a_url_and_a_token_variable() -> None:
    parsed = build_parser().parse_args(
        ("remote", "add", "staging", STAGING, "--token-variable", SHARED_TOKEN)
    )

    assert (parsed.remote_name, parsed.remote_url, parsed.remote_token_variable) == (
        "staging",
        STAGING,
        SHARED_TOKEN,
    )
    assert (
        build_parser().parse_args(("remote", "add", "origin", URL)).remote_token_variable
        == REMOTE_TOKEN_VARIABLE
    )


def test_a_remote_is_added_with_the_command_its_token_is_printed_by() -> None:
    parsed = build_parser().parse_args(
        ("remote", "add", "team", STAGING, "--token-command", GCLOUD)
    )

    assert parsed.remote_token_command == GCLOUD
    assert build_parser().parse_args(("remote", "add", "origin", URL)).remote_token_command is None


def test_a_remote_is_added_with_a_token_variable_or_a_command_not_both(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(
            (
                "remote",
                "add",
                "team",
                STAGING,
                "--token-variable",
                SHARED_TOKEN,
                "--token-command",
                GCLOUD,
            )
        )

    assert caught.value.code == 2
    assert (
        "argument --token-command: not allowed with argument --token-variable"
        in capsys.readouterr().err
    )


def test_the_cli_dispatches_add_list_and_remove(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def add(**options: object) -> int:
        calls.append(("add", options))
        return 0

    def listed() -> int:
        calls.append(("list", None))
        return 0

    def remove(name: str) -> int:
        calls.append(("remove", name))
        return 0

    monkeypatch.setattr(application, "add_remote", add)
    monkeypatch.setattr(application, "list_remotes", listed)
    monkeypatch.setattr(application, "remove_remote", remove)

    assert main(("remote", "add", "origin", URL)) == 0
    assert main(("remote", "add", "team", URL, "--token-command", GCLOUD)) == 0
    assert main(("remote", "list")) == 0
    assert main(("remote", "remove", "origin")) == 0
    assert calls == [
        (
            "add",
            {
                "name": "origin",
                "url": URL,
                "token_variable": REMOTE_TOKEN_VARIABLE,
                "token_command": None,
            },
        ),
        (
            "add",
            {
                "name": "team",
                "url": URL,
                "token_variable": REMOTE_TOKEN_VARIABLE,
                "token_command": GCLOUD,
            },
        ),
        ("list", None),
        ("remove", "origin"),
    ]


# Naming


def test_a_remote_is_named_listed_and_removed(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(capsys, "remote", "list") == (0, "", "")
    assert run(capsys, "remote", "add", "origin", f"{URL}/") == (
        0,
        f"Named remote origin for {URL}; its token is read from AZATHOTH_REMOTE_TOKEN.\n",
        "",
    )
    assert run(capsys, "remote", "add", "staging", STAGING, "--token-variable", SHARED_TOKEN) == (
        0,
        f"Named remote staging for {STAGING}; its token is read from {SHARED_TOKEN}.\n",
        "",
    )
    assert run(capsys, "remote", "list") == (
        0,
        f"origin  {URL}  AZATHOTH_REMOTE_TOKEN\nstaging  {STAGING}  {SHARED_TOKEN}\n",
        "",
    )
    assert run(capsys, "remote", "remove", "origin") == (
        0,
        f"Removed remote origin, for {URL}; nothing at the remote changed.\n",
        "",
    )
    assert run(capsys, "remote", "list") == (0, f"staging  {STAGING}  {SHARED_TOKEN}\n", "")


def test_a_remote_is_named_with_the_command_its_token_is_printed_by_and_listed(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shown = "gcloud auth print-identity-token --audiences 'https://team example'"

    assert run(capsys, "remote", "add", "team", STAGING, "--token-command", GCLOUD) == (
        0,
        f"Named remote team for {STAGING}; its token is printed by `{shown}`.\n",
        "",
    )
    assert run(capsys, "remote", "add", "origin", URL) == (
        0,
        f"Named remote origin for {URL}; its token is read from AZATHOTH_REMOTE_TOKEN.\n",
        "",
    )
    assert run(capsys, "remote", "list") == (
        0,
        f"origin  {URL}  AZATHOTH_REMOTE_TOKEN\nteam  {STAGING}  `{shown}`\n",
        "",
    )

    (team,) = (
        remote for remote in open_repositories(database).remotes.remotes() if remote.name == "team"
    )

    assert team.token_command == (
        "gcloud",
        "auth",
        "print-identity-token",
        "--audiences",
        "https://team example",
    )


def test_naming_a_remote_with_a_command_does_not_run_it(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    count = tmp_path / "count"
    command = shlex.join(printing_in_turn(count, "azr_x"))

    assert run(capsys, "remote", "add", "team", STAGING, "--token-command", command)[0] == 0
    assert runs(count) == 0


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("", "A token command names the program that prints the token; it was empty."),
        (
            "gcloud auth 'print-identity-token",
            'Token command "gcloud auth \'print-identity-token" cannot be split into '
            "arguments: No closing quotation.",
        ),
    ],
    ids=["empty", "unclosed-quote"],
)
def test_a_token_command_that_is_not_one_says_why(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    message: str,
) -> None:
    assert run(capsys, "remote", "add", "team", STAGING, "--token-command", command) == (
        1,
        "",
        f"{message}\n",
    )
    assert run(capsys, "remote", "list") == (0, "", "")


def test_removing_a_name_forgets_its_portfolio_snapshot(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshots = open_repositories(database).remote_portfolio_snapshots
    run(capsys, "remote", "add", "origin", URL)
    snapshots.save(URL, PortfolioResponse())

    run(capsys, "remote", "remove", "origin")

    assert snapshots.get(URL) is None


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            ("add", "origin", STAGING),
            f"Remote origin is already named, for {URL}; remove it first, or choose another name.",
        ),
        (
            ("add", "my.remote", STAGING),
            "Remote name 'my.remote' is not one: use 1 to 64 letters, digits, '_' or '-'.",
        ),
        (
            ("add", "staging", "staging.example.com"),
            "Remote URL 'staging.example.com' is not an http or https URL.",
        ),
        (
            ("add", "staging", STAGING, "--token-variable", "SHARED-TOKEN"),
            "Token variable 'SHARED-TOKEN' is not an environment variable's name: use letters, "
            "digits and '_', not beginning with a digit.",
        ),
        (
            ("remove", "staging"),
            "No remote is named 'staging'; name one with `azathoth remote add <NAME> <URL>`.",
        ),
    ],
    ids=["taken", "name", "url", "variable", "never-named"],
)
def test_a_name_that_cannot_be_given_or_removed_says_why(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
    message: str,
) -> None:
    run(capsys, "remote", "add", "origin", URL)

    assert run(capsys, "remote", *arguments) == (1, "", f"{message}\n")
    assert run(capsys, "remote", "list") == (0, f"origin  {URL}  AZATHOTH_REMOTE_TOKEN\n", "")


# Pushing and pulling by name


def test_a_push_and_pull_reach_a_remote_by_its_name(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    served = Remote(tmp_path)
    reach(monkeypatch, served)
    run(capsys, "remote", "add", "origin", URL)

    status, output, _ = run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID))

    assert status == 0
    assert output.startswith(f"Pushed to {URL}. Revisions received: 3.")

    status, output, _ = run(capsys, "remote", "pull", "origin", "--workflow", str(PARENT_ID))

    assert status == 0
    assert output.startswith(f"Pulled from {URL}. Revisions saved: 0.")


def test_a_name_reads_its_token_from_its_own_variable(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    served = Remote(tmp_path)
    reach(monkeypatch, served)
    run(capsys, "remote", "add", "origin", URL, "--token-variable", SHARED_TOKEN)
    monkeypatch.delenv(SHARED_TOKEN, raising=False)

    assert run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID)) == (
        1,
        "",
        f"No remote token was given; set {SHARED_TOKEN} to one created on the remote with "
        "`azathoth remote token create`.\n",
    )

    monkeypatch.setenv(SHARED_TOKEN, served.token)
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_not_this_one")

    status, output, _ = run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID))

    assert status == 0
    assert output.startswith(f"Pushed to {URL}. Revisions received: 3.")


def test_a_push_reaches_a_name_with_the_token_its_command_prints(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    served = Remote(tmp_path)
    reach(monkeypatch, served)
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_not_this_one")
    count = tmp_path / "count"
    command = shlex.join(printing_in_turn(count, served.token))
    run(capsys, "remote", "add", "origin", URL, "--token-command", command)

    status, output, _ = run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID))

    assert status == 0
    assert output.startswith(f"Pushed to {URL}. Revisions received: 3.")
    assert runs(count) == 1


def test_a_push_to_a_name_whose_command_fails_says_why(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    command = python("import sys; sys.stderr.write('Sign in again.'); sys.exit(2)")
    run(capsys, "remote", "add", "origin", URL, "--token-command", shlex.join(command))

    assert run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID)) == (
        1,
        "",
        f"Token command `{shlex.join(command)}` exited with status 2: Sign in again.\n",
    )


def test_pushing_to_a_name_never_given_says_so_and_sends_nothing(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID)) == (
        1,
        "",
        "No remote is named 'origin'; name one with `azathoth remote add <NAME> <URL>`.\n",
    )


def test_the_guide_quotes_the_naming_lines_and_refusals() -> None:
    guide = GUIDE.read_text(encoding="utf-8")

    for line in (
        "Named remote origin for https://azathoth.example.com; its token is read from "
        "AZATHOTH_REMOTE_TOKEN.",
        "origin  https://azathoth.example.com  AZATHOTH_REMOTE_TOKEN",
        "Removed remote origin, for https://azathoth.example.com; nothing at the remote changed.",
        "Remote <NAME> is already named, for <URL>; remove it first, or choose another name.",
        "No remote is named '<NAME>'; name one with `azathoth remote add <NAME> <URL>`.",
        "No remote token was given; set <VARIABLE> to one created on the remote with "
        "`azathoth remote token create`.",
    ):
        assert line in guide, line
