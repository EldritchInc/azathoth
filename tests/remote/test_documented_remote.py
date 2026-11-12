"""Tests that the remote package's README quotes its messages exactly (ADR 0124)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth import __version__
from azathoth.inputs import InMemoryContentStore, content_bytes_digest
from azathoth.remote import (
    MAX_CONTENT_BYTES,
    Action,
    OwnerOnlyPolicy,
    Principal,
    ProtocolMismatchError,
    PushBundle,
    ReceiveRefusedError,
    RemotePluginError,
    RemoteUnreachableError,
    RevisionRecord,
    child_drift_warnings,
    missing_credential_warning,
    receive_content,
    require_protocol,
    require_remote_url,
    unapproved_model_warnings,
)
from azathoth.remote.server import UNKNOWN_TOKEN_MESSAGE
from azathoth.revisions import Lineage, RevisionKind, content_digest, json_digest, revision_digest
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import WorkflowSpecification
from tests.remote.test_client import URL as CLIENT_URL
from tests.remote.test_client import answering
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    CALL_STEP,
    CHILD,
    CHILD_ID,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    SUMMARIZE_STEP,
    Instance,
    StaleWorkflows,
    call,
    child,
    parent,
    specification,
    tool_step,
)
from tests.remote.test_receiving import (
    CHART,
    CHART_BYTES,
    Bare,
    bundle,
    charts,
    first_record,
    local_with_history,
    received_by,
)
from tests.remote.test_records import WORKFLOW_ID, record, tampered
from tests.remote.test_records import specification as counting
from tests.remote.test_seams import Installed, TeamPolicy, default
from tests.remote.test_status import (
    PROMPT_STEP,
    TOOL,
    A,
    B,
    prompting,
    running_child,
)

README = Path(__file__).parents[2] / "src" / "azathoth" / "remote" / "README.md"


def documented(
    message: str,
) -> None:
    """Require the README to quote one message, as a line of its own."""

    assert f"\n{message}\n" in README.read_text(encoding="utf-8")


def refusal(
    error: pytest.ExceptionInfo[ValidationError],
) -> str:
    """Return the message of a model's one refusal."""

    (only,) = error.value.errors()

    return str(only["ctx"]["error"])


def test_the_protocol_refusal_is_documented() -> None:
    with pytest.raises(ProtocolMismatchError) as caught:
        require_protocol(2)

    documented(str(caught.value).replace("protocol 2,", "protocol <PROTOCOL>,"))


def test_the_record_refusals_are_documented() -> None:
    original = record(Lineage(kind=RevisionKind.WORKFLOW, id=WORKFLOW_ID), counting())
    changed = counting("tally")
    parent = "d" * 64
    names = {
        original.revision_digest: "<DIGEST>",
        str(WORKFLOW_ID): "<WORKFLOW_ID>",
        content_digest(changed): "<HELD>",
        original.content_digest: "<CONTENT_DIGEST>",
        revision_digest(
            original.lineage,
            content_digest=original.content_digest,
            parent_digest=parent,
        ): "<COMPUTED>",
    }

    for changes in (
        {"lineage": {"kind": "workflow", "id": str(PARENT_ID)}},
        {"document": changed.model_dump(mode="json")},
        {"parent_digest": parent},
    ):
        with pytest.raises(ValidationError) as caught:
            tampered(original, **changes)

        message = refusal(caught)

        for value, placeholder in {**names, str(PARENT_ID): "<WORKFLOW_ID>"}.items():
            message = message.replace(value, placeholder)

        documented(message)


