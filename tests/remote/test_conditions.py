"""Tests that a call asks its policy for more when the catalog says it does (ADRs 0127 and 0134)."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from azathoth.api.calls import SERVICE_CALLS
from azathoth.remote import Action, Decision, Principal
from azathoth.remote.conditions import CONDITION_CHECKS, condition_checks
from azathoth.sensitivity import Sensitivity
from tests.remote.test_call_routes import ERIS, Asking, Served

EXAMPLES = Path(__file__).parents[2] / "examples" / "tools"

MISSING = UUID("c1080000-0000-4000-8000-000000000001")

READS = frozenset(
    {Action.READ_CAPABILITIES, Action.READ_CATALOG, Action.READ_RUNS, Action.READ_PORTFOLIO}
)
"""The actions of a call that only reads."""


class Refusing(Asking):
    """A policy that lets the owner do everything but what it is told to refuse."""

    def __init__(
        self,
        *refused: Action,
    ) -> None:
        super().__init__()
        self.refused = frozenset(refused)

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        super().decide(principal, action, resource)

        if action in self.refused:
            return Decision(allowed=False, reason=f"{principal.name} may not {action.description}.")

        return Decision(allowed=True)


class Remote:
    """One remote's database, served to Eris under whichever policy a test gives."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path
        self.everything = self.served()

    def served(
        self,
        *refused: Action,
    ) -> Served:
        return Served(self.path, principal=ERIS, policy=Refusing(*refused))


@pytest.fixture
def remote(
    tmp_path: Path,
) -> Iterator[Remote]:
    yield Remote(tmp_path / "azathoth.db")


def asked(
    served: Served,
) -> list[Action]:
    return [action for _, action, _ in served.policy.asked]


def benchmark_with_a_case(
    served: Served,
    sensitivity: Sensitivity | None,
) -> str:
    """Create a benchmark through the remote, give it one case, and return its ID."""

    created = served.call("benchmarks.create", {"name": "charts", "description": "Charts."})
    benchmark_id: str = created.json()["benchmark"]["id"]
    added = served.call(
        "benchmarks.add_case",
        {
            "benchmark_id": benchmark_id,
            "input": {"payload": {"chart": "412"}},
            "comparison": "exact",
            "expected": "fine",
            "sensitivity": None if sensitivity is None else sensitivity.value,
        },
    )

    assert added.status == 200, added.json()

    return benchmark_id


# The checks


def test_every_condition_the_catalog_names_is_checked_once() -> None:
    named = sorted((call.name, condition.when) for call in SERVICE_CALLS for condition in call.also)
    checked = sorted((check.call, check.condition.when) for check in CONDITION_CHECKS)

    assert checked == named


def test_each_check_is_told_one_way_before_or_after() -> None:
    for check in CONDITION_CHECKS:
        assert (check.before is None) != (check.after is None), check.call


def test_a_call_that_changes_something_is_only_ever_checked_before_it_runs() -> None:
    calls = {call.name: call for call in SERVICE_CALLS}

    for check in CONDITION_CHECKS:
        if not set(calls[check.call].actions) <= READS:
            assert check.before is not None, check.call


def test_a_calls_checks_are_in_the_order_the_catalog_names_them() -> None:
    (from_a_run, from_a_restricted_run) = condition_checks("benchmarks.add_case")

    assert from_a_run.condition.action is Action.READ_RUNS
    assert from_a_restricted_run.condition.action is Action.READ_RESTRICTED
    assert condition_checks("workflows.get") == ()


@pytest.mark.parametrize(
    ("result", "restricted"),
    [
        (SimpleNamespace(sensitivity=Sensitivity.RESTRICTED), True),
        (SimpleNamespace(sensitivity=Sensitivity.INTERNAL), False),
        (SimpleNamespace(sensitivity=None), False),
        (SimpleNamespace(), False),
    ],
)
def test_a_result_read_is_restricted_only_when_it_is_labelled_so(
    result: Any,
    restricted: bool,
) -> None:
    (check,) = condition_checks("runs.get")

    assert check.after is not None
    assert check.after({}, result) is restricted


# Importing a process tool


def test_importing_a_process_tool_asks_for_import_process_tool_before_it_saves_anything(
    remote: Remote,
) -> None:
    served = remote.served(Action.IMPORT_PROCESS_TOOL)
    document = (EXAMPLES / "word-count-process.json").read_text()
    answer = served.call("tools.import_document", {"document": document})

    assert answer.status == 403
    assert answer.json()["error"] == "Eris may not import process tool."
    assert asked(served) == [Action.IMPORT_TOOL, Action.IMPORT_PROCESS_TOOL]
    assert remote.everything.call("tools.list").json() == []


def test_importing_a_tool_that_runs_no_process_asks_only_for_import_tool(
    remote: Remote,
) -> None:
    served = remote.served(Action.IMPORT_PROCESS_TOOL)
    document = json.loads((EXAMPLES / "word-count.json").read_text())
    answer = served.call("tools.import_document", {"document": document})

    assert answer.status == 200
    assert asked(served) == [Action.IMPORT_TOOL]


def test_a_document_that_is_no_tool_is_refused_by_the_call_itself(
    remote: Remote,
) -> None:
    served = remote.served()
    answer = served.call("tools.import_document", {"document": "not a tool"})

    assert (answer.status, answer.json()["code"]) == (422, "invalid_document")
    assert asked(served) == [Action.IMPORT_TOOL]


# Reading restricted benchmarks and cases


