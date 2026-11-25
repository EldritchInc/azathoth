"""Tests proving the model-watch example's tools: what each finds, records and authorizes.

Each tool is a process tool whose source reads its input on stdin. Its
functions are tested by loading the source as a module, with stand-ins for
the instance; each tool is also run as a workflow runs it, against a real
instance with no provider, to prove its wiring.
"""

import ast
import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest

from azathoth import api
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    RuntimeToolExecutor,
    ToolDocument,
    decode_tool_document,
    encode_tool_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLE = PROJECT_ROOT / "examples" / "model-watch"

DISCOVER_DOCUMENT = EXAMPLE / "tools" / "discover-new-models.json"

PORTFOLIO_DOCUMENT = EXAMPLE / "tools" / "add-to-local-portfolio.json"

TRIAGE = PROJECT_ROOT / "examples" / "ticket-triage"

CLASSIFY_WORKFLOW_ID = "f1000000-0000-4000-8000-000000000010"

CLASSIFY_BENCHMARK_ID = "f1000000-0000-4000-8000-000000000050"

TONIGHT = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)

LAST_NIGHT = "2026-11-24T03:00:00+00:00"

GRANTS = (
    "AZATHOTH_DATABASE",
    "AZATHOTH_AUTHOR",
    "OPENROUTER_API_KEY",
    "AZATHOTH_BEDROCK",
    "AZATHOTH_BEDROCK_PRICING",
    "AWS_*",
)

TARGET = {
    "workflow": CLASSIFY_WORKFLOW_ID,
    "benchmark": CLASSIFY_BENCHMARK_ID,
    "target_latency": 5,
    "target_cost": 0.01,
}


def read_tool(
    path: Path,
) -> ToolDocument:
    return decode_tool_document(path.read_text(encoding="utf-8"))


def loaded(
    path: Path,
) -> ModuleType:
    """Return a tool's source as a module, without running it as the step would."""

    source = read_tool(path).implementations[0].source
    module = ModuleType(path.stem.replace("-", "_"))

    assert source is not None

    exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102

    return module


@pytest.fixture(scope="module")
def discovering() -> ModuleType:
    return loaded(DISCOVER_DOCUMENT)


@pytest.fixture(scope="module")
def adding() -> ModuleType:
    return loaded(PORTFOLIO_DOCUMENT)


def served(
    identifier: str,
    *,
    modalities: tuple[str, ...] = ("text",),
) -> dict[str, Any]:
    """Return a model as `azathoth.api` lists it, dumped to JSON."""

    provider, _, model = identifier.partition("/")

    return {
        "identifier": identifier,
        "provider": provider,
        "model": model,
        "display_name": model,
        "input_modalities": list(modalities),
        "output_modalities": list(modalities),
        "capabilities": [],
        "context_window_tokens": 128000,
        "maximum_output_tokens": None,
        "input_usd_per_million_tokens": 0.5,
        "output_usd_per_million_tokens": 1.5,
        "authorized": False,
        "command": f"azathoth model show {identifier}",
    }


def ledger(
    **models: str,
) -> dict[str, Any]:
    """Return a ledger holding models by identifier, with `__` for `/`, each with its status."""

    return {
        "version": 1,
        "checked_at": LAST_NIGHT,
        "models": {
            name.replace("__", "/"): {"seen": LAST_NIGHT, "status": status}
            for name, status in models.items()
        },
    }


def discover(
    discovering: ModuleType,
    models: list[dict[str, Any]],
    held: dict[str, Any] | None,
    *,
    providers: tuple[str, ...] = (),
    modalities: tuple[str, ...] = ("text",),
    limit: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    said, after = discovering.discover(
        models,
        held,
        providers=providers,
        modalities=modalities,
        limit=limit,
        now=TONIGHT,
    )

    return said, after


# The documents


@pytest.mark.parametrize("path", [DISCOVER_DOCUMENT, PORTFOLIO_DOCUMENT])
def test_each_tool_document_is_canonical(
    path: Path,
) -> None:
    assert f"{encode_tool_document(read_tool(path))}\n" == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [DISCOVER_DOCUMENT, PORTFOLIO_DOCUMENT])
