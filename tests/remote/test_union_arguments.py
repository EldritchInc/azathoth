"""Tests that an argument a model or a JSON value can be travels as what it was (ADR 0140).

`runs.invoke` takes its input as a JSON value or a file. Read the other way
round, a file would arrive as the JSON object it is written as, and the
invocation would be given that object rather than the file's content.
"""

import uuid

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.remote.calling import call_signature, job_signature

FILE = api.RunFile(content=b"one two three", media_type="text/plain")


@pytest.mark.parametrize(
    "given",
    [
        FILE,
        {"content": "not base64 at all", "media_type": "text/plain", "more": 1},
        {"content": "b25l"},
        {"a": 1},
        "one two",
        None,
        [1, {"content": "x"}],
    ],
    ids=repr,
)
def test_an_invocations_input_arrives_as_it_was_sent(
    given: JsonValue | api.RunFile,
) -> None:
    signature = job_signature("runs.invoke")
    sent = signature.write_arguments(workflow_id=uuid.uuid4(), input=given)

    assert signature.read_arguments(sent)["input"] == given


def test_an_argument_of_models_alone_is_read_as_before() -> None:
    signature = job_signature("runs.run")
    sent = signature.write_arguments(workflow_id=uuid.uuid4(), input=FILE)

    assert signature.read_arguments(sent)["input"] == FILE

    case = call_signature("benchmarks.add_case")
    added = case.write_arguments(
        benchmark_id=uuid.uuid4(),
        input=api.RunInput(payload={"content": "b25l", "media_type": "text/plain"}),
        comparison="exact",
        expected=1,
    )

    assert case.read_arguments(added)["input"] == api.RunInput(
        payload={"content": "b25l", "media_type": "text/plain"}
    )
