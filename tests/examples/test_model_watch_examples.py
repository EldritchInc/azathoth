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

import jsonschema
import pytest

from azathoth import api
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    RuntimeToolExecutor,
    ToolDocument,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowNamedValueReference,
    WorkflowSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLE = PROJECT_ROOT / "examples" / "model-watch"

DISCOVER_DOCUMENT = EXAMPLE / "tools" / "discover-new-models.json"

PORTFOLIO_DOCUMENT = EXAMPLE / "tools" / "add-to-local-portfolio.json"

BENCHMARK_DOCUMENT = EXAMPLE / "tools" / "benchmark-against-new-models.json"

COMPARE_DOCUMENT = EXAMPLE / "tools" / "compare-cost-and-quality.json"

PROPOSE_DOCUMENT = EXAMPLE / "tools" / "propose-winner.json"

TOOL_DOCUMENTS = (
    DISCOVER_DOCUMENT,
    PORTFOLIO_DOCUMENT,
    BENCHMARK_DOCUMENT,
    COMPARE_DOCUMENT,
    PROPOSE_DOCUMENT,
)

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


@pytest.mark.parametrize("path", TOOL_DOCUMENTS)
def test_each_tool_document_is_canonical(
    path: Path,
) -> None:
    assert f"{encode_tool_document(read_tool(path))}\n" == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", TOOL_DOCUMENTS)
def test_each_tool_runs_python_with_the_instance_and_providers_granted(
    path: Path,
) -> None:
    (implementation,) = read_tool(path).implementations

    assert implementation.runtime == PROCESS_TOOL_RUNTIME
    assert implementation.command == ("python",)
    assert implementation.environment == GRANTS


def test_the_tools_have_the_ids_the_example_gives_them() -> None:
    assert [read_tool(path).definition.id for path in TOOL_DOCUMENTS] == [
        UUID(f"d7000000-0000-4000-8000-00000000000{number}") for number in range(1, 6)
    ]


def test_benchmarking_may_take_an_hour_and_every_other_step_two_minutes() -> None:
    assert [read_tool(path).implementations[0].timeout_seconds for path in TOOL_DOCUMENTS] == [
        120.0,
        120.0,
        3600.0,
        120.0,
        120.0,
    ]


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


@pytest.mark.parametrize("path", TOOL_DOCUMENTS)
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

    said = run_tool(DISCOVER_DOCUMENT, {"watch": {"ledger": str(path), "targets": [TARGET]}})

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
        run_tool(DISCOVER_DOCUMENT, {"watch": {"ledger": str(path), "targets": [missing]}})

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


# Benchmark Against New Models


@pytest.fixture(scope="module")
def benchmarking() -> ModuleType:
    return loaded(BENCHMARK_DOCUMENT)


@pytest.fixture(scope="module")
def comparing() -> ModuleType:
    return loaded(COMPARE_DOCUMENT)


@pytest.fixture(scope="module")
def proposing() -> ModuleType:
    return loaded(PROPOSE_DOCUMENT)


OTHER_WORKFLOW_ID = "f1000000-0000-4000-8000-000000000030"

OTHER_BENCHMARK_ID = "f1000000-0000-4000-8000-000000000060"

OTHER = {
    "workflow": OTHER_WORKFLOW_ID,
    "benchmark": OTHER_BENCHMARK_ID,
    "target_latency": 30,
    "target_cost": 0.1,
    "generations": 2,
}


class Summary:
    def __init__(
        self,
        experiment: UUID,
    ) -> None:
        self.winning_experiment_id = experiment


class Optimization:
    """A stand-in for an instance's optimization, recording each session it was asked for."""

    def __init__(
        self,
        *,
        failing: dict[str, Exception] | None = None,
    ) -> None:
        self.failing = failing or {}
        self.asked: list[tuple[UUID, UUID, float, float, int]] = []

    def optimize(
        self,
        workflow_id: UUID,
        benchmark_id: UUID,
        *,
        target_latency_seconds: float,
        target_cost_usd: float,
        generations: int,
    ) -> Summary:
        self.asked.append(
            (workflow_id, benchmark_id, target_latency_seconds, target_cost_usd, generations)
        )

        if str(workflow_id) in self.failing:
            raise self.failing[str(workflow_id)]

        return Summary(UUID(int=len(self.asked)))