def test_each_tool_runs_python_with_the_instance_and_providers_granted(
    path: Path,
) -> None:
    (implementation,) = read_tool(path).implementations

    assert implementation.runtime == PROCESS_TOOL_RUNTIME
    assert implementation.command == ("python",)
    assert implementation.environment == GRANTS


def test_the_tools_have_the_ids_the_example_gives_them() -> None:
    assert read_tool(DISCOVER_DOCUMENT).definition.id == UUID(
        "d7000000-0000-4000-8000-000000000001"
    )
    assert read_tool(PORTFOLIO_DOCUMENT).definition.id == UUID(
        "d7000000-0000-4000-8000-000000000002"
    )


# Discover New Models


def test_the_first_run_records_every_model_served_as_the_baseline_and_tries_none(
    discovering: ModuleType,
) -> None:
    said, after = discover(discovering, [served("acme/a"), served("acme/b")], None)

    assert said == {
        "new_models": [],
        "new": 0,
        "waiting": 0,
        "first_run": True,
        "message": (
            "Watching from now: 2 models served tonight are the baseline, and only models "
            "released after them are tried."
        ),
    }
    assert after == {
        "version": 1,
        "checked_at": "2026-11-25T03:00:00+00:00",
        "models": {
            "acme/a": {"seen": "2026-11-25T03:00:00+00:00", "status": "baseline"},
            "acme/b": {"seen": "2026-11-25T03:00:00+00:00", "status": "baseline"},
        },
    }


def test_a_new_model_is_one_served_that_the_ledger_never_held(
    discovering: ModuleType,
) -> None:
    held = ledger(acme__a="baseline", acme__b="rejected", acme__c="proposed")
    tonight = [served("acme/d"), served("acme/c"), served("acme/b"), served("acme/a")]

    said, after = discover(discovering, tonight, held)

    assert [model["identifier"] for model in said["new_models"]] == ["acme/d"]
    assert said["message"] == f"1 new model since {LAST_NIGHT}."
    assert said["first_run"] is False
    assert after["models"] == held["models"]
    assert after["checked_at"] == "2026-11-25T03:00:00+00:00"


def test_a_model_rejected_a_week_ago_never_comes_back(
    discovering: ModuleType,
) -> None:
    said, _ = discover(discovering, [served("acme/old")], ledger(acme__old="rejected"))

    assert said["new_models"] == []
    assert said["message"] == f"0 new models since {LAST_NIGHT}."


def test_new_models_are_tried_in_identifier_order_up_to_the_limit_and_the_rest_wait(
    discovering: ModuleType,
) -> None:
    tonight = [served(f"acme/m{number}") for number in (4, 1, 3, 2)]

    said, after = discover(discovering, tonight, ledger(), limit=2)

    assert [model["identifier"] for model in said["new_models"]] == ["acme/m1", "acme/m2"]
    assert (said["new"], said["waiting"]) == (4, 2)
    assert said["message"] == (
        f"4 new models since {LAST_NIGHT}. Trying 2 tonight; 2 wait for the next run."
    )
    assert after["models"] == {}


def test_only_the_providers_and_modalities_watched_are_new(
    discovering: ModuleType,
) -> None:
    tonight = [
        served("acme/text"),
        served("other/text"),
        served("acme/image-only", modalities=("image",)),
        served("acme/both", modalities=("text", "image")),
    ]

    said, _ = discover(discovering, tonight, ledger(), providers=("acme",))
    images, _ = discover(discovering, tonight, ledger(), modalities=("text", "image"))

    assert [model["identifier"] for model in said["new_models"]] == ["acme/both", "acme/text"]
    assert [model["identifier"] for model in images["new_models"]] == ["acme/both"]


def test_a_new_model_is_described_by_what_its_provider_publishes(
    discovering: ModuleType,
) -> None:
    said, _ = discover(discovering, [served("acme/a")], ledger())

    assert said["new_models"] == [
        {
            "identifier": "acme/a",
            "provider": "acme",
            "display_name": "a",
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "context_window_tokens": 128000,
            "input_usd_per_million_tokens": 0.5,
            "output_usd_per_million_tokens": 1.5,
        }
    ]


