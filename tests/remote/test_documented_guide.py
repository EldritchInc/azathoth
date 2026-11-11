"""Tests that ADR 0124 and the remote guide quote Azathoth's messages exactly."""

from pathlib import Path

import pytest

from azathoth.api.remote import NO_TOKEN_MESSAGE
from azathoth.cli.remote import TOKEN_SHOWN_ONCE_NOTE, serving_line
from azathoth.remote import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MISSING_REMOTE_EXTRA_MESSAGE,
    ProtocolMismatchError,
    RemotePluginError,
    require_protocol,
    restricted_refusal,
)
from azathoth.remote.server import UNKNOWN_TOKEN_MESSAGE
from tests.remote.test_seams import Installed, TeamPolicy, default

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0124-remote.md"

GUIDE = ROOT / "docs" / "remote.md"

URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def quoted(
    path: Path,
    message: str,
) -> None:
    """Require a document to quote one message as a line of its own."""

    assert f"\n{message}\n" in path.read_text(encoding="utf-8")


def protocol_refusal() -> str:
    with pytest.raises(ProtocolMismatchError) as caught:
        require_protocol(2)

    return str(caught.value).replace("protocol 2,", "protocol <PROTOCOL>,")


def plugin_refusal() -> str:
    with pytest.raises(RemotePluginError) as caught:
        default(
            Installed("policy", "b:policy", TeamPolicy),
            Installed("policy", "a:policy", TeamPolicy),
        )

    return (
        str(caught.value)
        .replace("policy seam", "<SEAM> seam")
        .replace("a:policy", "<FIRST>")
        .replace("b:policy", "<SECOND>")
    )


DIVERGED = (
    "Workflow <WORKFLOW_ID> has diverged: its latest revision here, <LATEST>, is not the one "
    "revision <DIGEST> builds on. Pull first, then push again."
)


def test_the_adr_quotes_the_refusals_exactly() -> None:
    for message in (
        protocol_refusal(),
        plugin_refusal(),
        restricted_refusal("This push carries restricted data"),
        DIVERGED,
    ):
        quoted(ADR, message)


def test_the_guide_quotes_the_messages_exactly() -> None:
    for message in (
        TOKEN_SHOWN_ONCE_NOTE,
        serving_line(URL, accept_restricted=False),
        serving_line(URL, accept_restricted=True),
        restricted_refusal("This push carries restricted data"),
        UNKNOWN_TOKEN_MESSAGE,
        NO_TOKEN_MESSAGE,
        protocol_refusal(),
        MISSING_REMOTE_EXTRA_MESSAGE,
        DIVERGED,
        "Forked <LINEAGE>: its pulled revisions build on an earlier revision here.",
        "Withheld <LINEAGE>: it is restricted; pull it with --include-restricted.",
    ):
        quoted(GUIDE, message)
