"""Tests that a listing leaves out what the policy does not let a caller see (ADR 0127)."""

import json
import typing
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from azathoth.api.calls import SERVICE_CALLS, ServiceCall, service_call
from azathoth.remote import Action, Decision, Principal
from azathoth.remote.listings import LISTED_IDS, listed_resource, visible
from tests.api.test_calls import functions
from tests.remote.test_call_routes import ERIS, Asking, Served
from tests.remote.test_conditions import EXAMPLES

LISTINGS = [call for call in SERVICE_CALLS if call.lists is not None]


class Seeing(Asking):
    """A policy that lets the owner do anything to the remote, and see only some things."""

    def __init__(
        self,
        *seen: str,
        lists: bool = True,
    ) -> None:
        super().__init__()
        self.seen = frozenset(seen)
        self.lists = lists

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        super().decide(principal, action, resource)

        if resource is None and self.lists:
            return Decision(allowed=True)

        if resource in self.seen:
            return Decision(allowed=True)

        return Decision(allowed=False, reason=f"{principal.name} may not see {resource}.")


class Remote:
    """One remote's database, served to Eris under whichever policy a test gives."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path
        self.everything = Served(path, principal=ERIS)

    def seeing(
        self,
        *seen: str,
        lists: bool = True,
    ) -> Served:
        return Served(self.path, principal=ERIS, policy=Seeing(*seen, lists=lists))


@pytest.fixture
def remote(
    tmp_path: Path,
) -> Iterator[Remote]:
    yield Remote(tmp_path / "azathoth.db")


def benchmark(
    remote: Remote,
    name: str,
) -> str:
    created = remote.everything.call(
        "benchmarks.create",
        {"name": name, "description": f"{name.capitalize()}."},
    )
    benchmark_id: str = created.json()["benchmark"]["id"]

    return benchmark_id


# Which field names each listed thing


def test_every_kind_the_catalog_lists_has_a_field_naming_each_item() -> None:
    assert {call.lists for call in LISTINGS} == set(LISTED_IDS)


@pytest.mark.parametrize("call", LISTINGS, ids=[call.name for call in LISTINGS])
def test_each_listings_items_have_the_field_their_kind_is_named_by(
    call: ServiceCall,
) -> None:
    returned = typing.get_type_hints(functions()[call.name])["return"]
    (item, more) = typing.get_args(returned)

    assert typing.get_origin(returned) is tuple
    assert more is Ellipsis
    assert call.lists is not None
    assert LISTED_IDS[call.lists] in item.model_fields


def test_a_listed_item_is_its_kind_and_id() -> None:
    assert listed_resource("run", SimpleNamespace(run_id="r1")) == "run r1"
    assert listed_resource("workflow", SimpleNamespace(id="w1")) == "workflow w1"

    with pytest.raises(KeyError):
        listed_resource("remote", SimpleNamespace(id="x"))


def test_a_call_that_lists_nothing_keeps_what_it_returns() -> None:
    policy = Seeing()

    assert visible(service_call("describe"), ("one",), policy, ERIS) == ("one",)
    assert policy.asked == []


# Listing through a remote


def test_a_listing_leaves_out_what_the_caller_may_not_see(
    remote: Remote,
) -> None:
    charts = benchmark(remote, "charts")
    scans = benchmark(remote, "scans")
    served = remote.seeing(f"benchmark {charts}")
    listed = served.call("benchmarks.list")

    assert listed.status == 200
    assert [summary["id"] for summary in listed.json()] == [charts]
    assert scans not in listed.body.decode()
    assert served.policy.asked == [
        ("Eris", Action.READ_CATALOG, None),
        ("Eris", Action.READ_CATALOG, f"benchmark {charts}"),
        ("Eris", Action.READ_CATALOG, f"benchmark {scans}"),
    ]


def test_a_listing_of_nothing_the_caller_may_see_is_empty_not_refused(
    remote: Remote,
) -> None:
    benchmark(remote, "charts")
    listed = remote.seeing().call("benchmarks.list")

    assert (listed.status, listed.json()) == (200, [])


def test_a_listing_the_caller_may_not_make_is_refused(
    remote: Remote,
) -> None:
    benchmark(remote, "charts")
    listed = remote.seeing(lists=False).call("benchmarks.list")

    assert (listed.status, listed.json()["code"]) == (403, "permission_denied")


def test_a_listing_keeps_the_order_it_was_listed_in(
    remote: Remote,
) -> None:
    made = [benchmark(remote, name) for name in ("alpha", "beta", "gamma")]
    everything = [summary["id"] for summary in remote.everything.call("benchmarks.list").json()]
    seen = remote.seeing(*(f"benchmark {each}" for each in made))

    assert [summary["id"] for summary in seen.call("benchmarks.list").json()] == everything


def test_a_listing_of_one_things_items_asks_about_each(
    remote: Remote,
) -> None:
    document = json.loads((EXAMPLES / "word-count.json").read_text())
    imported = remote.everything.call("tools.import_document", {"document": document})
    tool_id = imported.json()["tool"]["id"]
    resource = f"tool {tool_id}"

    seen = remote.seeing(resource).call("tools.versions", {"tool_id": tool_id})
    unseen = remote.seeing(lists=True).call("tools.versions", {"tool_id": tool_id})

    assert [version["id"] for version in seen.json()] == [tool_id]
    assert (unseen.status, unseen.json()["code"]) == (403, "permission_denied")
