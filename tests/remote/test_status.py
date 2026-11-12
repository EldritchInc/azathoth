"""Tests for how a lineage here relates to it at a remote, and push warnings (ADR 0125)."""

import sys
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptStrategySpec,
    PromptTemplate,
)
from azathoth.providers import ModelRequirements, Prompt
from azathoth.remote import (
    ComponentStatus,
    ModelStatus,
    Relation,
    RemoteStatus,
    child_drift_warnings,
    credential_names,
    fixed_models,
    missing_credential_warning,
    relation,
    unapproved_model_warnings,
)
from azathoth.revisions import Lineage, RevisionKind
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    MCP_TOOL_RUNTIME,
    PROCESS_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    ToolDocument,
    ToolImplementation,
    mcp_schema_digest,
)
from azathoth.workflows import WorkflowSpecification, WorkflowStepSpecification
from tests.remote.test_closure import (
    CALL_STEP,
    CHILD_ID,
    COUNT_ID,
    COUNT_STEP,
    PARENT_ID,
    SUMMARIZE_STEP,
    call,
    parent,
    specification,
    tool_step,
)
from tests.tools.test_catalog import create_tool_definition

A, B, C = ("a" * 64, "b" * 64, "c" * 64)

TOOL = Lineage(kind=RevisionKind.TOOL, id=COUNT_ID, version="1.0.0")

FIXED = FixedModelSelection(provider="openrouter", model="example/frontier")

PROMPT_STEP = UUID("5a700000-0000-4000-8000-000000000041")

CONTEXT_STEP = UUID("5a700000-0000-4000-8000-000000000042")

CHOSEN_STEP = UUID("5a700000-0000-4000-8000-000000000043")


# Relations


@pytest.mark.parametrize(
    ("local", "remote", "expected"),
    [
        ((A, B), (A, B), Relation.IN_SYNC),
        ((A, B, C), (A, B), Relation.AHEAD),
        ((A,), (A, B), Relation.BEHIND),
        ((A, B), (A, C), Relation.DIVERGED),
        ((A,), (C,), Relation.DIVERGED),
        ((A, B), (), Relation.LOCAL_ONLY),
        ((), (A,), Relation.REMOTE_ONLY),
    ],
    ids=[
        "in-sync",
        "ahead",
        "behind",
        "diverged",
        "other-history",
        "local-only",
        "remote-only",
    ],
)
def test_a_lineage_relates_as_its_chains_do(
    local: tuple[str, ...],
    remote: tuple[str, ...],
    expected: Relation,
) -> None:
    assert relation(local, remote) is expected


def test_a_lineage_neither_side_holds_has_no_relation() -> None:
    with pytest.raises(ValueError) as caught:
        relation((), ())

    assert str(caught.value) == "Neither side holds a revision of the lineage."


def test_the_relations_are_named() -> None:
    assert [value.value for value in Relation] == [
        "in_sync",
        "ahead",
        "behind",
        "diverged",
        "local_only",
        "remote_only",
    ]


def test_a_status_says_what_it_does_not_know() -> None:
    status = RemoteStatus(
        remote="https://azathoth.example.com",
        reachable=False,
        components=(ComponentStatus(lineage=TOOL, relation=Relation.LOCAL_ONLY),),
        models=(ModelStatus(identifier=FIXED.identifier, authorized_locally=True),),
    )

    (component,) = status.components
    (model,) = status.models

    assert (component.remote_digest, component.remote_production_digest) == (None, None)
    assert model.authorized_remotely is None
    assert status.portfolio_synced_at is None
    assert RemoteStatus.model_validate_json(status.model_dump_json()) == status

    with pytest.raises(ValidationError):
        ComponentStatus.model_validate({"lineage": TOOL.model_dump(), "relation": "sideways"})


# Credentials


def process_implementation(
    *environment: str,
) -> ToolImplementation:
    return ToolImplementation(
        id=UUID(int=11),
        tool_id=COUNT_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source="print('hello')",
        command=(sys.executable,),
        environment=environment,
    )


def mcp_implementation(
    authorization: str | None,
) -> ToolImplementation:
    return ToolImplementation(
        id=UUID(int=12),
        tool_id=COUNT_ID,
        tool_version="1.0.0",
        runtime=MCP_TOOL_RUNTIME,
        mcp=McpToolBinding(
            server=McpServer(url="https://mcp.example.com/mcp"),
            tool="search",
            schema_digest=mcp_schema_digest({"type": "object"}, None),
            credentials=McpCredentials(authorization=authorization),
        ),
    )


def test_a_tools_credentials_are_its_grants_and_its_authorization_each_once() -> None:
    document = ToolDocument(
        definition=create_tool_definition(tool_id=COUNT_ID),
        implementations=(
            process_implementation("SEARCH_TOKEN", "AWS_*"),
            mcp_implementation("SEARCH_TOKEN"),
        ),
    )

    assert credential_names(document) == ("SEARCH_TOKEN", "AWS_*")


