"""Tests of `--remote`, which runs a command on a remote rather than this machine (ADR 0140)."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.api.remote import not_named_message
from azathoth.cli import build_parser, main
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.parsing.targets import (
    NEVER_ON_A_REMOTE,
    NOT_YET_ON_A_REMOTE,
    REMOTE_ATTRIBUTE,
    command_parsers,
    not_yet_message,
)
from azathoth.cli.persistence import repositories
from azathoth.cli.remote_choice import (
    LOCAL_DATABASE_MESSAGE,
    RemoteChosenError,
    choosing,
    chosen_remote,
)
from azathoth.goals import Goal, encode_goal_document
from azathoth.remote import REMOTE_TOKEN_VARIABLE, Action
from tests.api.test_goals import answer_accurately, answer_briefly, save_goals
from tests.cli.test_workflow_run import configure_database
from tests.remote.asgi import AsgiHttp
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_conditions import Refusing

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

KINDLY = Goal(
    id=UUID("c1400000-0000-4000-8000-000000000003"),
    name="Answer kindly",
    description="Answer as a friend would.",
    success_criteria=("The answer is kind.",),
)

NEVER = frozenset(
    {
        "init",
        "worker run",
        "worker health",
        "remote serve",
        "remote push",
        "remote pull",
        "remote status",
        "remote add",
        "remote list",
        "remote remove",
        "remote token create",
        "remote token list",
        "remote token revoke",
        "tool verify",
    }
)


class Reaching:
    """The HTTP clients the command line makes, each sending its requests to one served remote."""

    def __init__(
        self,
        served: Served,
    ) -> None:
        self.served = served
        self.made: list[AsgiHttp] = []

    def __call__(
        self,
        **options: Any,
    ) -> AsgiHttp:
        made = AsgiHttp(self.served.app)
        self.made.append(made)

        return made

    @property
    def sent(
        self,
    ) -> list[tuple[str, str, bytes]]:
        return [request for made in self.made for request in made.sent]


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the command line at a database holding one goal, and naming the remote `origin`."""

    configured = configure_database(monkeypatch, tmp_path)
    save_goals(str(configured), answer_briefly())

    with api.open(configured) as instance:
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")

    return configured


@pytest.fixture
def remote_path(
    tmp_path: Path,
) -> Path:
    """Return the database a remote serves, holding another goal."""

    path = tmp_path / "remote.db"
    path.touch()
    save_goals(str(path), answer_accurately())

    return path


@pytest.fixture
def remote(
    remote_path: Path,
) -> Served:
    return Served(remote_path, principal=ERIS)


def reach(
    monkeypatch: pytest.MonkeyPatch,
    served: Served,
) -> Reaching:
    """Send every request the command line makes to an in-process remote."""

    reaching = Reaching(served)
    monkeypatch.setattr(httpx, "Client", reaching)

    return reaching


# Which commands take it


def test_every_command_takes_remote_but_those_that_never_run_on_one() -> None:
    commands = dict(command_parsers(build_parser()))

    assert set(NEVER_ON_A_REMOTE) == NEVER
    assert set(commands) >= NOT_YET_ON_A_REMOTE
    assert not NOT_YET_ON_A_REMOTE & NEVER

    for command, parser in commands.items():
        (option,) = [action for action in parser._actions if action.dest == REMOTE_ATTRIBUTE]

        assert option.option_strings == ["--remote"], command
        assert (option.help == "==SUPPRESS==") is (command in NEVER), command


def test_a_command_given_no_remote_runs_on_this_machine() -> None:
    parsed = build_parser().parse_args(("goal", "list"))

    assert getattr(parsed, REMOTE_ATTRIBUTE) is None
    assert parsed.command_path == "goal list"


