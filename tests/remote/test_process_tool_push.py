"""Tests that a push carrying a process tool asks to import one (ADRs 0127 and 0134).

A process tool runs a command wherever it is used, and a remote's jobs use
what is pushed to it, so a push of one asks the policy for
`import_process_tool` as well as `push`, as importing one does.
"""

import json
from uuid import UUID

from azathoth.remote import Action, AuditEventKind, PushBundle
from azathoth.remote.receiving import process_tool_lineages
from azathoth.revisions import Lineage, RevisionKind
from azathoth.tools import ToolDocument
from tests.remote.asgi import call
from tests.remote.test_call_audit import protocol
from tests.remote.test_closure import Instance
from tests.remote.test_conditions import EXAMPLES, Refusing
from tests.remote.test_receiving import Bare, bundle
from tests.remote.test_service_routes import ListAudit

PROCESS = Lineage(
    kind=RevisionKind.TOOL,
    id=UUID("55555555-5555-5555-5555-555555555555"),
    version="1.0.0",
)

PYTHON = Lineage(
    kind=RevisionKind.TOOL,
    id=UUID("11111111-1111-1111-1111-111111111111"),
    version="1.0.0",
)


def tools(
    *names: str,
) -> Instance:
    """Return an instance holding the example tools of these file names."""

    local = Instance()

    for name in names:
        local.tools.save_document(
            ToolDocument.model_validate(json.loads((EXAMPLES / name).read_text()))
        )

    return local


def pushed(
    sent: PushBundle,
    *refused: Action,
) -> tuple[int, dict[str, object], Refusing, ListAudit, Bare]:
    """Push a bundle to a remote whose policy refuses some actions, and return what happened."""

    audit = ListAudit()
    policy = Refusing(*refused)
    app, held = protocol(audit, policy=policy)
    answer = call(app, "POST", "/v1/push", raw=sent.model_dump_json().encode())

    return answer.status, answer.json(), policy, audit, held


def test_the_process_tools_a_bundle_carries_are_named_once_in_order() -> None:
    local = tools("word-count.json", "word-count-process.json")
    sent = bundle(local, PYTHON, PROCESS)

    assert process_tool_lineages(sent) == (PROCESS,)
    assert process_tool_lineages(bundle(local, PYTHON)) == ()
    assert process_tool_lineages(PushBundle()) == ()


def test_a_push_carrying_a_process_tool_asks_to_import_one_and_is_refused_without_it() -> None:
    sent = bundle(tools("word-count-process.json"), PROCESS)
    status, answer, policy, audit, held = pushed(sent, Action.IMPORT_PROCESS_TOOL)

    assert status == 403
    assert answer == {"error": "laptop may not import process tool."}
    assert [(action, resource) for _, action, resource in policy.asked] == [
        (Action.PUSH, None),
        (Action.PUSH, str(PROCESS)),
        (Action.IMPORT_PROCESS_TOOL, str(PROCESS)),
    ]
    assert held.tools.document_lineage(PROCESS.id, "1.0.0") == ()
    assert [event.kind for event in audit.events] == [AuditEventKind.REQUEST_DENIED]


def test_a_push_carrying_a_process_tool_is_told_as_one_before_it_is_received() -> None:
    sent = bundle(tools("word-count-process.json"), PROCESS)
    status, _, _, audit, held = pushed(sent)

    assert status == 200
    assert [(event.kind, event.resource) for event in audit.events] == [
        (AuditEventKind.PUSH, str(PROCESS)),
        (AuditEventKind.PROCESS_TOOL_IMPORTED, str(PROCESS)),
    ]
    assert audit.events[1].detail == "push"
    assert len(held.tools.document_lineage(PROCESS.id, "1.0.0")) == 1


def test_a_push_carrying_no_process_tool_asks_only_to_push() -> None:
    sent = bundle(tools("word-count.json"), PYTHON)
    status, _, policy, audit, _ = pushed(sent, Action.IMPORT_PROCESS_TOOL)

    assert status == 200
    assert {action for _, action, _ in policy.asked} == {Action.PUSH}
    assert [event.kind for event in audit.events] == [AuditEventKind.PUSH]


def test_the_examples_hold_one_process_tool_and_one_that_is_not() -> None:
    def runtimes(
        name: str,
    ) -> list[str]:
        document = json.loads((EXAMPLES / name).read_text())

        return [each["runtime"] for each in document["implementations"]]

    assert runtimes("word-count.json") == ["python"]
    assert runtimes("word-count-process.json") == ["process"]
