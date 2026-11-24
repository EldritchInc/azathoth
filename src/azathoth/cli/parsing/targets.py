"""Which instance a command runs on, as `--remote` names it (ADR 0140).

Every command takes `--remote <NAME>`, naming a remote this instance gave
a name, or its URL, to run on that remote rather than on this machine's
database. A command that never runs on a remote takes the option only to
say why, in a sentence of its own; one whose way onto the service API is
still to come says so too.
"""

from argparse import SUPPRESS, ArgumentParser, _SubParsersAction
from collections.abc import Iterator, Mapping
from typing import Final

REMOTE_OPTION: Final = "--remote"
"""The option naming the remote a command runs on."""

REMOTE_ATTRIBUTE: Final = "on_remote"
"""Where the parsed arguments keep the remote `--remote` named, or None."""

COMMAND_PATH_ATTRIBUTE: Final = "command_path"
"""Where the parsed arguments keep the command's words, such as `workflow list`."""

_LOCAL_REMOTE_NAMING: Final = (
    "names the remotes of this machine's database, so it takes no --remote."
)

NEVER_ON_A_REMOTE: Final[Mapping[str, str]] = {
    "init": "init prepares this machine's database, so it takes no --remote.",
    "worker run": "worker run works a queue on this machine, so it takes no --remote.",
    "worker health": "worker health checks this machine's worker, so it takes no --remote.",
    "remote serve": "remote serve runs a remote rather than calling one, so it takes no --remote.",
    "remote push": "remote push names the remote it pushes to itself, so it takes no --remote.",
    "remote pull": "remote pull names the remote it pulls from itself, so it takes no --remote.",
    "remote status": "remote status names the remote it asks itself, so it takes no --remote.",
    "remote add": f"remote add {_LOCAL_REMOTE_NAMING}",
    "remote list": f"remote list {_LOCAL_REMOTE_NAMING}",
    "remote remove": f"remote remove {_LOCAL_REMOTE_NAMING}",
    "remote token create": (
        "remote token create keeps a token in the database a remote is served from, "
        "so it takes no --remote."
    ),
    "remote token list": (
        "remote token list reads the tokens of the database a remote is served from, "
        "so it takes no --remote."
    ),
    "remote token revoke": (
        "remote token revoke changes the tokens of the database a remote is served from, "
        "so it takes no --remote."
    ),
    "tool verify": "tool verify runs a tool's tests on this machine, so it takes no --remote.",
}
"""Each command that never runs on a remote, and the sentence that says why."""

NOT_YET_ON_A_REMOTE: Final = frozenset(
    {
        "model authorize",
        "model deauthorize",
        "model list",
        "model policy",
        "model portfolio",
        "model show",
        "tool implementation-show",
        "tool implementations",
        "tool install-standard",
        "tool show",
        "tool test-case-show",
        "tool test-cases",
    }
)
"""The commands that still read this machine's database themselves, so run on no remote yet."""


def not_yet_message(
    command: str,
) -> str:
    """Return what a command not yet run on a remote says when `--remote` names one."""

    return f"{command} does not run on a remote yet, so it takes no --remote."


def remote_refusal(
    command: str,
) -> str | None:
    """Return why a command takes no `--remote`, or None when it runs on a remote."""

    if command in NEVER_ON_A_REMOTE:
        return NEVER_ON_A_REMOTE[command]

    if command in NOT_YET_ON_A_REMOTE:
        return not_yet_message(command)

    return None


def command_parsers(
    parser: ArgumentParser,
    words: tuple[str, ...] = (),
) -> Iterator[tuple[str, ArgumentParser]]:
    """Yield each command a parser parses, by its words, and the parser of its arguments.

    A command is a parser with no commands below it. A command named more
    than once, by an alias, is yielded once, by its first name.
    """

    below = [action for action in parser._actions if isinstance(action, _SubParsersAction)]

    if not below:
        yield " ".join(words), parser

        return

    seen: set[int] = set()

    for name, child in below[0].choices.items():
        if id(child) in seen:
            continue

        seen.add(id(child))
        yield from command_parsers(child, (*words, name))


def add_remote_options(
    parser: ArgumentParser,
) -> None:
    """Give every command a parser parses `--remote`, and its words to say which it is.

    A command that never runs on a remote takes the option hidden, so it
    can say why rather than that the option is unknown.
    """

    for command, arguments in command_parsers(parser):
        arguments.set_defaults(**{COMMAND_PATH_ATTRIBUTE: command})
        arguments.add_argument(
            REMOTE_OPTION,
            dest=REMOTE_ATTRIBUTE,
            metavar="NAME",
            default=None,
            help=(
                SUPPRESS
                if command in NEVER_ON_A_REMOTE
                else (
                    "Run on the remote this instance named NAME, or at the URL NAME, rather "
                    "than on this machine's database."
                )
            ),
        )


__all__ = [
    "COMMAND_PATH_ATTRIBUTE",
    "NEVER_ON_A_REMOTE",
    "NOT_YET_ON_A_REMOTE",
    "REMOTE_ATTRIBUTE",
    "REMOTE_OPTION",
    "add_remote_options",
    "command_parsers",
    "not_yet_message",
    "remote_refusal",
]
