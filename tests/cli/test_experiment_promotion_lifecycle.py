"""End-to-end CLI tests promoting an optimization experiment's winner.

`examples/workflows/classify-sentiment.json` and its benchmark are driven
through the commands an operator runs: import, authorize, optimize, promote
the winning experiment, and invoke (ADR 0092).
"""

import json
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPricing,
    ModelResponse,
    Prompt,
)
from azathoth.workflows import SQLiteWorkflowProductionStateRepository

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "classify-sentiment.json"

BENCHMARK_DOCUMENT = PROJECT_ROOT / "examples" / "benchmarks" / "classify-sentiment.json"

WORKFLOW_ID = UUID("5e2e0b6a-3c1d-4b7e-9f20-000000000001")

BENCHMARK_ID = UUID("5e2e0b6a-3c1d-4b7e-9f21-000000000000")

EXPENSIVE = FixedModelSelection(
    provider="test-provider",
    model="expensive",
)

CHEAP = FixedModelSelection(
    provider="test-provider",
    model="cheap",
)

WINNING_EXPERIMENT = "Winning Experiment ID: "


class PositiveModel:
    """Answer `positive` at a fixed cost per call."""

    def __init__(
        self,
        *,
        model: str,
        estimated_cost_usd: float,
    ) -> None:
        self._model = model
        self._estimated_cost_usd = estimated_cost_usd

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return one deterministic successful model response."""

        prompt_tokens = len(prompt.text.split())

        return ModelResponse(
            text="positive",
            provider="test-provider",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=1,
            total_tokens=prompt_tokens + 1,
            latency_ms=0,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def configure_cli_runtime(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give the real CLI runtime an expensive and a cheap deterministic model."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(
                ModelMetadata(
                    provider=EXPENSIVE.provider,
                    model=EXPENSIVE.model,
                    display_name="Expensive",
                    context_window_tokens=4096,
                    pricing=ModelPricing(
                        input_usd_per_million_tokens=10.0,
                        output_usd_per_million_tokens=20.0,
                    ),
                ),
                ModelMetadata(
                    provider=CHEAP.provider,
                    model=CHEAP.model,
                    display_name="Cheap",
                    context_window_tokens=4096,
                    pricing=ModelPricing(
                        input_usd_per_million_tokens=1.0,
                        output_usd_per_million_tokens=2.0,
                    ),
                ),
            )
        ),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                EXPENSIVE.identifier: PositiveModel(
                    model=EXPENSIVE.model,
                    estimated_cost_usd=0.10,
                ),
                CHEAP.identifier: PositiveModel(
                    model=CHEAP.model,
                    estimated_cost_usd=0.001,
                ),
            }
        ),
    )


def run_cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> str:
    """Run one CLI command, require success, and return its standard output."""

    status = main(arguments)
    captured = capsys.readouterr()

    assert status == 0, captured.err

    return captured.out


def import_authorize_and_optimize(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Prepare and optimize the sentiment workflow; return the winning experiment ID."""

    configure_cli_runtime(
        database=tmp_path / "azathoth.db",
        monkeypatch=monkeypatch,
    )

    run_cli(capsys, "workflow", "import", str(WORKFLOW_DOCUMENT))
    run_cli(capsys, "benchmark", "import", str(BENCHMARK_DOCUMENT))
    run_cli(capsys, "model", "authorize", EXPENSIVE.identifier)
    run_cli(capsys, "model", "authorize", CHEAP.identifier)

    report = run_cli(
        capsys,
        "workflow",
        "optimize",
        str(WORKFLOW_ID),
        "--benchmark",
        str(BENCHMARK_ID),
        "--target-latency",
        "60",
        "--target-cost",
        "0.01",
    )

    last_line = report.splitlines()[-1]

    assert last_line.startswith(WINNING_EXPERIMENT)

    return last_line.removeprefix(WINNING_EXPERIMENT)


def promoted_model(
    database: Path,
) -> FixedModelSelection:
    """Return the model active production pins the sentiment step to."""

    state = SQLiteWorkflowProductionStateRepository(database).get(WORKFLOW_ID)

    assert state is not None

    step = state.specification.steps[0].specification

    assert isinstance(step, ContextPromptStrategySpec)
    assert isinstance(step.model_selection, FixedModelSelection)

    return step.model_selection


def test_plain_promotion_pins_the_configured_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_authorize_and_optimize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))

    assert promoted_model(tmp_path / "azathoth.db") == EXPENSIVE


def test_cli_promotes_the_winning_experiments_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_id = import_authorize_and_optimize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    output = run_cli(
        capsys,
        "workflow",
        "promote",
        str(WORKFLOW_ID),
        "--experiment",
        experiment_id,
    )

    assert "Status: promoted\n" in output
    assert f"Primary Model: {CHEAP.identifier}" in output
    assert promoted_model(tmp_path / "azathoth.db") == CHEAP


def test_cli_invokes_the_promoted_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_id = import_authorize_and_optimize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID), "--experiment", experiment_id)

    output = run_cli(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input",
        '"The checkout flow was painless."',
        "--output",
        "result",
    )

    assert json.loads(output) == {"result": "positive"}


def test_cli_refuses_a_winner_measured_on_an_earlier_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_id = import_authorize_and_optimize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    document = json.loads(WORKFLOW_DOCUMENT.read_text(encoding="utf-8"))
    document["metadata"]["description"] = "Classify sentiment, revised after optimizing."

    revised = tmp_path / "classify-sentiment-revised.json"
    revised.write_text(json.dumps(document), encoding="utf-8")

    run_cli(capsys, "workflow", "import", str(revised))

    status = main(("workflow", "promote", str(WORKFLOW_ID), "--experiment", experiment_id))
    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert "measured on revision 1" in captured.err
    assert "its current revision is 2" in captured.err

    production = SQLiteWorkflowProductionStateRepository(tmp_path / "azathoth.db")

    assert production.get(WORKFLOW_ID) is None


def test_cli_refuses_an_unknown_experiment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_authorize_and_optimize(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    unknown = "00000000-0000-4000-8000-000000000000"

    status = main(("workflow", "promote", str(WORKFLOW_ID), "--experiment", unknown))
    captured = capsys.readouterr()

    assert status == 1
    assert captured.err == f"Experiment {unknown} was not found.\n"
