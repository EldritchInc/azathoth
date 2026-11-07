"""Tests that ADR 0110 states the S3 tools, the stack's grant and the example as they are."""

from pathlib import Path
from typing import Any
from uuid import UUID

from azathoth.context import LineageRun, LineageStep, StepLineage, encode_step_lineage
from tests.deploy.template import defaults, properties, resolve
from tests.standard.harness import standard_implementation, standard_source, standard_tool_failure

PROJECT_ROOT = Path(__file__).parents[2]

ADRS = PROJECT_ROOT / "docs" / "adrs"

ADR = ADRS / "0110-split-and-read-s3-objects.md"

MEBIBYTE = 1024 * 1024


def text() -> str:
    """Return the ADR."""

    return ADR.read_text(encoding="utf-8")


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(text().split())


def script(
    name: str,
) -> dict[str, Any]:
    """Load one S3 tool's source as a module that does not run, and return its names."""

    namespace: dict[str, Any] = {"__name__": name}

    exec(compile(standard_source(name), name, "exec"), namespace)

    return namespace


def test_the_adr_states_the_split_defaults_and_limits() -> None:
    split = script("split_s3_object")

    assert (split["DEFAULT_MODE"], split["MODES"]) == ("lines", ("lines", "bytes"))
    assert split["DEFAULT_CHUNK_BYTES"] == 5 * MEBIBYTE
    assert split["MAX_CHUNK_BYTES"] == 100 * MEBIBYTE
    assert "In `lines` mode, the default," in prose()
    assert "`chunk_bytes`, 5 MiB by default and at most 100 MiB" in prose()
    assert "a required `max_chunks`" in prose()


def test_the_adr_states_the_read_defaults_and_limits() -> None:
    read = script("read_s3_object")

    assert read["DEFAULT_MEDIA_TYPE"] == "text/plain"
    assert (read["DEFAULT_MAX_BYTES"], read["MAX_BYTES"]) == (10 * MEBIBYTE, 100 * MEBIBYTE)
    assert "a `media_type`, `text/plain` by default" in prose()
    assert "`max_bytes`, 10 MiB by default and at most 100 MiB" in prose()


def test_the_adr_shows_the_key_every_chunk_is_written_under() -> None:
    run_id = UUID("e9000000-0000-4000-8000-000000000001")
    step_id = UUID("e9000000-0000-4000-8000-000000000002")
    run = LineageRun(workflow_id=UUID("e9000000-0000-4000-8000-000000000003"), run_id=run_id)
    lineage = encode_step_lineage(
        StepLineage(
            step=LineageStep(
                workflow_id=run.workflow_id, run_id=run_id, step_id=step_id, attempt=3
            ),
            depth=0,
            root=run,
        )
    )
    plan = script("split_s3_object")["parse"](
        {"settings": {"destination_prefix": "s3://data/", "max_chunks": 1}, "uri": "s3://data/a"},
        lineage,
    )
    shown = f"{plan['destination_prefix']}chunk-000000".replace(str(run_id), "<RUN_ID>").replace(
        str(step_id), "<STEP_ID>"
    )

    assert shown == "<RUN_ID>/<STEP_ID>/3/chunk-000000"
    assert "```text\n<DESTINATION_PREFIX><RUN_ID>/<STEP_ID>/<ATTEMPT>/chunk-000000\n```" in text()


def test_the_adr_states_what_each_tool_grants_itself() -> None:
    for name in ("split_s3_object", "read_s3_object"):
        assert standard_implementation(name).environment == ("AWS_*",)

    assert "Each grants itself `AWS_*` and nothing else" in prose()


def test_the_adr_states_the_exit_statuses() -> None:
    status, _ = standard_tool_failure("read_s3_object", {"uri": "https://example.com/a"})

    assert status == 2
    assert "Bad inputs exit with status 2, and every other failure with status 1" in prose()


def test_the_adr_states_the_stacks_grant() -> None:
    parameters = {**defaults(), "DataBucket": "data", "DataPrefix": "work/"}
    (policy,) = resolve(properties("TaskRole"), parameters)["Policies"]
    (granted,) = (
        statement
        for statement in policy["PolicyDocument"]["Statement"]
        if statement["Sid"] == "WorkWithData"
    )

    assert granted["Action"] == ["s3:GetObject", "s3:PutObject"]
    assert "grant the task role `s3:GetObject` and `s3:PutObject` under that prefix" in prose()


def test_the_adr_names_an_example_that_exists() -> None:
    assert "`examples/large-file`" in text()
    assert (PROJECT_ROOT / "examples" / "large-file" / "README.md").exists()


def test_the_adrs_it_amends_point_to_it() -> None:
    for number in ("0095", "0108", "0109"):
        (path,) = ADRS.glob(f"{number}-*.md")
        status = path.read_text(encoding="utf-8").split("\n")[2]

        assert status.endswith("ADR 0110"), path.name
