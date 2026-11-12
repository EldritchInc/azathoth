"""Tests that a push warns of what would stop its documents running at the remote (ADR 0125)."""

from pathlib import Path

import httpx

from azathoth.providers import ModelPortfolioEntry
from azathoth.remote import PushReport, RemoteClient, missing_credential_warning, push_to
from azathoth.revisions import Lineage
from azathoth.tools import ToolDocument
from azathoth.workflows import WorkflowProductionState
from tests.remote.test_client import URL, client_of
from tests.remote.test_closure import (
    CALL_STEP,
    CHILD,
    CHILD_ID,
    COUNT,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    SUMMARIZE_STEP,
    Instance,
    call,
    child,
    parent,
    specification,
    tool_step,
)
from tests.remote.test_server import Remote
from tests.remote.test_status import (
    PROMPT_STEP,
    mcp_implementation,
    process_implementation,
    prompting,
)
from tests.tools.test_catalog import create_tool_definition


def pushed(
    local: Instance,
    remote: Remote,
    *roots: Lineage,
) -> PushReport:
    return push_to(
        client_of(remote),
        roots,
        workflows=local.workflows,
        tools=local.tools,
        benchmarks=local.benchmarks,
        content=local.content,
    )


def with_credentials(
    local: Instance,
) -> Instance:
    """Give the word-count tool implementations that need credentials."""

    local.tools.save_document(
        ToolDocument(
            definition=create_tool_definition(tool_id=COUNT_ID, name="word_count"),
            implementations=(
                process_implementation("SEARCH_TOKEN", "AWS_*"),
                mcp_implementation("WIKI_TOKEN"),
            ),
        )
    )

    return local


def test_a_clean_push_warns_of_nothing(
    tmp_path: Path,
) -> None:
    local = Instance()
    local.workflows.save(child())

    assert pushed(local, Remote(tmp_path), CHILD).warnings == ()


# Credentials


def test_a_credential_the_remote_does_not_set_is_warned_of(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path, environ={"AWS_REGION": "us-east-1", "WIKI_TOKEN": "s3cret"})

    report = pushed(with_credentials(Instance()), remote, COUNT)

    assert report.warnings == (missing_credential_warning(COUNT, "SEARCH_TOKEN"),)


def test_credentials_the_remote_sets_are_not_warned_of(
    tmp_path: Path,
) -> None:
    remote = Remote(
        tmp_path,
        environ={"AWS_REGION": "us-east-1", "WIKI_TOKEN": "s3cret", "SEARCH_TOKEN": "s3cret"},
    )

    assert pushed(with_credentials(Instance()), remote, COUNT).warnings == ()


def test_each_credential_a_pushed_workflows_tools_need_is_checked(
    tmp_path: Path,
) -> None:
    local = with_credentials(Instance())
    local.workflows.save(specification(PARENT_ID, tool_step(SUMMARIZE_STEP, "word_count", "1.0.0")))

    report = pushed(local, Remote(tmp_path), PARENT)

    assert report.warnings == (
        missing_credential_warning(COUNT, "SEARCH_TOKEN"),
        missing_credential_warning(COUNT, "AWS_*"),
        missing_credential_warning(COUNT, "WIKI_TOKEN"),
    )


# Child workflows


def test_a_child_not_in_production_at_the_remote_is_warned_of(
    tmp_path: Path,
) -> None:
    local = Instance()
    local.workflows.save(child())
    local.workflows.save(parent())

    report = pushed(local, Remote(tmp_path), PARENT)

    assert report.warnings == (
        f"Step {CALL_STEP} of workflow {PARENT_ID} runs workflow {CHILD_ID}, which is not in "
        "production at the remote; it cannot run there until the child is promoted.",
    )


def test_a_child_in_production_at_another_revision_is_warned_of(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    revision = theirs.workflows.revision(CHILD_ID, 1)

    assert revision is not None

    theirs.production_states.set(
        WorkflowProductionState(specification=revision.specification, specification_revision=1)
    )
    local = Instance()
    local.workflows.save(child())
    local.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "summarize", "2")))
    local.workflows.save(parent())
    history = local.workflows.lineage(CHILD_ID)

    report = pushed(local, Remote(tmp_path, held=theirs), PARENT)

    assert report.warnings == (
        f"Step {CALL_STEP} of workflow {PARENT_ID} runs workflow {CHILD_ID}, which is in "
        f"production at the remote as revision {history[0].revision_digest}, not "
        f"{history[1].revision_digest}, the latest here.",
    )


def test_a_child_in_production_at_the_latest_revision_is_not_warned_of(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    revision = theirs.workflows.revision(CHILD_ID, 1)

    assert revision is not None

    theirs.production_states.set(
        WorkflowProductionState(specification=revision.specification, specification_revision=1)
    )
    local = Instance()
    local.workflows.save(child())
    local.workflows.save(parent())

    assert pushed(local, Remote(tmp_path, held=theirs), PARENT).warnings == ()


# Models


def test_a_fixed_model_the_remote_has_not_authorized_is_warned_of(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.portfolio.save(ModelPortfolioEntry(provider="bedrock", model="example/private"))
    local = Instance()
    local.workflows.save(prompting())

    report = pushed(local, Remote(tmp_path, held=theirs), PARENT)

    assert report.warnings == (
        f"Step {PROMPT_STEP} of workflow {PARENT_ID} uses model openrouter/example/frontier, "
        "which the remote has not authorized; it cannot run there until the remote's portfolio "
        "holds it.",
    )


def test_warnings_come_credentials_first_then_children_then_models(
    tmp_path: Path,
) -> None:
    local = with_credentials(Instance())
    local.workflows.save(child())
    local.workflows.save(
        prompting().model_copy(
            update={
                "steps": (
                    *prompting().steps[:1],
                    tool_step(SUMMARIZE_STEP, "word_count", "1.0.0"),
                    *parent().steps[1:],
                )
            }
        )
    )

    warnings = pushed(local, Remote(tmp_path), PARENT).warnings

    assert [warning.split(" ")[0] for warning in warnings] == [
        "Tool",
        "Tool",
        "Tool",
        "Step",
        "Step",
    ]
    assert "not in production at the remote" in warnings[3]
    assert "has not authorized" in warnings[4]


def test_a_push_needing_no_check_asks_the_remote_nothing_more(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)
    asked: list[str] = []

    def recorded(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        answered = remote.client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=dict(request.headers),
        )

        return httpx.Response(answered.status_code, content=answered.content)

    local = Instance()
    local.workflows.save(specification(CHILD_ID, tool_step(SUMMARIZE_STEP, "word_count", "1.0.0")))

    report = push_to(
        RemoteClient(
            URL,
            remote.token,
            http=httpx.Client(base_url=URL, transport=httpx.MockTransport(recorded)),
        ),
        (CHILD,),
        workflows=local.workflows,
        tools=local.tools,
        benchmarks=local.benchmarks,
        content=local.content,
    )

    assert report.warnings == ()
    assert asked == ["/v1/capabilities", "/v1/missing", "/v1/push"]


def test_a_child_named_only_when_its_step_runs_is_not_checked(
    tmp_path: Path,
) -> None:
    local = Instance()
    local.workflows.save(
        specification(PARENT_ID, tool_step(CALL_STEP, "run_workflow", "1.0.0", call("later")))
    )

    assert pushed(local, Remote(tmp_path), PARENT).warnings == ()