def test_each_target_is_optimized_on_its_own_benchmark_and_targets(
    benchmarking: ModuleType,
) -> None:
    optimization = Optimization()

    said = benchmarking.benchmark(
        optimization, [TARGET, OTHER], [served("acme/a")], refused=api.ApiError
    )

    assert optimization.asked == [
        (UUID(CLASSIFY_WORKFLOW_ID), UUID(CLASSIFY_BENCHMARK_ID), 5.0, 0.01, 1),
        (UUID(OTHER_WORKFLOW_ID), UUID(OTHER_BENCHMARK_ID), 30.0, 0.1, 2),
    ]
    assert said == {
        "results": [
            {
                "workflow": CLASSIFY_WORKFLOW_ID,
                "benchmark": CLASSIFY_BENCHMARK_ID,
                "experiment": str(UUID(int=1)),
                "problem": None,
            },
            {
                "workflow": OTHER_WORKFLOW_ID,
                "benchmark": OTHER_BENCHMARK_ID,
                "experiment": str(UUID(int=2)),
                "problem": None,
            },
        ],
        "message": "Tested 1 new model on 2 workflows' own cases. Not a leaderboard.",
    }


def test_a_target_that_cannot_be_optimized_says_why_and_the_rest_go_on(
    benchmarking: ModuleType,
) -> None:
    optimization = Optimization(
        failing={CLASSIFY_WORKFLOW_ID: api.InvalidArgumentError("Benchmark has no cases.")}
    )

    said = benchmarking.benchmark(
        optimization,
        [TARGET, OTHER],
        [served("acme/a"), served("acme/b")],
        refused=api.ApiError,
    )

    assert [(result["experiment"], result["problem"]) for result in said["results"]] == [
        (None, "Benchmark has no cases."),
        (str(UUID(int=2)), None),
    ]
    assert said["message"] == (
        "Tested 2 new models on 1 workflow's own cases. Not a leaderboard. "
        "1 target could not be tried."
    )


# Compare Cost & Quality


def comparison(
    *,
    winner: tuple[bool, ...],
    baseline: tuple[bool, ...] | None,
    models: tuple[str, ...],
    cost_percent: float | None,
    experiment: UUID | None = None,
) -> dict[str, Any]:
    """Return an experiment comparison as `azathoth.api` dumps it to JSON."""

    experiment = UUID(int=1) if experiment is None else experiment

    return {
        "experiment_id": str(experiment),
        "workflow_id": CLASSIFY_WORKFLOW_ID,
        "baseline": None if baseline is None else "production",
        "reason": "Production already runs the winner." if baseline is None else None,
        "steps": [
            {"step_id": str(UUID(int=index)), "winner_model": model, "baseline_model": "x/y"}
            for index, model in enumerate(models)
        ],
        "cases": [
            {
                "case_id": str(UUID(int=index)),
                "winner_passed": passed,
                "baseline_passed": None if baseline is None else baseline[index],
            }
            for index, passed in enumerate(winner)
        ],
        "command": f"azathoth workflow promote {CLASSIFY_WORKFLOW_ID} --experiment {experiment}",
        "savings": None if cost_percent is None else {"cost_percent": cost_percent},
    }


class Dumped:
    def __init__(
        self,
        value: dict[str, Any],
    ) -> None:
        self.value = value

    def model_dump(
        self,
        *,
        mode: str,
    ) -> dict[str, Any]:
        return self.value


class Experiments:
    """A stand-in for an instance's experiments: each comparison, by experiment ID."""

    def __init__(
        self,
        compared: dict[UUID, dict[str, Any]],
    ) -> None:
        self.compared = compared

    def compare(
        self,
        experiment_id: UUID,
    ) -> Dumped:
        if experiment_id not in self.compared:
            raise api.ExperimentNotFoundError(f"Experiment {experiment_id} was not found.")

        return Dumped(self.compared[experiment_id])


def result_of(
    experiment: UUID | None,
    workflow: str = CLASSIFY_WORKFLOW_ID,
    problem: str | None = None,
) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "benchmark": CLASSIFY_BENCHMARK_ID,
        "experiment": None if experiment is None else str(experiment),
        "problem": problem,
    }


