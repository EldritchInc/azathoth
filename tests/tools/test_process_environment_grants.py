"""Tests for the environment variables a process implementation grants itself (ADR 0099)."""

import json
import re
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.revisions import content_digest
from azathoth.tools import (
    ENVIRONMENT_GRANT_PATTERN,
    ENVIRONMENT_PREFIX_WILDCARD,
    PROCESS_TOOL_RUNTIME,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    PYTHON_TOOL_RUNTIME,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

TOOL_EXAMPLES = PROJECT_ROOT / "examples" / "tools"

#
# Digests of checked-in tool examples computed before implementations could
# grant environment variables. An implementation without grants must never
# change them.
#
EXAMPLE_DIGESTS = {
    "word-count-process.json": "5cea8b823b9bf16468b90e0b8707f0de325346bfb7e601f570201a87b21c1ebd",
    "countdown-step.json": "1e68339ce9715b740c66e265ce720b7d91ab9bd5948f6ea7b1d913bfc42dbd4c",
}

TOOL_ID = UUID("2c3d4e5f-6a7b-4c8d-8e9f-1a2b3c4d5e01")

IMPLEMENTATION_ID = UUID("2c3d4e5f-6a7b-4c8d-8e9f-1a2b3c4d5e21")

SCRIPT = "import json, sys\nprint(json.dumps(json.load(sys.stdin)))\n"

CHILD_GRANTS = ("AZATHOTH_DATABASE", "OPENROUTER_API_KEY", "AZATHOTH_WORKFLOW_DEPTH")


def create_implementation(
    *,
    environment: tuple[str, ...] = (),
    runtime: str = PROCESS_TOOL_RUNTIME,
) -> ToolImplementation:
    """Create one implementation granting itself the given variables."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=runtime,
        source=SCRIPT,
        command=("python3",) if runtime == PROCESS_TOOL_RUNTIME else None,
        environment=environment,
    )


# Accepted grants


def test_an_implementation_grants_nothing_by_default() -> None:
    assert create_implementation().environment == ()


def test_an_implementation_grants_variables_by_name_in_order() -> None:
    assert create_implementation(environment=CHILD_GRANTS).environment == CHILD_GRANTS


@pytest.mark.parametrize(
    "grant",
    ["HOME", "_PRIVATE", "lower_case", "AWS_*", "OTEL_EXPORTER_*", "A*", "X1"],
)
def test_names_and_prefixes_are_grants(
    grant: str,
) -> None:
    assert create_implementation(environment=(grant,)).environment == (grant,)


def test_the_grant_pattern_is_a_name_with_an_optional_prefix_wildcard() -> None:
    assert ENVIRONMENT_GRANT_PATTERN == r"^[A-Za-z_][A-Za-z0-9_]*\*?$"
    assert ENVIRONMENT_PREFIX_WILDCARD == "*"


# Refused grants


@pytest.mark.parametrize(
    "grant",
    ["*", "", "1PASSWORD", "AWS-KEY", "AWS_*_ID", "A**", "PATH ", " PATH", "A.B", "*_KEY"],
)
def test_malformed_grants_are_refused(
    grant: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=re.escape(
            f"Environment grant {grant!r} must be a variable name, "
            "or a prefix of one followed by '*'."
        ),
    ):
        create_implementation(environment=(grant,))


def test_the_managed_timeout_variable_cannot_be_granted() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            f"{PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE} is set by the engine "
            "from timeout_seconds and cannot be granted"
        ),
    ):
        create_implementation(environment=(PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,))


def test_grants_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="Environment grants must be unique"):
        create_implementation(environment=("HOME", "AWS_*", "HOME"))


def test_only_process_implementations_grant_variables() -> None:
    with pytest.raises(
        ValidationError,
        match="Only process tool implementations may grant environment variables",
    ):
        create_implementation(environment=("HOME",), runtime=PYTHON_TOOL_RUNTIME)


def test_a_python_implementation_without_grants_is_unchanged() -> None:
    implementation = create_implementation(runtime=PYTHON_TOOL_RUNTIME)

    assert implementation.environment == ()
    assert "environment" not in implementation.model_dump(mode="json")


# Serialization and identity


def test_an_implementation_without_grants_serializes_without_them() -> None:
    assert "environment" not in create_implementation().model_dump(mode="json")


def test_grants_are_serialized_in_order() -> None:
    serialized = create_implementation(environment=CHILD_GRANTS).model_dump(mode="json")

    assert serialized["environment"] == list(CHILD_GRANTS)


def test_grants_round_trip_through_json() -> None:
    implementation = create_implementation(environment=("AWS_*", "HOME"))

    assert ToolImplementation.model_validate_json(implementation.model_dump_json()) == (
        implementation
    )


def test_an_implementation_from_before_grants_still_decodes() -> None:
    document = json.loads(create_implementation(environment=("HOME",)).model_dump_json())

    del document["environment"]

    assert ToolImplementation.model_validate(document).environment == ()


def test_grants_are_part_of_implementation_identity() -> None:
    assert content_digest(create_implementation(environment=("HOME",))) != content_digest(
        create_implementation()
    )


def test_grant_order_is_part_of_implementation_identity() -> None:
    assert content_digest(create_implementation(environment=("A", "B"))) != content_digest(
        create_implementation(environment=("B", "A"))
    )


@pytest.mark.parametrize(("name", "expected"), sorted(EXAMPLE_DIGESTS.items()))
def test_existing_tool_example_digests_are_unchanged(
    name: str,
    expected: str,
) -> None:
    document = decode_tool_document((TOOL_EXAMPLES / name).read_text(encoding="utf-8"))

    assert content_digest(document) == expected


def test_a_tool_document_round_trips_its_grants() -> None:
    document = decode_tool_document(
        (TOOL_EXAMPLES / "word-count-process.json").read_text(encoding="utf-8")
    )

    granted = document.model_copy(
        update={
            "implementations": tuple(
                implementation.model_copy(update={"environment": ("HOME", "AWS_*")})
                for implementation in document.implementations
            ),
        }
    )

    decoded = decode_tool_document(encode_tool_document(granted))

    assert decoded.implementations[0].environment == ("HOME", "AWS_*")
    assert decoded == granted