def test_a_restricted_benchmark_is_sent_only_to_a_caller_who_may_read_restricted_data(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, Sensitivity.RESTRICTED)
    refused = remote.served(Action.READ_RESTRICTED)
    answer = refused.call("benchmarks.get", {"benchmark_id": benchmark_id})

    assert answer.status == 403
    assert answer.json() == {
        "error": "Eris may not read restricted data.",
        "code": "permission_denied",
    }
    assert "412" not in answer.body.decode()
    assert asked(refused) == [Action.READ_CATALOG, Action.READ_RESTRICTED]

    allowed = remote.served()

    assert allowed.call("benchmarks.get", {"benchmark_id": benchmark_id}).status == 200
    assert allowed.call("benchmarks.export", {"benchmark_id": benchmark_id}).status == 200


def test_a_benchmark_that_is_not_restricted_asks_for_nothing_more(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, None)
    served = remote.served(Action.READ_RESTRICTED)

    assert served.call("benchmarks.get", {"benchmark_id": benchmark_id}).status == 200
    assert served.call("benchmarks.export", {"benchmark_id": benchmark_id}).status == 200
    assert Action.READ_RESTRICTED not in asked(served)


def test_a_restricted_case_is_sent_only_to_a_caller_who_may_read_restricted_data(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, Sensitivity.RESTRICTED)
    (case,) = remote.everything.call("benchmarks.cases", {"benchmark_id": benchmark_id}).json()
    arguments = {"benchmark_id": benchmark_id, "case_id": case["case_id"]}

    refused = remote.served(Action.READ_RESTRICTED).call("benchmarks.case", arguments)

    assert refused.status == 403
    assert "412" not in refused.body.decode()
    assert remote.served().call("benchmarks.case", arguments).status == 200


def test_comparing_revisions_with_a_restricted_case_asks_before_telling_its_values(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, Sensitivity.RESTRICTED)
    compared = {"benchmark_id": benchmark_id, "before": 1, "after": 2}
    served = remote.served(Action.READ_RESTRICTED)

    told = served.call("benchmarks.compare_revisions", compared)
    withheld = served.call(
        "benchmarks.compare_revisions",
        {**compared, "include_restricted": False},
    )

    assert told.status == 403
    assert withheld.status == 200
    assert any(change["withheld"] for change in withheld.json()["changes"])
    assert asked(served) == [Action.READ_CATALOG, Action.READ_RESTRICTED, Action.READ_CATALOG]
    assert remote.served().call("benchmarks.compare_revisions", compared).status == 200


def test_comparing_revisions_with_nothing_restricted_asks_for_nothing_more(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, None)
    served = remote.served(Action.READ_RESTRICTED)
    compared = {"benchmark_id": benchmark_id, "before": 1, "after": 2}

    assert served.call("benchmarks.compare_revisions", compared).status == 200
    assert asked(served) == [Action.READ_CATALOG]


# Cases made from runs, and promotions from experiments


def test_a_case_made_from_a_run_asks_to_read_runs_before_the_run_is_read(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, None)
    served = remote.served(Action.READ_RUNS)
    answer = served.call(
        "benchmarks.add_case",
        {"benchmark_id": benchmark_id, "run_id": str(MISSING), "comparison": "exact"},
    )

    assert answer.status == 403
    assert answer.json()["error"] == "Eris may not read runs."
    assert asked(served) == [Action.EDIT_BENCHMARK, Action.READ_RUNS]


def test_a_case_made_from_a_run_reads_the_run_once_reading_runs_is_allowed(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, None)
    served = remote.served()
    answer = served.call(
        "benchmarks.add_case",
        {"benchmark_id": benchmark_id, "run_id": str(MISSING), "comparison": "exact"},
    )

    assert (answer.status, answer.json()["code"]) == (404, "not_found")
    assert asked(served) == [Action.EDIT_BENCHMARK, Action.READ_RUNS]


def test_a_case_given_its_input_asks_only_to_edit_the_benchmark(
    remote: Remote,
) -> None:
    benchmark_id = benchmark_with_a_case(remote.everything, None)
    served = remote.served(Action.READ_RUNS, Action.READ_RESTRICTED)
    answer = served.call(
        "benchmarks.add_case",
        {
            "benchmark_id": benchmark_id,
            "input": {"payload": "more"},
            "comparison": "exact",
            "expected": "more",
        },
    )

    assert answer.status == 200
    assert asked(served) == [Action.EDIT_BENCHMARK]


def test_promoting_from_an_experiment_asks_to_read_runs_before_anything_is_promoted(
    remote: Remote,
) -> None:
    served = remote.served(Action.READ_RUNS)
    answer = served.call(
        "production.promote",
        {"workflow_id": str(MISSING), "experiment_id": str(MISSING)},
    )

    assert answer.status == 403
    assert asked(served) == [Action.PROMOTE, Action.READ_RUNS]


def test_promoting_a_workflow_itself_asks_only_to_promote(
    remote: Remote,
) -> None:
    served = remote.served(Action.READ_RUNS)
    answer = served.call("production.promote", {"workflow_id": str(MISSING)})

    assert answer.json()["code"] != "permission_denied"
    assert asked(served) == [Action.PROMOTE]


def test_a_run_that_is_not_there_is_not_found_before_any_label_is_asked_about(
    remote: Remote,
) -> None:
    served = remote.served(Action.READ_RESTRICTED)
    answer = served.call("runs.get", {"run_id": str(MISSING)})

    assert (answer.status, answer.json()["code"]) == (404, "not_found")
    assert asked(served) == [Action.READ_RUNS]
