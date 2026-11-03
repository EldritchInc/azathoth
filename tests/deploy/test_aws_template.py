"""Tests of the CloudFormation template that runs the workers on Fargate (ADR 0109).

They read the template, and resolve it as a stack would for a given set of
parameters. Nothing reaches AWS.
"""

import json
import re
import tomllib
from typing import Any

import pytest

from azathoth.cli import build_parser
from azathoth.inputs import S3ContentLocation, S3InputLocation
from azathoth.worker import (
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    MAX_WAIT_SECONDS,
)
from tests.deploy.template import (
    PROJECT_ROOT,
    PSEUDO_PARAMETERS,
    TEMPLATE,
    conditions,
    conditions_used,
    defaults,
    placeholders,
    properties,
    references,
    resolve,
    resources,
    template,
)

INPUTS = {"InputBucket": "azathoth-inputs", "InputPrefix": "requests/"}

OPENROUTER = {
    "OpenRouterSecretArn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:openrouter-Xy"
}

BEDROCK = {"EnableBedrock": "true"}

EVERYTHING = {**INPUTS, **OPENROUTER, **BEDROCK}

HEARTBEAT = "/tmp/azathoth-heartbeat"


def with_(
    **overrides: Any,
) -> dict[str, Any]:
    """Return the default parameters, with some overridden."""

    return {**defaults(), **overrides}


