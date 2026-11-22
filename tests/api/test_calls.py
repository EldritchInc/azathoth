"""Tests that every call of the service API names the actions a remote asks for it (ADR 0134)."""

import inspect
import re
import typing
from pathlib import Path

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
from azathoth.api.models import ExperimentComparison
from azathoth.remote import HIGH_PRIVILEGE_ACTIONS, Action, AuditEventKind

LIFECYCLE = frozenset({"close"})
"""What an instance has that is not a call: ending it."""

README = Path(__file__).parents[2] / "src" / "azathoth" / "api" / "README.md"

ALWAYS = re.compile(r"\bis the (`[a-z_]+`(?:(?:, | and )`[a-z_]+`)*) actions?\b(?! too)")
"""How a docstring names the actions its call always asks: `It is the `x` action`."""

CONDITION = re.compile(r"\b((?:for|when) [^`.;,]+?) the `([a-z_]+)` action too")
"""How a docstring names an action its call asks only sometimes: `for a … the `x` action too`."""

NEVER_SERVED = "A remote never serves it"
"""How a docstring says that its call is never served."""


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


def functions() -> dict[str, typing.Any]:
    """Return the function of every call an instance has, by its name."""

    found: dict[str, typing.Any] = {}

    for name, member in inspect.getmembers(Azathoth):
        if name.startswith("_") or name in LIFECYCLE:
            continue

        if isinstance(member, property):
            namespace = typing.get_type_hints(member.fget).get("return")

            if inspect.isclass(namespace):
                for method, function in inspect.getmembers(namespace, inspect.isfunction):
                    if not method.startswith("_"):
                        found[f"{name}.{method}"] = function
        elif inspect.isfunction(member):
            found[name] = member

    return found


def docstring(
    call: ServiceCall,
) -> str:
    """Return a call's docstring as one line."""

    return " ".join((inspect.getdoc(functions()[call.name]) or "").split())


def actions_named(
    text: str,
) -> list[Action]:
    return [Action(name) for name in re.findall(r"`([a-z_]+)`", text)]


def readme_rows() -> dict[str, list[str]]:
    """Return the cells of each row of the README's Actions table, by call."""

    section = README.read_text(encoding="utf-8").split("\n## Actions\n", 1)[1].split("\n## ")[0]
    rows: dict[str, list[str]] = {}

    for line in section.split("\n"):
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[cells[0].strip("`")] = cells[1:]

    return rows


def readme_cells(
    call: ServiceCall,
) -> list[str]:
    """Return the cells the README's Actions table holds for a call."""

    if not call.served:
        return ["never served", "", ""]

    return [
        ", ".join(f"`{action}`" for action in call.actions),
        "; ".join(f"`{condition.action}` {condition.when}" for condition in call.also),
        ", ".join(f"`{kind}`" for kind in call.audit),
    ]


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


def test_only_mcp_tools_and_installing_standard_tools_always_ask_high_privilege() -> None:
    always = {
        call.name: set(call.actions) & HIGH_PRIVILEGE_ACTIONS
        for call in SERVICE_CALLS
        if set(call.actions) & HIGH_PRIVILEGE_ACTIONS
    }

    assert always == {
        "tools.from_mcp": {Action.TOOL_FROM_MCP},
        "tools.install_standard": {Action.INSTALL_STANDARD_TOOLS},
    }


def test_importing_a_process_tool_asks_for_both_import_actions() -> None:
    call = service_call("tools.import_document")

    assert call.actions == (Action.IMPORT_TOOL,)
    assert call.also == (Condition(action=Action.IMPORT_PROCESS_TOOL, when="for a process tool"),)
    assert call.audit == (AuditEventKind.TOOL_IMPORTED, AuditEventKind.PROCESS_TOOL_IMPORTED)


def test_every_action_but_the_protocols_and_managing_tokens_has_a_call() -> None:
    asked = set().union(*(every_action_asked(call) for call in SERVICE_CALLS))

    assert {action for action in Action if action not in asked} == {
        Action.PUSH,
        Action.PULL,
        Action.READ_CONTENT,
        Action.MANAGE_TOKENS,
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


# Docstrings and the README say what the list says


def test_every_served_calls_docstring_names_the_actions_it_always_asks() -> None:
    for call in SERVICE_CALLS:
        if call.served:
            named = ALWAYS.findall(docstring(call))

            assert len(named) == 1, (call.name, named)
            assert actions_named(named[0]) == list(call.actions), call.name


def test_every_served_calls_docstring_names_when_it_asks_more() -> None:
    for call in SERVICE_CALLS:
        if call.served:
            named = [
                Condition(action=Action(action), when=when)
                for when, action in CONDITION.findall(docstring(call))
            ]

            assert named == list(call.also), call.name


def test_a_call_never_served_says_so() -> None:
    for call in SERVICE_CALLS:
        text = docstring(call)

        assert (NEVER_SERVED in text) is not call.served, call.name

        if not call.served:
            assert ALWAYS.findall(text) == [], call.name


def test_the_readme_lists_every_call_once_with_what_the_list_says() -> None:
    rows = readme_rows()

    assert list(rows) == [call.name for call in SERVICE_CALLS]

    for call in SERVICE_CALLS:
        assert rows[call.name] == readme_cells(call), call.name


def test_an_experiments_own_cost_is_read_with_its_runs_and_only_spend_reports_read_spend() -> None:
    reads_spend = [
        call.name for call in SERVICE_CALLS if Action.READ_SPEND in every_action_asked(call)
    ]

    assert service_call("experiments.get").actions == (Action.READ_RUNS,)
    assert service_call("experiments.compare").actions == (Action.READ_RUNS,)
    assert {"winner_runs", "baseline_runs", "savings"} <= set(ExperimentComparison.model_fields)
    assert reads_spend == ["spend.report"]
