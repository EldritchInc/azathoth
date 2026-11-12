"""Tests that ADRs 0124 to 0126 and the remote guide quote Azathoth's messages exactly."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.api.remote import NO_TOKEN_MESSAGE, no_token_message, not_named_message
from azathoth.cli.remote import (
    TOKEN_SHOWN_ONCE_NOTE,
    component_line,
    model_line,
    serving_line,
    status_lines,
)
from azathoth.remote import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MISSING_REMOTE_EXTRA_MESSAGE,
    ComponentStatus,
    InMemoryRemoteRepository,
    ModelStatus,
    ProtocolMismatchError,
    Relation,
    RemoteAlreadyNamedError,
    RemotePluginError,
    RemoteStatus,
    require_protocol,
    restricted_refusal,
)
from azathoth.remote.server import UNKNOWN_TOKEN_MESSAGE
from azathoth.revisions import Lineage, RevisionKind
from tests.remote.test_seams import Installed, TeamPolicy, default

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0124-remote.md"

GUIDE = ROOT / "docs" / "remote.md"

URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

SYNCED = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


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


STATUS_ADR = ROOT / "docs" / "adrs" / "0125-remote-status.md"


def test_the_status_adr_and_guide_quote_the_push_warnings_exactly() -> None:
    remote_readme = (ROOT / "src" / "azathoth" / "remote" / "README.md").read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")
    adr = STATUS_ADR.read_text(encoding="utf-8")
    warnings = [
        line
        for line in remote_readme.splitlines()
        if line.startswith(("Tool <TOOL_ID>", "Step <STEP_ID>")) and "remote" in line
    ]

    assert len(warnings) == 4

    for warning in warnings:
        assert f"\n{warning}\n" in adr

    for warning in (warnings[0], warnings[2], warnings[3]):
        assert f"\nWarning: {warning}\n" in guide


NAMES_ADR = ROOT / "docs" / "adrs" / "0126-named-remotes.md"


def naming_refusals() -> tuple[str, ...]:
    """Return the refusals naming a remote gives, with placeholders where they vary."""

    names = InMemoryRemoteRepository()
    names.add("origin", "https://azathoth.example.com")

    with pytest.raises(RemoteAlreadyNamedError) as taken:
        names.add("origin", "https://staging.example.com")

    return (
        str(taken.value)
        .replace("origin", "<NAME>")
        .replace("https://azathoth.example.com", "<URL>"),
        not_named_message("origin").replace("'origin'", "'<NAME>'"),
    )


def test_the_names_adr_quotes_its_messages_and_status_lines_exactly() -> None:
    for message in (
        *naming_refusals(),
        no_token_message("<VARIABLE>"),
        "Remote URL '<VALUE>' is not an http or https URL.",
        status_lines(RemoteStatus(remote="<REMOTE>", reachable=True))[0],
        *status_lines(RemoteStatus(remote="<REMOTE>", reachable=False)),
        status_lines(RemoteStatus(remote="<REMOTE>", reachable=False, portfolio_synced_at=SYNCED))[
            1
        ].replace(SYNCED.isoformat(), "<TIME>"),
        model_line(ModelStatus(identifier="<MODEL>", authorized_locally=True)),
    ):
        quoted(NAMES_ADR, message)


def test_the_guide_quotes_naming_and_a_status_as_they_are_printed() -> None:
    url = "http://127.0.0.1:8470"
    workflow = Lineage(kind=RevisionKind.WORKFLOW, id=UUID("a1000000-0000-4000-8000-000000000002"))

    for message in (
        f"Named remote origin for {url}; its token is read from AZATHOTH_REMOTE_TOKEN.",
        naming_refusals()[1],
        f"Status of origin ({url}): reached.",
        component_line(
            ComponentStatus(
                lineage=workflow,
                relation=Relation.IN_SYNC,
                local_digest="<DIGEST>",
                local_number=1,
                remote_digest="<DIGEST>",
                remote_number=1,
            ),
            reachable=True,
        ),
        f"Status of origin ({url}): not reached; its side is unknown.",
        "Its portfolio is as last read, at <TIME>.",
        component_line(
            ComponentStatus(
                lineage=workflow, relation=None, local_digest="<DIGEST>", local_number=1
            ),
            reachable=False,
        ),
    ):
        quoted(GUIDE, message)
