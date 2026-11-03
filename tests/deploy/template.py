"""Reading the CloudFormation template, and resolving it as a stack would (ADR 0109).

The template writes every intrinsic in its long form, so plain YAML reads
it. PyYAML ships no types, so it is imported by name. `resolve` evaluates
the intrinsics the template uses for one set of parameters, with each
resource standing for a recognizable placeholder.
"""

import importlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[2]

TEMPLATE = PROJECT_ROOT / "deploy" / "aws" / "azathoth.yaml"

REGION = "us-east-1"

ACCOUNT = "123456789012"

PSEUDO_PARAMETERS = {
    "AWS::Region": REGION,
    "AWS::Partition": "aws",
    "AWS::AccountId": ACCOUNT,
    "AWS::StackName": "azathoth",
}

NO_VALUE = object()
"""What `{"Ref": "AWS::NoValue"}` resolves to, before it is dropped."""

SUB_NAME = re.compile(r"\$\{([^}]+)\}")


def template() -> dict[str, Any]:
    """Return the template as plain data."""

    loaded = importlib.import_module("yaml").safe_load(TEMPLATE.read_text(encoding="utf-8"))

    assert isinstance(loaded, dict)

    return loaded


def resources() -> dict[str, Any]:
    """Return the template's resources by logical ID."""

    found = template()["Resources"]

    assert isinstance(found, dict)

    return found


def properties(
    name: str,
) -> dict[str, Any]:
    """Return one resource's properties."""

    found = resources()[name].get("Properties", {})

    assert isinstance(found, dict)

    return found


def placeholders() -> dict[str, str]:
    """Return what each resource's `Ref` and attributes stand for."""

    values: dict[str, str] = {}

    for name, resource in resources().items():
        kind = resource["Type"]

        if kind == "AWS::SQS::Queue":
            values[name] = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/{name.lower()}"
            values[f"{name}.Arn"] = f"arn:aws:sqs:{REGION}:{ACCOUNT}:{name.lower()}"
            values[f"{name}.QueueName"] = name.lower()
        elif kind == "AWS::S3::Bucket":
            values[name] = f"azathoth-{name.lower()}"
            values[f"{name}.Arn"] = f"arn:aws:s3:::azathoth-{name.lower()}"
        else:
            values[name] = f"<{name}>"
            values[f"{name}.Arn"] = f"<{name}.Arn>"
            values[f"{name}.Name"] = f"<{name}.Name>"

    return values


def conditions(
    parameters: Mapping[str, Any],
) -> dict[str, bool]:
    """Return the template's conditions for one set of parameters."""

    refs = {**PSEUDO_PARAMETERS, **parameters}

    return {
        name: bool(_evaluate(body, refs, {}))
        for name, body in template().get("Conditions", {}).items()
    }


def resolve(
    node: Any,
    parameters: Mapping[str, Any],
) -> Any:
    """Resolve the intrinsics in one part of the template for some parameters."""

    refs = {**PSEUDO_PARAMETERS, **placeholders(), **parameters}

    return _drop(_evaluate(node, refs, conditions(parameters)))


def defaults() -> dict[str, Any]:
    """Return every parameter's default, and a value for those without one."""

    values: dict[str, Any] = {
        name: parameter.get("Default") for name, parameter in template()["Parameters"].items()
    }
    values.update(
        VpcId="vpc-0123456789abcdef0",
        SubnetIds=["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"],
        DatabaseSecretArn=f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:azathoth-db-AbCdEf",
    )

    return values


def _evaluate(
    node: Any,
    refs: Mapping[str, Any],
    known: Mapping[str, bool],
) -> Any:
    """Evaluate the intrinsics in one node."""

    if isinstance(node, list):
        return [_evaluate(item, refs, known) for item in node]

    if not isinstance(node, dict):
        return node

    if set(node) == {"Ref"}:
        if node["Ref"] == "AWS::NoValue":
            return NO_VALUE

        return refs[node["Ref"]]

    if set(node) == {"Fn::GetAtt"}:
        resource, attribute = node["Fn::GetAtt"]

        return refs[f"{resource}.{attribute}"]

    if set(node) == {"Fn::Sub"}:
        return SUB_NAME.sub(lambda match: str(refs[match.group(1)]), node["Fn::Sub"])

    if set(node) == {"Fn::If"}:
        condition, then, otherwise = node["Fn::If"]

        return _evaluate(then if known[condition] else otherwise, refs, known)

    if set(node) == {"Fn::Equals"}:
        left, right = _evaluate(node["Fn::Equals"], refs, known)

        return left == right

    if set(node) == {"Fn::Not"}:
        (inner,) = node["Fn::Not"]

        return not _evaluate(inner, refs, known)

    return {key: _evaluate(value, refs, known) for key, value in node.items()}


def _drop(
    node: Any,
) -> Any:
    """Remove every `AWS::NoValue`, as CloudFormation does."""

    if isinstance(node, list):
        return [_drop(item) for item in node if item is not NO_VALUE]

    if isinstance(node, dict):
        return {key: _drop(value) for key, value in node.items() if value is not NO_VALUE}

    return node


def references(
    node: Any,
) -> set[str]:
    """Return every name a `Ref`, `Fn::GetAtt` or `Fn::Sub` in a node points at."""

    if isinstance(node, list):
        return set().union(*(references(item) for item in node)) if node else set()

    if not isinstance(node, dict):
        return set()

    if set(node) == {"Ref"}:
        return {node["Ref"]}

    if set(node) == {"Fn::GetAtt"}:
        return {node["Fn::GetAtt"][0]}

    if set(node) == {"Fn::Sub"}:
        return {name.split(".")[0] for name in SUB_NAME.findall(node["Fn::Sub"])}

    return set().union(*(references(value) for value in node.values())) if node else set()


def conditions_used(
    node: Any,
) -> set[str]:
    """Return every condition an `Fn::If` in a node, or a resource's `Condition`, names."""

    if isinstance(node, list):
        return set().union(*(conditions_used(item) for item in node)) if node else set()

    if not isinstance(node, dict):
        return set()

    found = {node["Fn::If"][0]} if set(node) == {"Fn::If"} else set()

    return found.union(*(conditions_used(value) for value in node.values()))
