"""Tests of how each call of the service API travels over HTTP, read from the call (ADR 0127)."""

import base64
import inspect
import json
import sqlite3
import typing
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.benchmark_cases import Keep
from azathoth.api.calls import SERVICE_CALLS
from azathoth.api.errors import InvalidArgumentError
from azathoth.api.models import InstanceDescription, RunFile
from azathoth.remote.calling import (
    CALLS_ROUTE,
    SERVER_ONLY_PARAMETERS,
    CallArgumentsError,
    NotServedError,
    call_signature,
    call_signatures,
)
from tests.api.test_calls import functions

WORKFLOW_ID = UUID("c1060000-0000-4000-8000-000000000001")

BENCHMARK_ID = UUID("c1060000-0000-4000-8000-000000000002")

RUN_ID = UUID("c1060000-0000-4000-8000-000000000003")

PDF = b"%PDF-1.7\n\x00\xff\xfe binary"


@pytest.fixture
def instance(
    tmp_path: Path,
) -> Iterator[api.Azathoth]:
    path = tmp_path / "azathoth.db"
    sqlite3.connect(path).close()

    with api.open(str(path)) as opened:
        yield opened


def parameters(
    name: str,
) -> dict[str, inspect.Parameter]:
    """Return a call's parameters on `Azathoth`, without `self`."""

    function = functions()[name]

    return dict(list(inspect.signature(function).parameters.items())[1:])


# Which calls travel


def test_each_call_is_served_at_a_route_of_its_name() -> None:
    assert CALLS_ROUTE == "/v1/calls/{name}"


def test_every_served_call_but_a_job_has_a_signature() -> None:
    expected = [call.name for call in SERVICE_CALLS if call.served and not call.job]

    assert list(call_signatures()) == expected
    assert len(expected) == 66


def test_a_job_is_a_call_that_takes_a_callback_for_its_events() -> None:
    jobs = {call.name for call in SERVICE_CALLS if call.job}
    takes_events = {
        call.name for call in SERVICE_CALLS if call.served and "on_event" in parameters(call.name)
    }

    assert jobs == takes_events
    assert sorted(jobs) == [
        "benchmarks.compare",
        "benchmarks.run",
        "invocations.resume",
        "optimization.optimize",
        "runs.invoke",
        "runs.resume",
        "runs.run",
        "runs.try_step",
    ]


def test_a_job_or_a_call_never_served_has_no_signature() -> None:
    with pytest.raises(NotServedError, match=r"^A remote runs runs\.run as a job on its workers"):
        call_signature("runs.run")

    with pytest.raises(NotServedError, match=r"^A remote never serves remotes\.add\.$"):
        call_signature("remotes.add")

    with pytest.raises(LookupError, match="no call named 'runs.fly'"):
        call_signature("runs.fly")


def test_every_argument_and_result_is_json() -> None:
    for signature in call_signatures().values():
        signature.arguments.model_json_schema()
        signature.result.json_schema(mode="serialization")
        signature.result.json_schema(mode="validation")


def test_every_parameter_travels_but_those_only_the_server_gives() -> None:
    for name, signature in call_signatures().items():
        fields = signature.arguments.model_fields
        expected = {
            parameter
            for parameter in parameters(name)
            if (name, parameter) not in SERVER_ONLY_PARAMETERS
        }

        assert set(fields) == expected, name

        for parameter, declared in parameters(name).items():
            if parameter in fields:
                required = declared.default is inspect.Parameter.empty

                assert fields[parameter].is_required() == required, (name, parameter)

                if not required:
                    assert fields[parameter].default == declared.default, (name, parameter)


def test_only_the_connection_tools_from_mcp_is_tested_with_is_the_servers_own() -> None:
    assert frozenset({("tools.from_mcp", "connect")}) == SERVER_ONLY_PARAMETERS

    hint = typing.get_type_hints(functions()["tools.from_mcp"])["connect"]

    assert type(None) in typing.get_args(hint)
    assert parameters("tools.from_mcp")["connect"].default is None


# Reading and writing arguments


def test_arguments_are_read_by_name_as_the_call_takes_them() -> None:
    signature = call_signature("workflows.get")

    read = signature.read_arguments(json.dumps({"workflow_id": str(WORKFLOW_ID)}).encode())

    assert read["workflow_id"] == WORKFLOW_ID
    assert set(read) == set(parameters("workflows.get"))


