"""End-to-end tests for the CLI workflow optimization lifecycle."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    optimize_workflow,
    render_workflow_optimization_session,
)
from azathoth.optimization import WorkflowOptimizationSession
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelPricing,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

EXPENSIVE_IDENTIFIER = "test-provider/expensive"
CHEAP_IDENTIFIER = "test-provider/cheap"


def model_identifier(
    candidate: WorkflowCandidate,
) -> str:
    """Return the model bound to the candidate prompt strategy."""

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def create_workflow() -> WorkflowSpecification:
    """Create one durable portfolio-selected workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="optimization-lifecycle",
            description=("Exercise the installed empirical optimization lifecycle."),
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="prompt",
                        description="Return deterministic output.",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_models() -> ModelCatalog:
    """Create current expensive and cheap provider models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="expensive",
                display_name="Expensive",
                context_window_tokens=4096,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=10.0,
                    output_usd_per_million_tokens=20.0,
                ),
            ),
            ModelMetadata(
                provider="test-provider",
                model="cheap",
                display_name="Cheap",
                context_window_tokens=4096,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=1.0,
                    output_usd_per_million_tokens=2.0,
                ),
            ),
        ),
    )


def create_portfolio() -> ModelPortfolio:
    """Authorize both current provider models."""

    return ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider="test-provider",
                model="expensive",
            ),
            ModelPortfolioEntry(
                provider="test-provider",
                model="cheap",
            ),
        ),
    )


class CostedDeterministicLanguageModel:
    """Return deterministic output with configured execution cost."""

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
        completion_tokens = 1

        return ModelResponse(
            text="success",
            provider="test-provider",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=0,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def create_registry() -> LanguageModelRegistry:
    """Create executable implementations with equal output and unequal cost."""

    return LanguageModelRegistry(
        models={
            EXPENSIVE_IDENTIFIER: CostedDeterministicLanguageModel(
                model="expensive",
                estimated_cost_usd=0.10,
            ),
            CHEAP_IDENTIFIER: CostedDeterministicLanguageModel(
                model="cheap",
                estimated_cost_usd=0.01,
            ),
        }
    )


def create_runtime(
    *,
    workflow: WorkflowSpecification,
) -> AzathothRuntime:
    """Create the reconstructed runtime used by the CLI."""

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(workflow,),
        ),
        models=create_models(),
        portfolio=create_portfolio(),
        language_models=create_registry(),
    )


def test_cli_workflow_optimization_empirically_selects_cheaper_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    workflow = create_workflow()

    SQLiteWorkflowRepository(database).save(
        workflow,
    )

    configuration = CliRuntimeConfiguration(
        database=database,
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    reconstructed = SQLiteWorkflowRepository(
        database,
    ).get(
        WORKFLOW_ID,
    )

    assert reconstructed is not None
    assert reconstructed == workflow

    runtime = create_runtime(
        workflow=reconstructed,
    )

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda received: (
            runtime
            if received == configuration
            else pytest.fail("CLI loaded runtime with unexpected configuration.")
        ),
    )

    rendered_sessions: list[WorkflowOptimizationSession] = []

    real_renderer = render_workflow_optimization_session

    def capture_session(
        session: WorkflowOptimizationSession,
    ) -> str:
        rendered_sessions.append(session)

        return real_renderer(session)

    monkeypatch.setattr(
        workflow_commands,
        "render_workflow_optimization_session",
        capture_session,
    )

    result = optimize_workflow(
        workflow_id=WORKFLOW_ID,
        expected_value="success",
        target_latency_seconds=60.0,
        target_cost_usd=0.01,
        generations=2,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert "Workflow: optimization-lifecycle" in captured.out
    assert f"Workflow ID: {WORKFLOW_ID}" in captured.out

    assert "Initial Candidates: 1" in captured.out
    assert "Generations: 2" in captured.out

    assert "Generation 1" in captured.out
    assert "Evaluated Candidates: 1" in captured.out
    assert "Next Population: 2" in captured.out

    assert "Generation 2" in captured.out
    assert "Evaluated Candidates: 2" in captured.out

    assert captured.out.index("Generation 1") < captured.out.index("Generation 2")

    assert "  Quality: 1.000000" in captured.out
    assert "  Reliability: 1.000000" in captured.out
    assert "  Cost: 1.000000" in captured.out

    assert captured.out.count("  Overall:") == 2

    assert len(rendered_sessions) == 1

    session = rendered_sessions[0]

    assert len(session.generations) == 2

    first_generation = session.generations[0]
    second_generation = session.generations[1]

    assert len(first_generation.previous_experiment.evidence) == 1

    assert len(second_generation.previous_experiment.evidence) == 2

    assert tuple(model_identifier(candidate) for candidate in first_generation.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAP_IDENTIFIER,
    )

    winner_signature = second_generation.previous_experiment.winner_evidence.candidate_signature

    winner = next(
        candidate
        for candidate in second_generation.candidates
        if candidate.signature == winner_signature
    )

    assert model_identifier(winner) == CHEAP_IDENTIFIER

    assert second_generation.previous_experiment.winner.quality_score == 1.0

    assert second_generation.previous_experiment.winner.cost_score == 1.0
