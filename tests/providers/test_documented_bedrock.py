"""Tests that the Bedrock documentation names what Azathoth really does (ADR 0103)."""

import json
import re
from pathlib import Path

import pytest

from azathoth.providers import (
    BLOCKED_STOP_REASONS,
    MISSING_BEDROCK_EXTRA_MESSAGE,
    MISSING_REGION_MESSAGE,
    BedrockPricing,
)
from azathoth.standard import standard_tool_documents

PROJECT_ROOT = Path(__file__).parents[2]

BEDROCK_GUIDE = PROJECT_ROOT / "docs" / "bedrock.md"

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

PROVIDERS_README = PROJECT_ROOT / "src" / "azathoth" / "providers" / "README.md"

BEDROCK_GRANTS = ("AZATHOTH_BEDROCK", "AZATHOTH_BEDROCK_PRICING", "AWS_*")

COMPOSITION_TOOLS = ("run_workflow", "loop_workflow")


def section(
    path: Path,
    heading: str,
) -> str:
    """Return the text under one heading, up to the next heading of its level or above."""

    text = path.read_text(encoding="utf-8")
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(f"{heading}\n")
    rest = text[start + len(heading) + 1 :]
    following = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)

    return rest if following is None else rest[: following.start()]


def json_blocks(
    text: str,
) -> list[object]:
    """Return every fenced JSON block, decoded."""

    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]


@pytest.mark.parametrize("guide", (BEDROCK_GUIDE, CLI_README))
def test_the_configuration_refusals_are_quoted_exactly(
    guide: Path,
) -> None:
    text = guide.read_text(encoding="utf-8")

    assert f"\n{MISSING_BEDROCK_EXTRA_MESSAGE}\n" in text
    assert f"\n{MISSING_REGION_MESSAGE}\n" in text


@pytest.mark.parametrize(
    ("guide", "heading"),
    (
        (BEDROCK_GUIDE, "## 4. Price Your Models"),
        (PROVIDERS_README, "## Amazon Bedrock"),
    ),
)
def test_the_documented_pricing_document_is_a_valid_one(
    guide: Path,
    heading: str,
) -> None:
    (document,) = json_blocks(section(guide, heading))

    pricing = BedrockPricing.model_validate(document)

    assert pricing.price("amazon.nova-pro-v1:0") is not None


def test_the_iam_policy_allows_exactly_the_calls_azathoth_makes() -> None:
    (policy,) = json_blocks(section(BEDROCK_GUIDE, "### The permissions it needs"))

    assert isinstance(policy, dict)

    actions = {action for statement in policy["Statement"] for action in statement["Action"]}

    assert actions == {
        "bedrock:ListFoundationModels",
        "bedrock:ListInferenceProfiles",
        "bedrock:InvokeModel",
    }


def test_every_blocked_stop_reason_is_named_in_the_guide() -> None:
    troubleshooting = section(BEDROCK_GUIDE, "## Troubleshooting")

    for reason in BLOCKED_STOP_REASONS:
        assert f"`{reason}`" in troubleshooting, reason


def test_the_guide_names_the_grants_the_standard_tools_really_have() -> None:
    children = section(BEDROCK_GUIDE, "## Child Workflows")

    for document in standard_tool_documents():
        if document.definition.name not in COMPOSITION_TOOLS:
            continue

        (implementation,) = document.implementations

        for grant in BEDROCK_GRANTS:
            assert grant in implementation.environment, (document.definition.name, grant)

    for grant in BEDROCK_GRANTS:
        name = grant.removesuffix("*")

        assert f"`{name}" in children, grant
