"""Tests that the remote package's README quotes its messages exactly (ADR 0124)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.remote import (
    Action,
    OwnerOnlyPolicy,
    Principal,
    ProtocolMismatchError,
    RemotePluginError,
    require_protocol,
)
from azathoth.revisions import Lineage, RevisionKind, content_digest, revision_digest
from tests.remote.test_closure import (
    CALL_STEP,
    CHILD,
    CHILD_ID,
    PARENT_ID,
    SUMMARIZE_STEP,
    Instance,
    StaleWorkflows,
    call,
    child,
    specification,
    tool_step,
)
from tests.remote.test_records import WORKFLOW_ID, record, tampered
from tests.remote.test_records import specification as counting
from tests.remote.test_seams import Installed, TeamPolicy, default

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