def test_an_empty_body_gives_no_arguments_and_the_calls_defaults() -> None:
    read = call_signature("workflows.list").read_arguments(b"")

    assert read == call_signature("workflows.list").read_arguments(b"{}")
    assert set(read) == set(parameters("workflows.list"))


@pytest.mark.parametrize(
    ("body", "refusal"),
    [
        (
            b"{}",
            "These are not the arguments workflows.get takes at workflow_id: Field required.",
        ),
        (
            b'{"workflow_id": "not-a-uuid"}',
            "These are not the arguments workflows.get takes at workflow_id: Input should be a "
            "valid UUID",
        ),
        (
            b'{"workflow_id": "c1060000-0000-4000-8000-000000000001", "everything": true}',
            "These are not the arguments workflows.get takes at everything: Extra inputs are not "
            "permitted.",
        ),
        (
            b'["c1060000-0000-4000-8000-000000000001"]',
            "These are not the arguments workflows.get takes: Input should be an object.",
        ),
        (
            b"workflow_id=c1060000",
            "These are not the arguments workflows.get takes: Invalid JSON: expected value at "
            "line 1 column 1.",
        ),
    ],
    ids=["missing", "invalid", "unknown", "not-an-object", "not-json"],
)
def test_arguments_that_are_not_the_calls_are_refused_saying_where(
    body: bytes,
    refusal: str,
) -> None:
    with pytest.raises(CallArgumentsError) as caught:
        call_signature("workflows.get").read_arguments(body)

    assert str(caught.value).startswith(refusal)
    assert isinstance(caught.value, InvalidArgumentError)
    assert caught.value.code == "invalid_argument"


def test_a_client_writes_only_the_arguments_it_gives_and_not_as_their_defaults() -> None:
    signature = call_signature("benchmarks.add_case")
    body = signature.write_arguments(
        benchmark_id=BENCHMARK_ID,
        run_id=RUN_ID,
        comparison="exact",
        expected=Keep.KEEP,
        description=None,
    )

    assert json.loads(body) == {
        "benchmark_id": str(BENCHMARK_ID),
        "run_id": str(RUN_ID),
        "comparison": "exact",
    }
    assert signature.read_arguments(body)["expected"] is Keep.KEEP


def test_a_client_is_refused_arguments_the_call_does_not_take() -> None:
    with pytest.raises(CallArgumentsError, match="at flavour: Extra inputs are not permitted"):
        call_signature("workflows.get").write_arguments(workflow_id=WORKFLOW_ID, flavour="dry")


def test_a_files_bytes_travel_in_base64_and_arrive_whole() -> None:
    signature = call_signature("benchmarks.add_case")
    sent = RunFile(content=PDF, media_type="application/pdf")
    body = signature.write_arguments(
        benchmark_id=BENCHMARK_ID,
        file=sent,
        file_uri="file:///a.pdf",
        comparison="exact",
    )
    content = json.loads(body)["file"]["content"]

    assert base64.urlsafe_b64decode(content) == PDF
    assert signature.read_arguments(body)["file"] == sent


def test_a_file_in_standard_base64_is_read_too() -> None:
    standard = base64.b64encode(PDF).decode("ascii")

    assert "+" in standard or "/" in standard
    assert RunFile.model_validate_json(
        json.dumps({"content": standard, "media_type": "application/pdf"})
    ) == RunFile(content=PDF, media_type="application/pdf")


# Results and the method called


def test_a_result_is_written_and_read_back_as_the_call_returns_it(
    instance: api.Azathoth,
) -> None:
    signature = call_signature("describe")
    described = signature.bound(instance)()

    assert isinstance(described, InstanceDescription)
    assert signature.read_result(signature.write_result(described)) == described


def test_a_call_of_a_collection_is_bound_to_its_method(
    instance: api.Azathoth,
) -> None:
    signature = call_signature("workflows.list")
    listed = signature.bound(instance)(**signature.read_arguments(b""))

    assert signature.read_result(signature.write_result(listed)) == listed
    assert signature.bound(instance) == instance.workflows.list
