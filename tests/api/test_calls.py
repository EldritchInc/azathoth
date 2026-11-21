"""Tests that every call of the service API names the actions a remote asks for it (ADR 0134)."""

import inspect
import typing

import pytest

from azathoth import api
from azathoth.api.calls import (
    SERVICE_CALLS,
    Condition,
    Resource,
    ServiceCall,
    service_call,
)
from azathoth.api.instance import Azathoth
from azathoth.remote import HIGH_PRIVILEGE_ACTIONS, Action, AuditEventKind

LIFECYCLE = frozenset({"close"})
"""What an instance has that is not a call: ending it."""


def calls_by_inspection() -> dict[str, inspect.Signature]:
    """Return every call an instance has, as `namespace.method` or `method`, with its signature."""

    found: dict[str, inspect.Signature] = {}

    for name, member in inspect.getmembers(Azathoth):
        if name.startswith("_") or name in LIFECYCLE:
            continue

        if isinstance(member, property):
            namespace = typing.get_type_hints(member.fget).get("return")

            if not inspect.isclass(namespace):
                continue

            for method, function in inspect.getmembers(namespace, inspect.isfunction):
                if not method.startswith("_"):
                    found[f"{name}.{method}"] = inspect.signature(function)
        elif inspect.isfunction(member):
            found[name] = inspect.signature(member)

    return found


def every_action_asked(
    call: ServiceCall,
) -> set[Action]:
    return set(call.actions) | {condition.action for condition in call.also}


# Complete and unique


def test_every_call_of_an_instance_is_listed_and_nothing_else() -> None:
    assert sorted(call.name for call in SERVICE_CALLS) == sorted(calls_by_inspection())


def test_each_call_is_listed_once() -> None:
    names = [call.name for call in SERVICE_CALLS]

    assert len(names) == len(set(names))


def test_a_call_is_found_by_its_name() -> None:
    assert service_call("workflows.get") == ServiceCall(
        name="workflows.get",
        actions=(Action.READ_CATALOG,),
        resource=Resource(kind="workflow", parameter="workflow_id"),
    )

    with pytest.raises(LookupError) as caught:
        service_call("workflows.delete")

    assert str(caught.value) == "The service API has no call named 'workflows.delete'."


def test_the_list_is_part_of_the_service_api() -> None:
    assert api.SERVICE_CALLS is SERVICE_CALLS
    assert api.service_call is service_call


# What each call names


def test_a_resource_is_named_by_a_parameter_of_its_call() -> None:
    signatures = calls_by_inspection()

    for call in SERVICE_CALLS:
        if call.resource is not None:
            assert call.resource.parameter in signatures[call.name].parameters, call.name


def test_a_served_call_asks_for_an_action_and_a_local_one_for_none() -> None:
    for call in SERVICE_CALLS:
        if call.served:
            assert call.actions, call.name
        else:
            assert call.actions == () and call.also == () and call.audit == (), call.name


def test_only_the_calls_that_name_other_remotes_are_never_served() -> None:
    assert sorted(call.name for call in SERVICE_CALLS if not call.served) == [
        "remote",
        "remotes.add",
        "remotes.get",
        "remotes.list",
        "remotes.remove",
    ]


def test_what_a_call_tells_the_audit_records_an_action_it_asks() -> None:
    for call in SERVICE_CALLS:
        for kind in call.audit:
            assert kind.action in every_action_asked(call), (call.name, kind)


def test_reading_restricted_data_is_always_told_to_the_audit() -> None:
    for call in SERVICE_CALLS:
        if Action.READ_RESTRICTED in every_action_asked(call):
            assert AuditEventKind.RESTRICTED_READ in call.audit, call.name


def test_a_condition_says_when_it_holds() -> None:
    for call in SERVICE_CALLS:
        for condition in call.also:
            assert condition.when.startswith(("for ", "when ")), (call.name, condition)
            assert condition.action not in call.actions, (call.name, condition)


def test_restricted_data_is_only_ever_asked_for_when_a_call_would_show_some() -> None:
    for call in SERVICE_CALLS:
        assert Action.READ_RESTRICTED not in call.actions, call.name


def test_no_call_but_making_a_tool_from_mcp_asks_a_high_privilege_action_every_time() -> None:
    always = {
        call.name: set(call.actions) & HIGH_PRIVILEGE_ACTIONS
        for call in SERVICE_CALLS
        if set(call.actions) & HIGH_PRIVILEGE_ACTIONS
    }

    assert always == {"tools.from_mcp": {Action.TOOL_FROM_MCP}}


def test_importing_a_process_tool_asks_for_both_import_actions() -> None:
    call = service_call("tools.import_document")

    assert call.actions == (Action.IMPORT_TOOL,)
    assert call.also == (Condition(action=Action.IMPORT_PROCESS_TOOL, when="for a process tool"),)
    assert call.audit == (AuditEventKind.TOOL_IMPORTED, AuditEventKind.PROCESS_TOOL_IMPORTED)


def test_every_action_but_the_protocols_and_installing_standard_tools_has_a_call() -> None:
    asked = set().union(*(every_action_asked(call) for call in SERVICE_CALLS))

    assert {action for action in Action if action not in asked} == {
        Action.PUSH,
        Action.PULL,
        Action.READ_CONTENT,
        Action.MANAGE_TOKENS,
        Action.INSTALL_STANDARD_TOOLS,
    }


def test_a_listing_names_the_kind_of_resource_it_returns() -> None:
    listings = {call.name: call.lists for call in SERVICE_CALLS if call.lists is not None}

    assert listings == {
        "workflows.list": "workflow",
        "tools.list": "tool",
        "tools.versions": "tool",
        "benchmarks.list": "benchmark",
        "goals.list": "goal",
        "runs.list": "run",
        "runs.interrupted": "run",
        "invocations.list": "invocation",
        "experiments.list": "experiment",
        "benchmarks.executions": "execution",
    }