def test_the_closure_messages_are_documented() -> None:
    parent = Lineage(kind=RevisionKind.WORKFLOW, id=PARENT_ID)
    held = Instance()
    held.workflows.save(child())
    held.workflows.save(
        specification(
            PARENT_ID,
            tool_step(CALL_STEP, "run_workflow", "1.0.0", call("named later")),
        )
    )
    unheld = Instance()
    unheld.workflows.save(
        specification(
            PARENT_ID,
            tool_step(CALL_STEP, "run_workflow", "1.0.0", call({"workflow_id": str(CHILD_ID)})),
        )
    )
    stale = Instance()
    stale.workflows = StaleWorkflows()
    stale.workflows.save(child())
    stale.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "2")))

    messages = (
        *Instance().closure(parent).unresolved,
        *held.closure(CHILD, parent).unresolved,
        *unheld.closure(parent).unresolved,
        stale.closure(CHILD).unresolved[-1],
    )
    names = {
        str(SUMMARIZE_STEP): "<STEP_ID>",
        str(CALL_STEP): "<STEP_ID>",
        f"workflow {CHILD_ID}, which": "workflow <CHILD_ID>, which",
        str(CHILD_ID): "<WORKFLOW_ID>",
        str(PARENT_ID): "<WORKFLOW_ID>",
        "summarize of any version": "<NAME> <VERSION>",
        "e" * 64: "<CONTENT_DIGEST>",
        "Revision 2": "Revision <NUMBER>",
    }

    assert len(messages) == 5

    for message in messages:
        for value, placeholder in names.items():
            message = message.replace(value, placeholder)

        documented(message)


def test_the_policys_refusal_is_documented() -> None:
    decision = OwnerOnlyPolicy().decide(Principal(name="guest"), Action.PUSH, None)

    assert decision.reason is not None

    documented(decision.reason.replace("guest", "<PRINCIPAL>").replace("push", "<ACTION>"))


def test_the_plugin_refusals_are_documented() -> None:
    cases = (
        (
            (
                Installed("policy", "b:policy", TeamPolicy),
                Installed("policy", "a:policy", TeamPolicy),
            ),
            {"policy": "<SEAM>", "a:<SEAM>": "<FIRST>", "b:<SEAM>": "<SECOND>"},
        ),
        (
            (Installed("streams", "extra:streams", TeamPolicy),),
            {"extra:streams": "<PLUGIN>", "'streams'": "'<NAME>'"},
        ),
        (
            (Installed("audit", "broken:factory", object),),
            {
                "broken:factory": "<PLUGIN>",
                "audit seam": "<SEAM> seam",
                "of object": "of <TYPE>",
                "an AuditSink": "<KIND>",
            },
        ),
    )

    for installed, names in cases:
        with pytest.raises(RemotePluginError) as caught:
            default(*installed)

        message = str(caught.value)

        for value, placeholder in names.items():
            message = message.replace(value, placeholder)

        documented(message)


def refused(
    receiving: Callable[[], object],
) -> str:
    """Return the message one receiving refuses with."""

    with pytest.raises(ReceiveRefusedError) as caught:
        receiving()

    return str(caught.value)