def test_a_winner_on_a_new_model_that_passes_as_many_cases_is_same_accuracy_cheaper(
    comparing: ModuleType,
) -> None:
    experiments = Experiments(
        {
            UUID(int=1): comparison(
                winner=(True, True, False),
                baseline=(True, True, False),
                models=("acme/new", "x/y"),
                cost_percent=62.4,
            )
        }
    )

    said = comparing.compare(
        experiments, [result_of(UUID(int=1))], [served("acme/new")], refused=api.ApiError
    )

    assert said["message"] == "Same accuracy. 62% cheaper."
    assert said["compared"] == [
        {
            "workflow": CLASSIFY_WORKFLOW_ID,
            "experiment": str(UUID(int=1)),
            "baseline": "production",
            "reason": None,
            "cases": 3,
            "winner_passed": 2,
            "baseline_passed": 2,
            "holds_quality": True,
            "new_models_used": ["acme/new"],
            "cost_percent": 62.4,
            "latency_percent": None,
            "command": (
                f"azathoth workflow promote {CLASSIFY_WORKFLOW_ID} --experiment {UUID(int=1)}"
            ),
            "problem": None,
        }
    ]


def test_the_best_saving_is_said_among_winners_that_hold_quality_on_a_new_model(
    comparing: ModuleType,
) -> None:
    experiments = Experiments(
        {
            UUID(int=1): comparison(
                winner=(True,), baseline=(True,), models=("acme/new",), cost_percent=30.0
            ),
            UUID(int=2): comparison(
                winner=(False,), baseline=(True,), models=("acme/new",), cost_percent=90.0
            ),
            UUID(int=3): comparison(
                winner=(True,), baseline=(True,), models=("x/old",), cost_percent=80.0
            ),
        }
    )
    results = [result_of(UUID(int=number), f"w{number}") for number in (1, 2, 3)]

    said = comparing.compare(experiments, results, [served("acme/new")], refused=api.ApiError)

    assert said["message"] == "Same accuracy. 30% cheaper."
    assert [target["holds_quality"] for target in said["compared"]] == [True, False, True]
    assert [target["new_models_used"] for target in said["compared"]] == [
        ["acme/new"],
        ["acme/new"],
        [],
    ]


def test_nothing_cheaper_on_a_new_model_is_said(
    comparing: ModuleType,
) -> None:
    experiments = Experiments(
        {
            UUID(int=1): comparison(
                winner=(True,), baseline=None, models=("x/old",), cost_percent=None
            )
        }
    )

    said = comparing.compare(
        experiments, [result_of(UUID(int=1))], [served("acme/new")], refused=api.ApiError
    )

    assert said["message"] == "No new model beat what runs now on cost at the same accuracy."
    assert said["compared"][0]["baseline_passed"] is None
    assert said["compared"][0]["holds_quality"] is True


def test_a_target_that_was_not_tried_or_cannot_be_compared_keeps_its_problem(
    comparing: ModuleType,
) -> None:
    said = comparing.compare(
        Experiments({}),
        [result_of(None, "w1", "Benchmark has no cases."), result_of(UUID(int=9), "w2")],
        [],
        refused=api.ApiError,
    )

    assert said["compared"] == [
        {"workflow": "w1", "problem": "Benchmark has no cases.", "new_models_used": []},
        {
            "workflow": "w2",
            "problem": f"Experiment {UUID(int=9)} was not found.",
            "new_models_used": [],
        },
    ]


# Propose Winner


class Removing:
    """A stand-in for an instance's portfolio, recording each model removed."""

    def __init__(
        self,
        *,
        authorized: tuple[str, ...],
        in_use: tuple[str, ...] = (),
    ) -> None:
        self.authorized = list(authorized)
        self.in_use = set(in_use)
        self.removed: list[str] = []

    def remove(
        self,
        identifier: str,
    ) -> None:
        if identifier not in self.authorized:
            raise api.NotFoundError(f"Model {identifier!r} is not authorized.")

        if identifier in self.in_use:
            raise api.ConflictError(f"Model {identifier!r} is in use.")

        self.authorized.remove(identifier)
        self.removed.append(identifier)