@pytest.mark.parametrize(
    ("targets", "message"),
    [
        (None, "Name at least one target: a workflow, and the benchmark to try new models on."),
        ([], "Name at least one target: a workflow, and the benchmark to try new models on."),
        (["x"], "Target 1 is not an object."),
        ([{**TARGET, "workflow": ""}], "Target 1 names no workflow."),
        ([{k: v for k, v in TARGET.items() if k != "benchmark"}], "Target 1 names no benchmark."),
        ([{**TARGET, "target_latency": 0}], "Target 1's target_latency is not a number above 0."),
        ([{**TARGET, "target_cost": True}], "Target 1's target_cost is not a number above 0."),
        (
            [TARGET, TARGET],
            f"Target 2 names workflow {CLASSIFY_WORKFLOW_ID} again; name each once.",
        ),
    ],
)
def test_targets_that_are_not_ones_are_refused_by_their_place(
    discovering: ModuleType,
    targets: object,
    message: str,
) -> None:
    with pytest.raises(discovering.WatchError) as caught:
        discovering.check_targets(targets)

    assert str(caught.value) == message


@pytest.mark.parametrize("limit", [0, -1, 2.5, True, "5"])
def test_a_limit_that_is_not_a_count_is_refused(
    discovering: ModuleType,
    limit: object,
) -> None:
    with pytest.raises(discovering.WatchError) as caught:
        discovering.check_limit(limit)

    assert str(caught.value) == "The limit is how many new models to try a night: 1 or more."


def test_the_limit_is_five_unless_named(
    discovering: ModuleType,
) -> None:
    assert discovering.check_limit(None) == 5
    assert discovering.check_limit(2) == 2


def test_the_ledger_is_written_whole_and_read_back(
    discovering: ModuleType,
    tmp_path: Path,
) -> None:
    path = tmp_path / "watch" / "ledger.json"

    assert discovering.read_ledger(path) is None

    discovering.write_ledger(path, ledger(acme__a="baseline"))

    assert discovering.read_ledger(path) == ledger(acme__a="baseline")
    assert [child.name for child in path.parent.iterdir()] == ["ledger.json"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "could not be read as JSON."),
        ('{"version": 2, "models": {}}', "is not a model-watch ledger."),
        ('{"version": 1, "models": []}', "is not a model-watch ledger."),
    ],
)
def test_a_ledger_that_is_not_one_is_refused(
    discovering: ModuleType,
    tmp_path: Path,
    text: str,
    message: str,
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(discovering.WatchError) as caught:
        discovering.read_ledger(path)

    assert str(caught.value) == f"The ledger at {path} {message}"


class Holding:
    """A stand-in for an instance's workflows or benchmarks, holding some IDs."""

    def __init__(
        self,
        *held: str,
    ) -> None:
        self.held = {UUID(each) for each in held}

    def get(
        self,
        identifier: UUID,
    ) -> object:
        if identifier not in self.held:
            raise api.NotFoundError(f"{identifier} was not found.")

        return object()


class Instance:
    def __init__(
        self,
        workflows: Holding,
        benchmarks: Holding,
    ) -> None:
        self.workflows = workflows
        self.benchmarks = benchmarks


def test_a_target_this_instance_does_not_hold_is_refused(
    discovering: ModuleType,
) -> None:
    instance = Instance(Holding(CLASSIFY_WORKFLOW_ID), Holding())

    discovering.check_held(
        Instance(Holding(CLASSIFY_WORKFLOW_ID), Holding(CLASSIFY_BENCHMARK_ID)), [TARGET]
    )

    with pytest.raises(discovering.WatchError) as caught:
        discovering.check_held(instance, [TARGET])

    assert str(caught.value) == (
        f"Target 1's benchmark {CLASSIFY_BENCHMARK_ID} is not on this instance."
    )

    with pytest.raises(discovering.WatchError) as caught:
        discovering.check_held(instance, [{**TARGET, "workflow": "classify"}])

    assert str(caught.value) == "Target 1's workflow classify is not an ID."


# Add to Local Portfolio


class Portfolio:
    """A stand-in for an instance's portfolio: what it holds, and what providers serve."""

    def __init__(
        self,
        *,
        authorized: tuple[str, ...] = (),
        serving: tuple[str, ...] = (),
    ) -> None:
        self.authorized = list(authorized)
        self.serving = set(serving)

    def add(
        self,
        identifier: str,
    ) -> None:
        if identifier in self.authorized:
            raise api.ConflictError(f"Model {identifier!r} is already authorized.")

        if identifier not in self.serving:
            raise api.NotFoundError(f"Model {identifier!r} is not available.")

        self.authorized.append(identifier)


def add(
    adding: ModuleType,
    portfolio: Portfolio,
    identifiers: list[str],
) -> dict[str, Any]:
    said: dict[str, Any] = adding.add_to_portfolio(
        portfolio,
        identifiers,
        conflict=api.ConflictError,
        missing=api.NotFoundError,
    )

    return said


def test_new_models_are_authorized_on_this_machine_and_production_stays_locked(
    adding: ModuleType,
) -> None:
    portfolio = Portfolio(serving=("acme/a", "acme/b"))

    assert add(adding, portfolio, ["acme/a", "acme/b"]) == {
        "added": ["acme/a", "acme/b"],
        "already": [],
        "unavailable": [],
        "message": "Approved 2 models on this machine for testing. Production stays locked.",
    }
    assert portfolio.authorized == ["acme/a", "acme/b"]


def test_a_model_authorized_already_or_no_longer_served_is_left_and_said(
    adding: ModuleType,
) -> None:
    portfolio = Portfolio(authorized=("acme/a",), serving=("acme/a", "acme/b"))

    said = add(adding, portfolio, ["acme/a", "acme/b", "acme/gone"])

    assert (said["added"], said["already"], said["unavailable"]) == (
        ["acme/b"],
        ["acme/a"],
        ["acme/gone"],
    )
    assert said["message"] == (
        "Approved 1 model on this machine for testing. 1 was already approved here. "
        "1 is no longer served. Production stays locked."
    )


@pytest.mark.parametrize("path", [DISCOVER_DOCUMENT, PORTFOLIO_DOCUMENT])
def test_no_tool_pushes_promotes_or_reaches_a_remote(
    path: Path,
) -> None:
    source = read_tool(path).implementations[0].source or ""
    named = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute | ast.Name)
    }

    assert named.isdisjoint({"push", "pull", "promote", "connect", "remote", "remotes"})


