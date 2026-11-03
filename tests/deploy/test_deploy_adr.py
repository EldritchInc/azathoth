"""Tests that ADR 0109 states the deployment as the template and workflows make it."""

import re

from azathoth.worker import MAX_WAIT_SECONDS
from tests.deploy.template import PROJECT_ROOT, defaults, properties, resolve, template

ADR = PROJECT_ROOT / "docs" / "adrs" / "0109-deploy-on-aws.md"


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(ADR.read_text(encoding="utf-8").split())


def test_the_adr_states_the_templates_defaults() -> None:
    parameters = template()["Parameters"]

    assert parameters["MaxReceiveCount"]["Default"] == 5
    assert "`MaxReceiveCount` receipts, 5 by default" in prose()
    assert (parameters["MinTasks"]["Default"], parameters["MaxTasks"]["Default"]) == (1, 4)
    assert "between `MinTasks` and `MaxTasks` workers, 1 and 4 by default" in prose()
    assert parameters["ScaleOutBacklog"]["Default"] == 10
    assert "`ScaleOutBacklog` messages wait, 10 by default" in prose()
    assert parameters["ImageUri"]["Default"] == "ghcr.io/eldritchinc/azathoth:1.1.0"
    assert f"`{parameters['ImageUri']['Default']}`" in prose()


def test_the_adr_states_the_tasks_health_check_and_stop_timeout() -> None:
    (container,) = resolve(properties("TaskDefinition"), defaults())["ContainerDefinitions"]
    check = container["HealthCheck"]

    assert (check["Interval"], check["Retries"], check["StartPeriod"]) == (30, 3, 60)
    assert "every 30 seconds, with three retries and a minute to start" in prose()
    assert container["StopTimeout"] == 60
    assert "its stop timeout is 60 seconds, longer than a drain takes" in prose()
    assert container["StopTimeout"] > MAX_WAIT_SECONDS


def test_the_adr_states_the_queues_timing() -> None:
    queue = properties("JobQueue")

    assert (queue["VisibilityTimeout"], queue["ReceiveMessageWaitTimeSeconds"]) == (120, 20)
    assert "a two-minute visibility timeout and 20-second polls" in prose()


def test_the_adr_quotes_the_verify_command_the_container_guide_shows() -> None:
    guide = (PROJECT_ROOT / "docs" / "container.md").read_text(encoding="utf-8")
    (shown,) = set(re.findall(r"^cosign verify .+$", guide, re.MULTILINE))
    general = shown.replace("1.1.0", "<VERSION>")

    assert f"```text\n{general}\n```" in ADR.read_text(encoding="utf-8")


def test_the_adr_names_the_template_it_records() -> None:
    assert "](../../deploy/aws/azathoth.yaml)" in ADR.read_text(encoding="utf-8")
    assert (PROJECT_ROOT / "deploy" / "aws" / "azathoth.yaml").exists()