def compared_target(
    workflow: str,
    *,
    holds: bool = True,
    used: tuple[str, ...] = (),
    problem: str | None = None,
) -> dict[str, Any]:
    if problem is not None:
        return {"workflow": workflow, "problem": problem, "new_models_used": []}

    return {
        "workflow": workflow,
        "experiment": str(UUID(int=7)),
        "holds_quality": holds,
        "new_models_used": list(used),
        "cost_percent": 40.0,
        "command": f"azathoth workflow promote {workflow} --experiment {UUID(int=7)}",
        "problem": None,
    }


def propose(
    proposing: ModuleType,
    compared: list[dict[str, Any]],
    new: tuple[str, ...],
    portfolio: Removing,
    *,
    added: tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    said, after = proposing.propose(
        ledger(acme__old="baseline"),
        compared,
        [served(identifier) for identifier in new],
        set(new if added is None else added),
        portfolio,
        now=TONIGHT,
        missing=api.NotFoundError,
        refused=api.ApiError,
    )

    return said, after


def test_a_new_model_that_won_is_proposed_for_a_human_and_the_rest_rejected(
    proposing: ModuleType,
) -> None:
    portfolio = Removing(authorized=("acme/new", "acme/lost"))

    said, after = propose(
        proposing,
        [compared_target("w1", used=("acme/new",)), compared_target("w2")],
        ("acme/new", "acme/lost"),
        portfolio,
    )

    assert said == {
        "proposals": [
            {
                "workflow": "w1",
                "experiment": str(UUID(int=7)),
                "new_models_used": ["acme/new"],
                "cost_percent": 40.0,
                "command": f"azathoth workflow promote w1 --experiment {UUID(int=7)}",
            }
        ],
        "rejected": ["acme/lost"],
        "kept_authorized": [],
        "message": "Waiting for a human: 1 proposal. 1 new model rejected.",
    }
    assert portfolio.removed == ["acme/lost"]
    assert after["models"] == {
        "acme/old": {"seen": LAST_NIGHT, "status": "baseline"},
        "acme/new": {"seen": "2026-11-25T03:00:00+00:00", "status": "proposed", "won": ["w1"]},
        "acme/lost": {"seen": "2026-11-25T03:00:00+00:00", "status": "rejected"},
    }


def test_a_model_that_won_one_target_and_lost_another_is_kept_and_proposed(
    proposing: ModuleType,
) -> None:
    portfolio = Removing(authorized=("acme/new",))

    said, after = propose(
        proposing,
        [compared_target("w1", used=("acme/new",)), compared_target("w2", holds=False)],
        ("acme/new",),
        portfolio,
    )

    assert [proposal["workflow"] for proposal in said["proposals"]] == ["w1"]
    assert portfolio.removed == []
    assert after["models"]["acme/new"]["won"] == ["w1"]


def test_a_winner_that_loses_accuracy_is_never_proposed(
    proposing: ModuleType,
) -> None:
    said, after = propose(
        proposing,
        [compared_target("w1", holds=False, used=("acme/new",))],
        ("acme/new",),
        Removing(authorized=("acme/new",)),
    )

    assert said["proposals"] == []
    assert said["message"] == "Nothing to propose tonight. 1 new model rejected."
    assert after["models"]["acme/new"]["status"] == "rejected"


def test_only_the_models_the_watch_added_are_taken_back(
    proposing: ModuleType,
) -> None:
    portfolio = Removing(authorized=("acme/mine", "acme/added"))

    said, _ = propose(
        proposing,
        [compared_target("w1")],
        ("acme/mine", "acme/added"),
        portfolio,
        added=("acme/added",),
    )

    assert portfolio.removed == ["acme/added"]
    assert portfolio.authorized == ["acme/mine"]
    assert said["rejected"] == ["acme/mine", "acme/added"]


def test_a_rejected_model_that_cannot_be_taken_back_is_named(
    proposing: ModuleType,
) -> None:
    said, _ = propose(
        proposing,
        [compared_target("w1")],
        ("acme/used", "acme/gone"),
        Removing(authorized=("acme/used",), in_use=("acme/used",)),
    )

    assert said["kept_authorized"] == ["acme/used"]


def test_when_a_target_was_not_tried_the_losers_are_taken_back_but_tried_again(
    proposing: ModuleType,
) -> None:
    portfolio = Removing(authorized=("acme/new", "acme/lost"))

    said, after = propose(
        proposing,
        [
            compared_target("w1", used=("acme/new",)),
            compared_target("w2", problem="Benchmark has no cases."),
        ],
        ("acme/new", "acme/lost"),
        portfolio,
    )

    assert portfolio.removed == ["acme/lost"]
    assert "acme/lost" not in after["models"]
    assert after["models"]["acme/new"]["status"] == "proposed"
    assert said["message"] == (
        "Waiting for a human: 1 proposal. 1 new model rejected. "
        "Not every target was tried, so the rejected are tried again."
    )


def test_propose_never_promotes(
    proposing: ModuleType,
) -> None:
    assert "production" not in {
        node.attr
        for node in ast.walk(ast.parse(read_tool(PROPOSE_DOCUMENT).implementations[0].source or ""))
        if isinstance(node, ast.Attribute)
    }


# The later steps, as a workflow runs them


def test_benchmark_runs_as_a_step_and_says_a_target_it_cannot_try(
    instance: Path,
) -> None:
    said = run_tool(
        BENCHMARK_DOCUMENT,
        {"watch": {"ledger": "unused", "targets": [TARGET]}, "new_models": [served("acme/new")]},
    )

    (result,) = said["results"]

    assert result["experiment"] is None
    assert result["problem"]


def test_compare_runs_as_a_step(
    instance: Path,
) -> None:
    said = run_tool(
        COMPARE_DOCUMENT,
        {"results": [result_of(UUID(int=9))], "new_models": []},
    )

    assert said["compared"][0]["problem"] == f"Experiment {UUID(int=9)} was not found."


def test_propose_runs_as_a_step_and_writes_the_ledger(
    instance: Path,
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger()), encoding="utf-8")

    said = run_tool(
        PROPOSE_DOCUMENT,
        {
            "watch": {"ledger": str(path), "targets": [TARGET]},
            "compared": [compared_target("w1")],
            "new_models": [{"identifier": "acme/lost"}],
            "added": ["acme/lost"],
            "discovered": "1 new model since last night.",
            "approved": "Approved 1 model on this machine for testing.",
            "tested": "Tested 1 new model.",
            "measured": "No new model beat what runs now on cost at the same accuracy.",
        },
    )

    assert said["summary"] == [
        "1 new model since last night.",
        "Approved 1 model on this machine for testing.",
        "Tested 1 new model.",
        "No new model beat what runs now on cost at the same accuracy.",
        "Nothing to propose tonight. 1 new model rejected.",
    ]
    assert said["rejected"] == ["acme/lost"]
    assert said["kept_authorized"] == []
    assert json.loads(path.read_text(encoding="utf-8"))["models"]["acme/lost"]["status"] == (
        "rejected"
    )


