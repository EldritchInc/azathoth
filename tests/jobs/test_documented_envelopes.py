"""Tests that the job envelopes shown in the READMEs are real ones (ADR 0097)."""

import json
import re
from pathlib import Path

import pytest
from pydantic import JsonValue

from azathoth.jobs import (
    JobError,
    JobErrorCode,
    JobRequestError,
    JobResult,
    JobStatus,
    decode_job_request,
)

PROJECT_ROOT = Path(__file__).parents[2]

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

JOBS_README = PROJECT_ROOT / "src" / "azathoth" / "jobs" / "README.md"

INVOCATION_ID = "55555555-5555-5555-5555-555555555555"


def json_blocks(
    path: Path,
    heading: str,
) -> tuple[str, ...]:
    """Return the JSON blocks between one heading and the next heading of its level."""

    text = path.read_text(encoding="utf-8")
    marker = heading.split(" ", 1)[0]
    section = text.split(f"{heading}\n", 1)[1]
    following = re.search(rf"^{re.escape(marker)} ", section, re.MULTILINE)

    if following is not None:
        section = section[: following.start()]

    return tuple(
        block.replace("<INVOCATION_ID>", INVOCATION_ID)
        for block in re.findall(r"```json\n(.*?)\n```", section, re.DOTALL)
    )


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        (CLI_README, "## Job Requests"),
        (JOBS_README, "## Requests"),
    ],
)
def test_documented_requests_decode(
    path: Path,
    heading: str,
) -> None:
    (block,) = json_blocks(path, heading)

    request = decode_job_request(json.loads(block))

    assert request.idempotency_key == "order-4711-review"


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        (CLI_README, "## Job Results"),
        (JOBS_README, "## Results"),
    ],
)
def test_documented_results_validate(
    path: Path,
    heading: str,
) -> None:
    result = JobResult.model_validate_json(json_blocks(path, heading)[0])

    assert result.status is JobStatus.SUCCEEDED


def test_the_documented_version_error_is_the_one_reported() -> None:
    blocks = json_blocks(CLI_README, "## Job Results")

    documented = JobError.model_validate_json(blocks[1])

    request: dict[str, JsonValue] = {
        "kind": "invoke",
        "version": 2,
        "idempotency_key": "order-4711-review",
    }

    with pytest.raises(JobRequestError) as raised:
        decode_job_request(request)

    assert documented.code is JobErrorCode.UNSUPPORTED_VERSION
    assert raised.value.error == documented


def test_the_cli_command_tree_names_job_run() -> None:
    assert "├── job\n│   └── run <FILE | ->\n" in CLI_README.read_text(encoding="utf-8")
