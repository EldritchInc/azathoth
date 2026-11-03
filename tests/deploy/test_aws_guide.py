"""Tests that the AWS guide's commands and files fit the stack and the CLI (ADR 0109).

The guide is followed for real only in a sandbox account, before a release.
These tests check everything that can be checked without AWS: the
parameters and outputs it names, the files it sends, and the result it
shows, by running its job locally.
"""

import json
import re
from pathlib import Path

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import build_parser, main
from azathoth.jobs import decode_job_request
from azathoth.persistence import DatabaseNotInitializedError, parse_database_location
from azathoth.providers import LanguageModelRegistry, ModelCatalog
from tests.deploy.template import PROJECT_ROOT, resources, template

GUIDE = PROJECT_ROOT / "docs" / "aws.md"

INIT_OVERRIDES = PROJECT_ROOT / "deploy" / "aws" / "init-overrides.json"

EXAMPLE_REQUEST = PROJECT_ROOT / "deploy" / "aws" / "example-request.json"

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "redundant-word-count.json"

TOOL_DOCUMENTS = (
    PROJECT_ROOT / "examples" / "tools" / "word-count.json",
    PROJECT_ROOT / "examples" / "tools" / "word-count-process.json",
)


def text() -> str:
    """Return the guide."""

    return GUIDE.read_text(encoding="utf-8")


def deploy_lines() -> list[str]:
    """Return every `aws cloudformation deploy` command the guide shows."""

    return [line for line in text().splitlines() if line.startswith("aws cloudformation deploy")]


def overridden_parameters(
    line: str,
) -> list[str]:
    """Return the parameters one deploy command sets."""

    overrides = line.split("--parameter-overrides ", 1)[1]

    return [assignment.split("=", 1)[0] for assignment in overrides.split()]


def test_every_deploy_names_the_template_and_acknowledges_its_roles() -> None:
    assert len(deploy_lines()) == 6

    for line in deploy_lines():
        assert "--template-file deploy/aws/azathoth.yaml" in line
        assert "--capabilities CAPABILITY_IAM" in line


def test_every_deploy_sets_only_the_templates_parameters_and_every_required_one() -> None:
    parameters = template()["Parameters"]
    required = {name for name, parameter in parameters.items() if "Default" not in parameter}

    for line in deploy_lines():
        named = set(overridden_parameters(line))

        assert named <= set(parameters), line
        assert required <= named, line


def test_the_parameter_table_lists_every_parameter_the_first_deploy_leaves_to_its_default() -> None:
    tabled = set()

    for row in re.findall(r"^\| (`.+?`) \|", text(), re.MULTILINE):
        tabled |= set(re.findall(r"`([A-Za-z]+)`", row))

    first = set(overridden_parameters(deploy_lines()[0]))
    defaulted = {
        name for name, parameter in template()["Parameters"].items() if "Default" in parameter
    }

    assert tabled == defaulted - first


def test_the_table_states_the_templates_defaults() -> None:
    parameters = template()["Parameters"]

    for row in re.findall(r"^\| `(\w+)` \| `([^`]+)` \|", text(), re.MULTILINE):
        name, default = row

        assert str(parameters[name]["Default"]) == default, name


def test_every_output_the_guide_reads_is_one_the_stack_has() -> None:
    read = set(re.findall(r"(?:\$\(|= |\()output (\w+)", text()))

    assert read <= set(template()["Outputs"])
    assert {"JobQueueUrl", "ResultQueueUrl", "TaskDefinitionArn", "ContentBucketName"} <= read


def test_the_init_task_overrides_the_workers_container_with_init() -> None:
    overrides = json.loads(INIT_OVERRIDES.read_text(encoding="utf-8"))
    (container,) = resources()["TaskDefinition"]["Properties"]["ContainerDefinitions"]
    (override,) = overrides["containerOverrides"]

    assert override["name"] == container["Name"]
    assert build_parser().parse_args(override["command"]).command == "init"
    assert text().count("--overrides file://deploy/aws/init-overrides.json") == 4


def test_the_example_request_is_a_job_for_the_workflow_the_guide_promotes() -> None:
    request = decode_job_request(json.loads(EXAMPLE_REQUEST.read_text(encoding="utf-8")))
    workflow = json.loads(WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))

    assert str(request.workflow_id) == workflow["metadata"]["id"]
    assert f"azathoth workflow promote {request.workflow_id}" in text()
    assert f"```json\n{EXAMPLE_REQUEST.read_text(encoding='utf-8').rstrip()}\n```" in text()
    assert text().count("--message-body file://deploy/aws/example-request.json") == 2


def test_the_guide_shows_the_result_the_example_job_really_has(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(cli_bootstrap, "_load_current_models", lambda _: ModelCatalog())
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(),
    )

    request = decode_job_request(json.loads(EXAMPLE_REQUEST.read_text(encoding="utf-8")))

    assert main(("init",)) == 0

    for tool in TOOL_DOCUMENTS:
        assert main(("tool", "import", str(tool))) == 0

    assert main(("workflow", "import", str(WORKFLOW_DOCUMENT))) == 0
    assert main(("workflow", "promote", str(request.workflow_id))) == 0

    capsys.readouterr()

    assert main(("job", "run", str(EXAMPLE_REQUEST))) == 0

    (line,) = capsys.readouterr().out.splitlines()
    result = json.loads(line)
    documented = line.replace(result["invocation_id"], "<INVOCATION_ID>")

    assert f"```json\n{documented}\n```" in text()


def test_the_guide_quotes_the_real_refusal_of_an_uninitialized_database() -> None:
    location = parse_database_location("postgresql://azathoth:secret@db.example.com:5432/azathoth")
    message = str(DatabaseNotInitializedError(location)).replace("db.example.com", "<HOST>")

    assert f"```text\n{message}\n```" in text()


def test_the_readme_and_the_guides_link_the_aws_guide() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "https://github.com/EldritchInc/azathoth/blob/main/docs/aws.md" in readme

    for guide in ("install.md", "container.md"):
        assert "](aws.md)" in (PROJECT_ROOT / "docs" / guide).read_text(encoding="utf-8")