def worker(
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Return the worker's container definition, resolved for some parameters."""

    (container,) = resolve(properties("TaskDefinition"), parameters)["ContainerDefinitions"]

    assert isinstance(container, dict)

    return container


def statements(
    parameters: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the task role's statements by their Sid, resolved for some parameters."""

    (policy,) = resolve(properties("TaskRole"), parameters)["Policies"]

    return {statement["Sid"]: statement for statement in policy["PolicyDocument"]["Statement"]}


# The template itself


def test_the_template_is_plain_yaml_with_long_form_intrinsics() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert template()["AWSTemplateFormatVersion"] == "2010-09-09"
    assert not re.search(r"!(Ref|Sub|GetAtt|If|Equals|Not|Select|Join)\b", text)


def test_every_reference_names_a_parameter_a_resource_or_a_pseudo_parameter() -> None:
    known = set(template()["Parameters"]) | set(resources()) | set(PSEUDO_PARAMETERS)

    assert references(template()["Resources"]) | references(template()["Outputs"]) <= (
        known | {"AWS::NoValue"}
    )


def test_every_condition_is_defined_and_used() -> None:
    defined = set(template()["Conditions"])
    used = conditions_used(template()["Resources"])

    assert used == defined


def test_every_parameter_is_used() -> None:
    used = references(template()["Resources"]) | references(template()["Conditions"])

    assert set(template()["Parameters"]) <= used


def test_development_reads_the_template_with_pyyaml() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    development = project["project"]["optional-dependencies"]["dev"]

    assert any(requirement.startswith("PyYAML") for requirement in development)
    assert not any(
        requirement.startswith("PyYAML") for requirement in project["project"]["dependencies"]
    )


# The queues


def test_the_job_queue_matches_the_worker_and_moves_poison_to_the_dead_letter_queue() -> None:
    queue = resolve(properties("JobQueue"), defaults())

    assert queue["VisibilityTimeout"] == DEFAULT_VISIBILITY_TIMEOUT_SECONDS
    assert queue["ReceiveMessageWaitTimeSeconds"] == MAX_WAIT_SECONDS
    assert queue["RedrivePolicy"] == {
        "deadLetterTargetArn": placeholders()["JobDeadLetterQueue.Arn"],
        "maxReceiveCount": 5,
    }


@pytest.mark.parametrize("name", ["JobQueue", "JobDeadLetterQueue", "ResultQueue"])
def test_every_queue_is_encrypted_and_keeps_messages_fourteen_days(
    name: str,
) -> None:
    queue = properties(name)

    assert queue["SqsManagedSseEnabled"] is True
    assert queue["MessageRetentionPeriod"] == 14 * 24 * 60 * 60


# The content bucket


def test_the_content_bucket_is_private_encrypted_and_outlives_the_stack() -> None:
    bucket = resources()["ContentBucket"]
    settings = bucket["Properties"]

    assert (bucket["DeletionPolicy"], bucket["UpdateReplacePolicy"]) == ("Retain", "Retain")
    assert settings["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    assert settings["BucketEncryption"]["ServerSideEncryptionConfiguration"] == [
        {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
    ]
    assert settings["OwnershipControls"] == {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}


# The worker's container


@pytest.mark.parametrize("extra", [{}, INPUTS], ids=["no-inputs", "inputs"])
def test_the_command_is_a_real_worker_run_over_the_stacks_queues(
    extra: dict[str, Any],
) -> None:
    command = worker(with_(**extra))["Command"]
    arguments = build_parser().parse_args(command)

    assert arguments.worker_action == "run"
    assert arguments.worker_queue_url == placeholders()["JobQueue"]
    assert arguments.worker_result_queue_url == placeholders()["ResultQueue"]
    assert str(arguments.worker_heartbeat_file) == HEARTBEAT


def test_without_an_input_bucket_the_worker_accepts_no_references() -> None:
    arguments = build_parser().parse_args(worker(defaults())["Command"])

    assert arguments.worker_allow_input_buckets == []


def test_the_worker_allows_exactly_the_inputs_its_role_may_read() -> None:
    parameters = with_(**INPUTS)
    arguments = build_parser().parse_args(worker(parameters)["Command"])

    (allowed,) = [S3InputLocation.parse(value) for value in arguments.worker_allow_input_buckets]
    granted = statements(parameters)["ReadInputs"]

    assert (allowed.bucket, allowed.prefix) == ("azathoth-inputs", "requests/")
    assert granted["Action"] == ["s3:GetObject"]
    assert granted["Resource"] == f"arn:aws:s3:::{allowed.bucket}/{allowed.prefix}*"


def test_the_health_check_is_a_real_worker_health_of_the_workers_heartbeat() -> None:
    container = worker(defaults())
    check = container["HealthCheck"]
    command = check["Command"]

    assert command[:2] == ["CMD", "azathoth"]

    health = build_parser().parse_args(command[2:])

    assert health.worker_action == "health"
    assert str(health.worker_heartbeat_file) == HEARTBEAT
    assert health.worker_max_age_seconds > check["Interval"]
    assert (check["Retries"], check["StartPeriod"]) == (3, 60)


def test_ecs_waits_longer_than_a_drain_takes_before_killing_a_worker() -> None:
    stop = worker(defaults())["StopTimeout"]

    assert MAX_WAIT_SECONDS < stop <= 120


def test_the_root_is_read_only_with_a_writable_tmp() -> None:
    container = worker(defaults())
    definition = resolve(properties("TaskDefinition"), defaults())

    assert container["ReadonlyRootFilesystem"] is True
    assert container["MountPoints"] == [
        {"SourceVolume": "tmp", "ContainerPath": "/tmp", "ReadOnly": False}
    ]
    assert definition["Volumes"] == [{"Name": "tmp"}]
    assert definition["RequiresCompatibilities"] == ["FARGATE"]
    assert definition["NetworkMode"] == "awsvpc"


def test_resolved_content_is_kept_in_the_stacks_bucket() -> None:
    environment = {item["Name"]: item["Value"] for item in worker(defaults())["Environment"]}
    location = S3ContentLocation.parse(environment["AZATHOTH_CONTENT_STORE"])

    assert location == S3ContentLocation(bucket=placeholders()["ContentBucket"], prefix="evidence")
    assert environment["AWS_REGION"] == "us-east-1"
    assert "AZATHOTH_BEDROCK" not in environment


def test_bedrock_is_turned_on_only_when_asked() -> None:
    environment = {item["Name"]: item["Value"] for item in worker(with_(**BEDROCK))["Environment"]}

    assert environment["AZATHOTH_BEDROCK"] == "1"


def test_the_database_url_and_the_openrouter_key_come_from_secrets() -> None:
    plain = worker(defaults())
    keyed = worker(with_(**OPENROUTER))

    assert plain["Secrets"] == [
        {"Name": "AZATHOTH_DATABASE", "ValueFrom": defaults()["DatabaseSecretArn"]}
    ]
    assert keyed["Secrets"][1] == {
        "Name": "OPENROUTER_API_KEY",
        "ValueFrom": OPENROUTER["OpenRouterSecretArn"],
    }

    for container in (plain, keyed):
        assert not {item["Name"] for item in container["Environment"]} & {
            "AZATHOTH_DATABASE",
            "OPENROUTER_API_KEY",
        }


def test_the_worker_logs_to_the_stacks_log_group() -> None:
    logging = worker(defaults())["LogConfiguration"]

    assert logging["LogDriver"] == "awslogs"
    assert logging["Options"]["awslogs-group"] == placeholders()["LogGroup"]


# Least privilege


def test_the_task_role_grants_exactly_the_calls_the_worker_makes() -> None:
    granted = statements(defaults())
    names = placeholders()

    assert set(granted) == {"TakeJobs", "SendResults", "KeepContent"}
    assert granted["TakeJobs"]["Action"] == [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
    ]
    assert granted["TakeJobs"]["Resource"] == names["JobQueue.Arn"]
    assert granted["SendResults"]["Action"] == ["sqs:SendMessage"]
    assert granted["SendResults"]["Resource"] == names["ResultQueue.Arn"]
    assert granted["KeepContent"]["Action"] == ["s3:GetObject", "s3:PutObject"]
    assert granted["KeepContent"]["Resource"] == f"{names['ContentBucket.Arn']}/evidence/*"


def test_every_optional_grant_appears_only_with_its_parameter() -> None:
    assert set(statements(with_(**EVERYTHING))) == {
        "TakeJobs",
        "SendResults",
        "KeepContent",
        "ReadInputs",
        "DiscoverModels",
        "InvokeModels",
    }


def test_the_bedrock_grants_are_the_bedrock_guides() -> None:
    guide = (PROJECT_ROOT / "docs" / "bedrock.md").read_text(encoding="utf-8")
    (policy,) = [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", guide, re.DOTALL)
        if '"Sid": "DiscoverModels"' in block
    ]
    documented = {statement["Sid"]: statement["Action"] for statement in policy["Statement"]}
    granted = statements(with_(**BEDROCK))

    assert granted["DiscoverModels"]["Action"] == documented["DiscoverModels"]
    assert granted["InvokeModels"]["Action"] == documented["InvokeModels"]
    assert granted["InvokeModels"]["Resource"] == [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:*:123456789012:inference-profile/*",
    ]


def test_no_grant_names_every_action_and_only_model_discovery_every_resource() -> None:
    for sid, statement in statements(with_(**EVERYTHING)).items():
        actions = statement["Action"]

        assert not any(action.endswith("*") for action in actions), sid

        if statement["Resource"] == "*":
            assert sid == "DiscoverModels"


def test_ecs_reads_only_the_secrets_it_injects() -> None:
    def secrets(parameters: dict[str, Any]) -> Any:
        (policy,) = resolve(properties("ExecutionRole"), parameters)["Policies"]
        (statement,) = policy["PolicyDocument"]["Statement"]

        assert statement["Action"] == "secretsmanager:GetSecretValue"

        return statement["Resource"]

    assert secrets(defaults()) == [defaults()["DatabaseSecretArn"]]
    assert secrets(with_(**OPENROUTER)) == [
        defaults()["DatabaseSecretArn"],
        OPENROUTER["OpenRouterSecretArn"],
    ]


@pytest.mark.parametrize("role", ["ExecutionRole", "TaskRole"])
def test_only_ecs_tasks_assume_the_roles(
    role: str,
) -> None:
    (statement,) = properties(role)["AssumeRolePolicyDocument"]["Statement"]

    assert statement == {
        "Effect": "Allow",
        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }


def test_the_workers_accept_no_connections() -> None:
    group = properties("WorkerSecurityGroup")

    assert "SecurityGroupIngress" not in group


# The service and its scaling


def test_the_service_runs_the_workers_on_fargate_and_rolls_back_a_broken_deploy() -> None:
    service = resolve(properties("Service"), defaults())

    assert service["LaunchType"] == "FARGATE"
    assert service["DesiredCount"] == 1
    assert service["EnableExecuteCommand"] is False
    assert service["DeploymentConfiguration"]["DeploymentCircuitBreaker"] == {
        "Enable": True,
        "Rollback": True,
    }
    assert service["NetworkConfiguration"]["AwsvpcConfiguration"] == {
        "AssignPublicIp": "DISABLED",
        "Subnets": defaults()["SubnetIds"],
        "SecurityGroups": [placeholders()["WorkerSecurityGroup"]],
    }


def test_the_service_scales_between_its_bounds() -> None:
    target = resolve(properties("ScalableTarget"), with_(MinTasks=0, MaxTasks=8))

    assert (target["MinCapacity"], target["MaxCapacity"]) == (0, 8)
    assert target["ScalableDimension"] == "ecs:service:DesiredCount"
    assert target["ResourceId"] == "service/<Cluster>/<Service.Name>"


def test_a_backlog_adds_a_worker() -> None:
    alarm = resolve(properties("BacklogAlarm"), defaults())

    assert alarm["MetricName"] == "ApproximateNumberOfMessagesVisible"
    assert alarm["Dimensions"] == [{"Name": "QueueName", "Value": "jobqueue"}]
    assert (alarm["Threshold"], alarm["ComparisonOperator"]) == (
        10,
        "GreaterThanOrEqualToThreshold",
    )
    assert alarm["AlarmActions"] == [placeholders()["ScaleOutPolicy"]]


def test_a_queue_with_nothing_waiting_or_running_removes_a_worker() -> None:
    alarm = resolve(properties("IdleAlarm"), defaults())
    metrics = {metric["Id"]: metric for metric in alarm["Metrics"]}

    assert metrics["waiting"]["MetricStat"]["Metric"]["MetricName"] == (
        "ApproximateNumberOfMessagesVisible"
    )
    assert metrics["running"]["MetricStat"]["Metric"]["MetricName"] == (
        "ApproximateNumberOfMessagesNotVisible"
    )
    assert metrics["busy"]["Expression"] == "waiting + running"
    assert [metric["ReturnData"] for metric in alarm["Metrics"]] == [False, False, True]
    assert (alarm["Threshold"], alarm["ComparisonOperator"], alarm["EvaluationPeriods"]) == (
        0,
        "LessThanOrEqualToThreshold",
        5,
    )
    assert alarm["AlarmActions"] == [placeholders()["ScaleInPolicy"]]


# The outputs


def test_the_outputs_name_everything_the_guide_uses() -> None:
    assert set(template()["Outputs"]) == {
        "JobQueueUrl",
        "ResultQueueUrl",
        "DeadLetterQueueUrl",
        "ContentBucketName",
        "ClusterName",
        "ServiceName",
        "TaskDefinitionArn",
        "SecurityGroupId",
        "LogGroupName",
    }


def test_the_conditions_follow_their_parameters() -> None:
    assert conditions(defaults()) == {
        "HasInputBucket": False,
        "HasOpenRouter": False,
        "UseBedrock": False,
    }
    assert conditions(with_(**EVERYTHING)) == {
        "HasInputBucket": True,
        "HasOpenRouter": True,
        "UseBedrock": True,
    }