def test_the_receiving_refusals_are_documented() -> None:
    local = local_with_history()
    sent = bundle(local, PARENT)
    diverged = Instance()
    diverged.workflows.save(child())
    diverged.workflows.save(parent())
    diverged.workflows.save(parent("Counts differently."))
    other = Instance()
    other.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "9")))
    unreadable = first_record({"metadata": {"id": str(CHILD_ID)}})
    reread = counting_child()
    benchmark = bundle(charts(None), BENCHMARK)
    large = b"x" * (MAX_CONTENT_BYTES + 1)

    messages = {
        refused(lambda: received_by(diverged, sent)): {},
        refused(lambda: received_by(Bare(), PushBundle(revisions=(sent.revisions[-1],)))): {},
        refused(lambda: received_by(other, bundle(local, CHILD))): {},
        refused(lambda: received_by(Bare(), PushBundle(revisions=(unreadable,)))): {
            "Field required": "<ERROR>",
        },
        refused(lambda: received_by(Bare(), PushBundle(revisions=(reread,)))): {},
        refused(lambda: received_by(Bare(), benchmark)): {},
        refused(
            lambda: receive_content(
                InMemoryContentStore(),
                large,
                digest=content_bytes_digest(large),
                sensitivity=Sensitivity.INTERNAL,
                accepts_restricted=False,
            )
        ): {str(MAX_CONTENT_BYTES + 1): "<SIZE>"},
        refused(
            lambda: receive_content(
                InMemoryContentStore(),
                b"other",
                digest=CHART.digest,
                sensitivity=Sensitivity.INTERNAL,
                accepts_restricted=False,
            )
        ): {content_bytes_digest(b"other"): "<HELD>"},
        refused(lambda: received_by(Bare(), bundle(charts(Sensitivity.RESTRICTED), BENCHMARK))): {},
        refused(
            lambda: receive_content(
                InMemoryContentStore(),
                CHART_BYTES,
                digest=CHART.digest,
                sensitivity=Sensitivity.RESTRICTED,
                accepts_restricted=False,
            )
        ): {},
    }
    digests = {
        __version__: "<VERSION>",
        str(PARENT_ID): "<WORKFLOW_ID>",
        str(CHILD_ID): "<WORKFLOW_ID>",
        str(BENCHMARK_ID): "<BENCHMARK_ID>",
        diverged.workflows.lineage(PARENT_ID)[-1].revision_digest: "<LATEST>",
        sent.revisions[-1].revision_digest: "<DIGEST>",
        sent.revisions[-2].revision_digest: "<PARENT>",
        local.workflows.lineage(CHILD_ID)[0].revision_digest: "<DIGEST>",
        unreadable.revision_digest: "<DIGEST>",
        reread.revision_digest: "<DIGEST>",
        reread.content_digest: "<CONTENT_DIGEST>",
        json_digest(
            WorkflowSpecification.model_validate(reread.document).model_dump(mode="json")
        ): "<READ>",
        benchmark.revisions[0].revision_digest: "<DIGEST>",
        CHART.digest: "<CONTENT_DIGEST>",
        content_bytes_digest(large): "<CONTENT_DIGEST>",
    }

    assert len(messages) == 10

    for message, names in messages.items():
        for value, placeholder in {**names, **digests}.items():
            message = message.replace(value, placeholder)

        documented(message)


def counting_child() -> RevisionRecord:
    """Return a first revision of the child whose document this Azathoth reads as other content."""

    document = child().model_dump(mode="json")
    del document["steps"][0]["inputs"]

    return first_record(document)


def test_the_servers_refusal_of_unknown_tokens_is_documented() -> None:
    documented(UNKNOWN_TOKEN_MESSAGE)


def test_the_client_refusals_are_documented() -> None:
    unreachable = answering(502, b"<html>Bad gateway</html>")
    other = answering(200, b'{"status": "ok"}')
    url = CLIENT_URL
    messages: list[str] = []

    for asking in (unreachable.capabilities, other.capabilities):
        with pytest.raises(RemoteUnreachableError) as caught:
            asking()

        messages.append(
            str(caught.value)
            .replace(url, "<URL>")
            .replace("502", "<STATUS>")
            .replace("Capabilities", "<MODEL>")
        )

    with pytest.raises(ValueError) as refused:
        require_remote_url("ftp://example.com")

    messages.append(str(refused.value).replace("ftp://example.com", "<URL>"))
    messages.append(
        f"The remote at {url} could not be reached: Connection refused".replace(
            url, "<URL>"
        ).replace("Connection refused", "<REASON>")
    )

    for message in messages:
        documented(message)


def test_the_push_warnings_are_documented() -> None:
    messages = [
        missing_credential_warning(TOOL, "SEARCH_TOKEN")
        .replace(str(COUNT_ID), "<TOOL_ID>")
        .replace("1.0.0", "<VERSION>")
        .replace("SEARCH_TOKEN", "<NAME>"),
        *child_drift_warnings(
            running_child(),
            local_latest={CHILD_ID: B},
            remote_production={CHILD_ID: A},
        ),
        *child_drift_warnings(running_child(), local_latest={}, remote_production={}),
        *unapproved_model_warnings(prompting(), authorized={"bedrock/example/private"}),
    ]
    names = {
        str(CALL_STEP): "<STEP_ID>",
        str(PROMPT_STEP): "<STEP_ID>",
        f"workflow {CHILD_ID}": "workflow <CHILD_ID>",
        str(PARENT_ID): "<WORKFLOW_ID>",
        A: "<RUNNING>",
        B: "<LATEST>",
        "openrouter/example/frontier": "<MODEL>",
    }

    assert len(messages) == 4

    for message in messages:
        for value, placeholder in names.items():
            message = message.replace(value, placeholder)

        documented(message)