def test_a_tool_needing_nothing_names_nothing() -> None:
    assert credential_names(ToolDocument(definition=create_tool_definition())) == ()
    assert (
        credential_names(
            ToolDocument(
                definition=create_tool_definition(tool_id=COUNT_ID),
                implementations=(mcp_implementation(None), process_implementation()),
            )
        )
        == ()
    )


def test_a_missing_credential_is_warned_of() -> None:
    assert missing_credential_warning(TOOL, "SEARCH_TOKEN") == (
        f"Tool {COUNT_ID}@1.0.0 needs SEARCH_TOKEN, which is not set at the remote; its steps "
        "fail there until it is."
    )


# Child drift


def running_child() -> WorkflowSpecification:
    return parent()


def test_a_child_in_production_at_the_latest_revision_is_not_drift() -> None:
    assert (
        child_drift_warnings(
            running_child(),
            local_latest={CHILD_ID: A},
            remote_production={CHILD_ID: A},
        )
        == ()
    )


def test_a_child_in_production_at_another_revision_is_drift() -> None:
    assert child_drift_warnings(
        running_child(),
        local_latest={CHILD_ID: B},
        remote_production={CHILD_ID: A},
    ) == (
        f"Step {CALL_STEP} of workflow {PARENT_ID} runs workflow {CHILD_ID}, which is in "
        f"production at the remote as revision {A}, not {B}, the latest here.",
    )


def test_a_child_not_in_production_at_the_remote_cannot_run_there() -> None:
    expected = (
        f"Step {CALL_STEP} of workflow {PARENT_ID} runs workflow {CHILD_ID}, which is not in "
        "production at the remote; it cannot run there until the child is promoted.",
    )

    for production in ({}, {CHILD_ID: None}):
        assert (
            child_drift_warnings(
                running_child(),
                local_latest={CHILD_ID: B},
                remote_production=production,
            )
            == expected
        )


def test_a_child_not_held_here_is_drift_only_when_it_is_not_running_there() -> None:
    assert (
        child_drift_warnings(
            running_child(),
            local_latest={},
            remote_production={CHILD_ID: A},
        )
        == ()
    )


def test_a_child_named_only_when_its_step_runs_is_not_checked() -> None:
    later = specification(
        PARENT_ID,
        tool_step(CALL_STEP, "run_workflow", "1.0.0", call("named later")),
        tool_step(COUNT_STEP, "word_count", "1.0.0"),
    )

    assert child_drift_warnings(later, local_latest={}, remote_production={}) == ()


# Models


def prompting() -> WorkflowSpecification:
    def metadata(step_id: UUID) -> StrategyMetadata:
        return StrategyMetadata(
            id=UUID(int=step_id.int + 1),
            name="prompt",
            description="Prompt.",
            version="1.0.0",
        )

    return specification(
        PARENT_ID,
        WorkflowStepSpecification(
            id=PROMPT_STEP,
            specification=PromptStrategySpec(
                metadata=metadata(PROMPT_STEP),
                prompt=Prompt(text="Say hello."),
                model_selection=FIXED,
            ),
        ),
        WorkflowStepSpecification(
            id=CONTEXT_STEP,
            specification=ContextPromptStrategySpec(
                metadata=metadata(CONTEXT_STEP),
                template=PromptTemplate(
                    text="Summarize: {claim}",
                    bindings=(
                        PromptBinding(
                            variable_name="claim",
                            event_type="workflow.input.received",
                            field_name="input",
                        ),
                    ),
                ),
                model_selection=FixedModelSelection(provider="bedrock", model="example/private"),
            ),
        ),
        WorkflowStepSpecification(
            id=CHOSEN_STEP,
            specification=PromptStrategySpec(
                metadata=metadata(CHOSEN_STEP),
                prompt=Prompt(text="Say goodbye."),
                model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
            ),
        ),
        tool_step(SUMMARIZE_STEP, "summarize"),
    )


def test_the_models_steps_fix_are_named_and_others_are_not() -> None:
    assert list(fixed_models(prompting())) == [
        (PROMPT_STEP, "openrouter/example/frontier"),
        (CONTEXT_STEP, "bedrock/example/private"),
    ]


def test_a_fixed_model_the_remote_has_not_authorized_is_warned_of() -> None:
    assert unapproved_model_warnings(
        prompting(),
        authorized={"bedrock/example/private"},
    ) == (
        f"Step {PROMPT_STEP} of workflow {PARENT_ID} uses model openrouter/example/frontier, "
        "which the remote has not authorized; it cannot run there until the remote's portfolio "
        "holds it.",
    )
    assert (
        unapproved_model_warnings(
            prompting(),
            authorized={"bedrock/example/private", "openrouter/example/frontier"},
        )
        == ()
    )