# Nothing new


def test_nothing_is_optimized_on_a_night_with_nothing_new(
    benchmarking: ModuleType,
) -> None:
    optimization = Optimization()

    said = benchmarking.benchmark(optimization, [TARGET], [], refused=api.ApiError)

    assert said == {"results": [], "message": "Nothing new to test tonight."}
    assert optimization.asked == []


def test_nothing_is_compared_on_a_night_with_nothing_new(
    comparing: ModuleType,
) -> None:
    said = comparing.compare(Experiments({}), [], [], refused=api.ApiError)

    assert said == {"compared": [], "message": "Nothing new to compare tonight."}


def test_nothing_is_proposed_or_recorded_on_a_night_with_nothing_new(
    proposing: ModuleType,
) -> None:
    portfolio = Removing(authorized=())

    said, after = propose(proposing, [], (), portfolio)

    assert said == {
        "proposals": [],
        "rejected": [],
        "kept_authorized": [],
        "message": "Nothing to propose tonight.",
    }
    assert after == ledger(acme__old="baseline")


# The workflow


WORKFLOW_DOCUMENT = EXAMPLE / "workflows" / "model-watch.json"

WATCH_DOCUMENT = EXAMPLE / "watch.json"

REEL_STEPS = (
    "Discover New Models",
    "Add to Local Portfolio",
    "Benchmark Against New Models",
    "Compare Cost & Quality",
    "Propose Winner",
)