@pytest.mark.parametrize("command", sorted(NEVER))
def test_a_command_that_never_runs_on_a_remote_says_why_in_a_sentence(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = {
        "remote push": ("origin",),
        "remote pull": ("origin",),
        "remote status": ("origin",),
        "remote add": ("origin", URL),
        "remote remove": ("origin",),
        "remote token create": ("laptop",),
        "remote token revoke": ("azr_x",),
        "tool verify": ("c1400000-0000-4000-8000-000000000001", "--version", "1.0.0"),
        "worker health": ("--heartbeat-file", "heartbeat"),
        "worker run": ("--queue-url", "https://sqs.example.com/queue"),
    }.get(command, ())

    try:
        status = main((*command.split(), *arguments, "--remote", "origin"))
    except SystemExit as exited:
        pytest.fail(f"{command} did not parse: {exited}")

    assert status == 2
    assert capsys.readouterr().err == f"{NEVER_ON_A_REMOTE[command]}\n"


def test_a_command_not_yet_run_on_a_remote_says_so(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(("workflow", "production", str(UUID(int=1)), "--remote", "origin")) == 2
    assert capsys.readouterr().err == f"{not_yet_message('workflow production')}\n"
    assert not_yet_message("workflow list") == (
        "workflow list does not run on a remote yet, so it takes no --remote."
    )


# Running on a remote


def test_a_command_given_a_remote_by_name_reads_the_remote_not_this_machine(
    database: Path,
    remote: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reaching = reach(monkeypatch, remote)

    assert main(("goal", "list")) == 0
    assert capsys.readouterr().out == f"{answer_briefly().id}  {answer_briefly().name}\n"
    assert reaching.sent == []

    assert main(("goal", "list", "--remote", "origin")) == 0
    assert capsys.readouterr().out == f"{answer_accurately().id}  {answer_accurately().name}\n"
    assert [(method, path) for method, path, _ in reaching.sent] == [
        ("POST", "/v1/calls/goals.list"),
    ]
    assert {made.authorizations[0] for made in reaching.made} == {"Bearer azr_origin"}


def test_a_command_given_a_remote_by_url_reads_it_with_the_token_its_variable_holds(
    database: Path,
    remote: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reaching = reach(monkeypatch, remote)
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_url")

    assert main(("goal", "show", str(answer_accurately().id), "--remote", URL)) == 0
    assert f"Name: {answer_accurately().name}\n" in capsys.readouterr().out
    assert reaching.made[0].authorizations == ["Bearer azr_url"]


def test_a_command_that_changes_what_it_is_given_changes_the_remote_only(
    database: Path,
    remote_path: Path,
    remote: Served,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reaching = reach(monkeypatch, remote)
    document = tmp_path / "goal.json"
    document.write_text(encode_goal_document(KINDLY), encoding="utf-8")

    assert main(("goal", "import", str(document), "--remote", "origin")) == 0

    (sent,) = [body for _, path, body in reaching.sent if path.endswith("goals.import_document")]

    assert json.loads(json.loads(sent)["document"])["id"] == str(KINDLY.id)

    with api.open(remote_path) as there, api.open(database) as here:
        assert {goal.id for goal in there.goals.list()} == {answer_accurately().id, KINDLY.id}
        assert [goal.id for goal in here.goals.list()] == [answer_briefly().id]


def test_a_remote_this_machine_does_not_name_is_refused_before_anything_is_sent(
    database: Path,
    remote: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reaching = reach(monkeypatch, remote)

    assert main(("goal", "list", "--remote", "elsewhere")) == 1
    assert capsys.readouterr().err == f"{not_named_message('elsewhere')}\n"
    assert reaching.made == []


def test_a_remote_whose_token_is_not_set_is_refused_before_anything_is_sent(
    database: Path,
    remote: Served,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reaching = reach(monkeypatch, remote)
    monkeypatch.delenv(TOKEN_VARIABLE)

    assert main(("goal", "list", "--remote", "origin")) == 1
    assert TOKEN_VARIABLE in capsys.readouterr().err
    assert reaching.made == []


def test_what_the_remote_refuses_is_said_in_a_line_as_a_local_refusal_is(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "refusing.db"
    path.touch()
    reach(monkeypatch, Served(path, principal=ERIS, policy=Refusing(Action.READ_CATALOG)))

    assert main(("goal", "list", "--remote", "origin")) == 1

    assert capsys.readouterr().err == "Eris may not read the catalog.\n"


# This machine's database, while a remote is chosen


def test_a_command_on_a_remote_is_refused_this_machines_database(
    database: Path,
) -> None:
    configuration = CliRuntimeConfiguration.from_environment()

    with choosing("origin"):
        assert chosen_remote() == "origin"

        with pytest.raises(RemoteChosenError) as caught:
            repositories(configuration)

    assert str(caught.value) == LOCAL_DATABASE_MESSAGE
    assert chosen_remote() is None
    assert repositories(configuration).goals.get(answer_briefly().id) is not None