# As a workflow runs them


@pytest.fixture
def instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    """Return an instance holding the ticket classifier and its benchmark, with no provider."""

    database = tmp_path / "azathoth.db"
    api.initialize(database)

    with api.open(database, author="Eris <eris@eldritch.example>") as opened:
        opened.workflows.import_document(
            (TRIAGE / "workflows" / "classify-ticket.json").read_text(encoding="utf-8")
        )
        opened.benchmarks.import_document(
            (TRIAGE / "benchmarks" / "classify-ticket.json").read_text(encoding="utf-8")
        )

    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))
    monkeypatch.setenv("AZATHOTH_AUTHOR", "Eris <eris@eldritch.example>")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("AZATHOTH_BEDROCK", raising=False)

    yield database


def run_tool(
    path: Path,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    output = asyncio.run(RuntimeToolExecutor().execute(read_tool(path).implementations[0], inputs))

    return dict(output)


def test_discover_runs_as_a_step_and_records_its_first_run(
    instance: Path,
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.json"

    said = run_tool(DISCOVER_DOCUMENT, {"ledger": str(path), "targets": [TARGET]})

    assert said["first_run"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["models"] == {}


def test_discover_fails_its_step_on_a_target_the_instance_does_not_hold(
    instance: Path,
    tmp_path: Path,
) -> None:
    from azathoth.tools import ToolExecutionError

    path = tmp_path / "ledger.json"
    missing = {**TARGET, "benchmark": "f1000000-0000-4000-8000-000000000999"}

    with pytest.raises(ToolExecutionError) as caught:
        run_tool(DISCOVER_DOCUMENT, {"ledger": str(path), "targets": [missing]})

    assert str(caught.value).endswith(
        "Target 1's benchmark f1000000-0000-4000-8000-000000000999 is not on this instance."
    )
    assert not path.exists()


def test_add_to_local_portfolio_runs_as_a_step(
    instance: Path,
) -> None:
    said = run_tool(PORTFOLIO_DOCUMENT, {"new_models": [{"identifier": "acme/gone"}]})

    assert said["unavailable"] == ["acme/gone"]
    assert said["added"] == []