def read_workflow() -> WorkflowSpecification:
    return decode_workflow_document(WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))


def test_the_workflow_document_is_canonical() -> None:
    assert f"{encode_workflow_document(read_workflow())}\n" == WORKFLOW_DOCUMENT.read_text(
        encoding="utf-8"
    )


def test_the_workflow_runs_the_five_steps_in_order_each_saying_what_it_did() -> None:
    workflow = read_workflow()

    assert workflow.metadata.id == UUID("d7000000-0000-4000-8000-000000000020")
    assert tuple(step.message for step in workflow.steps) == REEL_STEPS
    assert all(step.emit_values for step in workflow.steps)
    assert all(not step.conditions for step in workflow.steps)
    assert [step.depends_on for step in workflow.steps] == [
        (),
        *[(workflow.steps[index].id,) for index in range(4)],
    ]


def test_each_step_runs_its_tool_of_the_example() -> None:
    names = [read_tool(path).definition.name for path in TOOL_DOCUMENTS]
    specifications = [step.specification for step in read_workflow().steps]

    assert all(isinstance(each, ToolStepSpecification) for each in specifications)
    assert [
        each.requirement.name for each in specifications if isinstance(each, ToolStepSpecification)
    ] == names


def test_each_step_says_what_it_did_under_a_name_of_its_own() -> None:
    said = [
        [binding.name for binding in step.outputs if binding.path == ("message",)]
        for step in read_workflow().steps
    ]

    assert said == [["discovered"], ["approved"], ["tested"], ["measured"], ["proposed"]]


def test_the_result_is_the_proposal_report_and_the_input_is_the_watch() -> None:
    workflow = read_workflow()
    schema = read_tool(DISCOVER_DOCUMENT).definition.input_schema.json_schema

    assert isinstance(schema, dict)

    properties = schema["properties"]

    assert isinstance(properties, dict)
    assert workflow.result == WorkflowNamedValueReference(name="report")
    assert workflow.input_schema == properties["watch"]


def test_the_demo_watch_is_a_valid_input_naming_two_ticket_triage_targets() -> None:
    watch = json.loads(WATCH_DOCUMENT.read_text(encoding="utf-8"))

    schema = read_workflow().input_schema

    assert isinstance(schema, dict)

    jsonschema.validate(watch, schema)

    assert [(target["workflow"], target["benchmark"]) for target in watch["targets"]] == [
        (CLASSIFY_WORKFLOW_ID, CLASSIFY_BENCHMARK_ID),
        (OTHER_WORKFLOW_ID, OTHER_BENCHMARK_ID),
    ]


def test_the_workflow_runs_end_to_end_on_its_first_night(
    instance: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from azathoth.cli import main

    with api.open(instance) as opened:
        opened.workflows.import_document(
            (TRIAGE / "workflows" / "triage-ticket.json").read_text(encoding="utf-8")
        )
        opened.benchmarks.import_document(
            (TRIAGE / "benchmarks" / "triage-ticket.json").read_text(encoding="utf-8")
        )

    for path in TOOL_DOCUMENTS:
        assert main(["tool", "import", str(path)]) == 0

    assert main(["workflow", "import", str(WORKFLOW_DOCUMENT)]) == 0

    ledger_path = tmp_path / "ledger.json"
    watch = {**json.loads(WATCH_DOCUMENT.read_text(encoding="utf-8")), "ledger": str(ledger_path)}
    watch_path = tmp_path / "watch.json"
    watch_path.write_text(json.dumps(watch), encoding="utf-8")
    capsys.readouterr()

    status = main(
        [
            "workflow",
            "run",
            "d7000000-0000-4000-8000-000000000020",
            "--input-file",
            str(watch_path),
            "--output",
            "result",
        ]
    )
    captured = capsys.readouterr()

    assert status == 0, captured.err

    report = json.loads(captured.out)

    assert report["proposals"] == []
    assert report["summary"] == [
        "Watching from now: 0 models served tonight are the baseline, and only models "
        "released after them are tried.",
        "Approved 0 models on this machine for testing. Production stays locked.",
        "Nothing new to test tonight.",
        "Nothing new to compare tonight.",
        "Nothing to propose tonight.",
    ]
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["models"] == {}
