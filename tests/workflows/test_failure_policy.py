"""Tests for workflow failure policies."""

from azathoth.workflows import WorkflowFailurePolicy


def test_failure_policy_values_are_stable() -> None:
    assert WorkflowFailurePolicy.FAIL_WORKFLOW.value == "fail_workflow"
    assert WorkflowFailurePolicy.CONTINUE.value == "continue"
    assert WorkflowFailurePolicy.SKIP_DEPENDENTS.value == "skip_dependents"


def test_failure_policy_is_string_compatible() -> None:
    assert str(WorkflowFailurePolicy.FAIL_WORKFLOW) == "fail_workflow"

    assert str(WorkflowFailurePolicy.CONTINUE) == "continue"


def test_failure_policy_round_trips_from_serialized_values() -> None:
    assert WorkflowFailurePolicy("fail_workflow") is WorkflowFailurePolicy.FAIL_WORKFLOW
    assert WorkflowFailurePolicy("continue") is WorkflowFailurePolicy.CONTINUE
    assert WorkflowFailurePolicy("skip_dependents") is WorkflowFailurePolicy.SKIP_DEPENDENTS


def test_failure_policies_are_distinct() -> None:
    policies = {
        WorkflowFailurePolicy.FAIL_WORKFLOW,
        WorkflowFailurePolicy.CONTINUE,
        WorkflowFailurePolicy.SKIP_DEPENDENTS,
    }

    assert len(policies) == 3
