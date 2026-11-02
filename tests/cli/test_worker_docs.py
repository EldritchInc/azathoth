"""Tests that the worker's documentation quotes what the worker really says (ADR 0107)."""

import json
import re
from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.cli import build_parser
from azathoth.cli.worker import WORKER_INPUT_POLICY, settings_problems
from azathoth.inputs import InputResolutionError, ReferenceInput, SQLiteContentStore, resolve_input
from azathoth.worker import (
    MISSING_WORKER_EXTRA_MESSAGE,
    HeartbeatError,
    HeartbeatFile,
    QueueError,
    SettledMessage,
    SqsResultQueue,
    WorkerSettings,
    check_heartbeat,
    sqs_client,
)

PROJECT_ROOT = Path(__file__).parents[2]

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

WORKER_README = PROJECT_ROOT / "src" / "azathoth" / "worker" / "README.md"

INSTALL_GUIDE = PROJECT_ROOT / "docs" / "install.md"

CONTAINER_GUIDE = PROJECT_ROOT / "docs" / "container.md"

DOCUMENTED_HEARTBEAT = "/tmp/azathoth-heartbeat"


def text_blocks(
    path: Path,
) -> str:
    """Return every line inside the document's `text` blocks, one per line."""

    blocks = re.findall(r"```text\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)

    return "\n" + "\n".join(blocks) + "\n"


def assert_quoted(
    path: Path,
    message: str,
) -> None:
    """Check one document quotes a message as a whole line of a `text` block."""

    assert f"\n{message}\n" in text_blocks(path), (path.name, message)


def subcommand(
    parser: ArgumentParser,
    dest: str,
    name: str,
) -> ArgumentParser:
    """Return one subcommand's parser."""

    (commands,) = (
        action
        for action in parser._actions
        if isinstance(action, _SubParsersAction) and action.dest == dest
    )
    chosen = commands.choices[name]

    assert isinstance(chosen, ArgumentParser)

    return chosen


def section(
    path: Path,
    heading: str,
) -> str:
    """Return the text under one heading, up to the next heading of its level or above."""

    text = path.read_text(encoding="utf-8")
    level = heading.split(" ", 1)[0]
    start = text.index(f"\n{heading}\n")
    rest = text[start + len(heading) + 2 :]
    following = re.search(rf"^#{{1,{len(level)}}} ", rest, re.MULTILINE)

    return rest if following is None else rest[: following.start()]


@pytest.mark.parametrize("path", [CLI_README, WORKER_README, INSTALL_GUIDE])
def test_the_guides_quote_the_real_missing_extra_message(
    path: Path,
) -> None:
    assert_quoted(path, MISSING_WORKER_EXTRA_MESSAGE)


def test_the_cli_readme_quotes_the_real_reference_refusal(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri="file:///etc/hostname", media_type="text/plain"),
            policy=WORKER_INPUT_POLICY,
            store=SQLiteContentStore(tmp_path / "azathoth.db"),
        )

    assert_quoted(CLI_README, str(raised.value))


def test_the_cli_readme_quotes_the_real_settings_refusals() -> None:
    with pytest.raises(ValidationError) as range_error:
        WorkerSettings(wait_seconds=21)

    with pytest.raises(ValidationError) as extension_error:
        WorkerSettings(visibility_timeout_seconds=30, extend_every_seconds=30)

    (out_of_range,) = settings_problems(range_error.value)
    (too_rare,) = settings_problems(extension_error.value)

    assert_quoted(CLI_README, out_of_range)
    assert_quoted(CLI_README, too_rare.replace("30", "<SECONDS>"))
    assert_quoted(WORKER_README, too_rare.replace("30", "<SECONDS>"))


def test_the_cli_readme_quotes_the_real_queue_refusals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fifo = "https://sqs.us-east-1.amazonaws.com/123456789012/results.fifo"

    with pytest.raises(QueueError) as fifo_error:
        SqsResultQueue(fifo, client=object())

    assert_quoted(CLI_README, str(fifo_error.value).replace(fifo, "<URL>"))

    pytest.importorskip("boto3")

    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)

    empty = tmp_path / "aws-config"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty))

    local = "http://localhost:9324/000000000000/jobs"

    with pytest.raises(QueueError) as region_error:
        sqs_client(local)

    assert_quoted(CLI_README, str(region_error.value).replace(local, "<URL>"))


def test_the_readmes_quote_the_shape_of_a_failed_sqs_call() -> None:
    assert_quoted(CLI_README, "SQS ReceiveMessage failed on <URL>: <CODE>: <MESSAGE>")
    assert_quoted(WORKER_README, "SQS <OPERATION> failed on <URL>: <CODE>: <MESSAGE>")


def test_the_cli_readme_quotes_the_real_health_messages(
    tmp_path: Path,
) -> None:
    path = tmp_path / "heartbeat"

    missing = check_heartbeat(path, max_age_seconds=90).message

    HeartbeatFile(path).beat()
    beat_at = path.stat().st_mtime

    fresh = check_heartbeat(path, max_age_seconds=90, now=beat_at + 4).message
    stale = check_heartbeat(path, max_age_seconds=90, now=beat_at + 131).message

    for message in (missing, fresh, stale):
        assert_quoted(CLI_README, message.replace(str(path), DOCUMENTED_HEARTBEAT))


def test_the_cli_readme_quotes_the_real_heartbeat_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "heartbeat"

    with pytest.raises(HeartbeatError) as raised:
        HeartbeatFile(path).beat()

    documented = (
        str(raised.value)
        .replace(str(path), "<PATH>")
        .replace("No such file or directory", "<REASON>")
    )

    assert_quoted(CLI_README, documented)


@pytest.mark.parametrize("path", [CLI_README, WORKER_README])
def test_the_documented_log_line_is_a_settled_message(
    path: Path,
) -> None:
    (line,) = (
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith('{"message_id": ')
    )

    assert SettledMessage.model_validate_json(line).model_dump(mode="json") == json.loads(line)


def test_the_options_table_lists_every_worker_run_option() -> None:
    documented = re.findall(
        r"^\| `(--[a-z-]+)` \|",
        section(CLI_README, "## Worker Options"),
        re.MULTILINE,
    )

    run = subcommand(subcommand(build_parser(), "command", "worker"), "worker_action", "run")

    options = [
        option
        for action in run._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    ]

    assert documented == options


def test_the_container_guides_task_definition_parses() -> None:
    (block,) = re.findall(
        r"```json\n(\{\n  \"command\".*?)\n```",
        CONTAINER_GUIDE.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    definition = json.loads(block)

    run = build_parser().parse_args(definition["command"])
    health = definition["healthCheck"]["command"]

    assert run.worker_action == "run"
    assert health[:2] == ["CMD", "azathoth"]
    assert build_parser().parse_args(health[2:]).worker_action == "health"
    assert run.worker_heartbeat_file == build_parser().parse_args(health[2:]).worker_heartbeat_file
    assert definition["stopTimeout"] > 20
