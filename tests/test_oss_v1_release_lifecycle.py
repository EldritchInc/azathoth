"""Release acceptance coverage for the complete OSS V1 CLI lifecycle."""

from pathlib import Path

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
    render_workflow_optimization_session,
)
from azathoth.optimization import WorkflowOptimizationSession
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolioEntry,
    ModelPricing,
    ModelResponse,
    Prompt,
    SQLiteModelPortfolioRepository,
)
from azathoth.workflows import (
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCandidate,
    WorkflowProductionState,
    decode_workflow_document,
)

PROJECT_ROOT = Path(__file__).parents[1]

SIMPLE_PROMPT_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "simple-prompt.json"

EXPENSIVE_IDENTIFIER = "test-provider/expensive"
CHEAP_IDENTIFIER = "test-provider/cheap"


class CostedDeterministicLanguageModel:
    """Return deterministic output with explicit empirical execution cost."""

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

        prompt_tokens = len(
            prompt.text.split(),
        )
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


def create_models() -> ModelCatalog:
    """Return deterministic current provider state for release acceptance."""

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


def create_registry() -> LanguageModelRegistry:
    """Return deterministic executable models with unequal empirical cost."""

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


def configure_provider_boundary(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace only external provider state with deterministic equivalents."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: create_models(),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: create_registry(),
    )


def model_identifier(
    candidate: WorkflowCandidate,
) -> str:
    """Return the executable model bound to one prompt workflow candidate."""

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )
    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def production_model_identifier(
    state: WorkflowProductionState,
) -> str:
    """Return the fixed primary model materialized into production."""

    step = state.specification.steps[0].specification

    assert isinstance(
        step,
        PromptStrategySpec,
    )

    selection = step.model_selection

    assert isinstance(
        selection,
        FixedModelSelection,
    )

    return selection.identifier


def test_oss_v1_release_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prove the documented OSS V1 lifecycle composes end to end."""

    database = tmp_path / "azathoth.db"

    configure_provider_boundary(
        database=database,
        monkeypatch=monkeypatch,
    )

    canonical_workflow = decode_workflow_document(
        SIMPLE_PROMPT_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )
    workflow_id = canonical_workflow.metadata.id

    #
    # Durable workflow configuration.
    #

    assert (
        main(
            (
                "workflow",
                "import",
                str(SIMPLE_PROMPT_DOCUMENT),
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (f"Imported workflow {workflow_id}.\n")

    persisted_workflow = SQLiteWorkflowRepository(
        database,
    ).get(
        workflow_id,
    )

    assert persisted_workflow == canonical_workflow

    #
    # Provider availability is visible independently from authorization.
    #

    assert (
        main(
            (
                "model",
                "list",
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert EXPENSIVE_IDENTIFIER in captured.out
    assert CHEAP_IDENTIFIER in captured.out

    assert (
        SQLiteModelPortfolioRepository(
            database,
        ).entries()
        == ()
    )

    #
    # Organizational authorization is durable.
    #

    assert (
        main(
            (
                "model",
                "authorize",
                EXPENSIVE_IDENTIFIER,
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (f"Authorized model {EXPENSIVE_IDENTIFIER}.\n")

    assert (
        main(
            (
                "model",
                "authorize",
                CHEAP_IDENTIFIER,
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (f"Authorized model {CHEAP_IDENTIFIER}.\n")

    portfolio_repository = SQLiteModelPortfolioRepository(
        database,
    )

    assert portfolio_repository.entries() == (
        ModelPortfolioEntry(
            provider="test-provider",
            model="expensive",
        ),
        ModelPortfolioEntry(
            provider="test-provider",
            model="cheap",
        ),
    )

    assert (
        main(
            (
                "model",
                "portfolio",
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out == (f"{EXPENSIVE_IDENTIFIER}\n{CHEAP_IDENTIFIER}\n")

    #
    # Configured execution generates and executes the configured workflow.
    #

    assert (
        main(
            (
                "workflow",
                "run",
                str(workflow_id),
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert f"Workflow ID: {workflow_id}\n" in captured.out
    assert "Status: succeeded\n" in captured.out
    assert "Provider: test-provider\n" in captured.out
    assert "Model: expensive\n" in captured.out
    assert 'Output:\n"success"\n' in captured.out

    #
    # Empirical optimization discovers the cheaper passing candidate.
    #

    rendered_sessions: list[WorkflowOptimizationSession] = []

    real_renderer = render_workflow_optimization_session

    def capture_optimization_session(
        session: WorkflowOptimizationSession,
    ) -> str:
        """Capture empirical evidence while preserving normal CLI rendering."""

        rendered_sessions.append(
            session,
        )

        return real_renderer(
            session,
        )

    monkeypatch.setattr(
        workflow_commands,
        "render_workflow_optimization_session",
        capture_optimization_session,
    )

    assert (
        main(
            (
                "workflow",
                "optimize",
                str(workflow_id),
                "--expected",
                '"success"',
                "--target-latency",
                "60",
                "--target-cost",
                "0.01",
                "--generations",
                "2",
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Generations: 2\n" in captured.out
    assert "Generation 1\n" in captured.out
    assert "Generation 2\n" in captured.out

    assert (
        len(
            rendered_sessions,
        )
        == 1
    )

    optimization = rendered_sessions[0]

    assert (
        len(
            optimization.generations,
        )
        == 2
    )

    first_generation = optimization.generations[0]
    second_generation = optimization.generations[1]

    assert tuple(
        model_identifier(
            candidate,
        )
        for candidate in first_generation.candidates
    ) == (
        EXPENSIVE_IDENTIFIER,
        CHEAP_IDENTIFIER,
    )

    winner_signature = second_generation.previous_experiment.winner_evidence.candidate_signature

    winner = next(
        candidate
        for candidate in second_generation.candidates
        if candidate.signature == winner_signature
    )

    assert (
        model_identifier(
            winner,
        )
        == CHEAP_IDENTIFIER
    )

    assert second_generation.previous_experiment.winner.quality_score == 1.0
    assert second_generation.previous_experiment.winner.reliability_score == 1.0
    assert second_generation.previous_experiment.winner.cost_score == 1.0

    #
    # Optimization is empirical search, not production authority.
    #

    production_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    revision_repository = SQLiteWorkflowProductionRevisionRepository(
        database,
    )

    assert (
        production_repository.get(
            workflow_id,
        )
        is None
    )
    assert (
        revision_repository.revisions_for_workflow(
            workflow_id,
        )
        == ()
    )

    #
    # Promotion is the explicit production state transition.
    #

    assert (
        main(
            (
                "workflow",
                "promote",
                str(workflow_id),
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert f"Workflow ID: {workflow_id}\n" in captured.out
    assert "Status: promoted\n" in captured.out

    state = production_repository.get(
        workflow_id,
    )

    assert state is not None

    #
    # Promotion materializes the configured candidate independently from the
    # optimizer's empirical winner.
    #

    assert (
        production_model_identifier(
            state,
        )
        == EXPENSIVE_IDENTIFIER
    )

    revisions = revision_repository.revisions_for_workflow(
        workflow_id,
    )

    assert (
        len(
            revisions,
        )
        == 1
    )
    assert revisions[0].state == state

    #
    # Production invocation executes active production state and persists
    # invocation, run, association, and terminal result.
    #

    assert (
        main(
            (
                "workflow",
                "invoke",
                str(workflow_id),
                "--input",
                '{"request":"release acceptance"}',
            )
        )
        == 0
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Status: succeeded\n" in captured.out

    invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )
    run_repository = SQLiteWorkflowRunRepository(
        database,
    )
    invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    invocations = invocation_repository.invocations()

    assert (
        len(
            invocations,
        )
        == 1
    )

    invocation = invocations[0]

    assert invocation.workflow_id == workflow_id

    terminal_result = invocation_repository.result(
        invocation.id,
    )

    assert isinstance(
        terminal_result,
        ProductionInvocationSuccess,
    )

    #
    # The canonical minimal workflow declares no public production emissions,
    # so the caller-visible result is intentionally empty even though the
    # workflow itself executed successfully.
    #

    assert terminal_result.result == {}

    association = invocation_run_repository.get(
        invocation.id,
    )

    assert association is not None

    run = run_repository.get(
        association.run_id,
    )

    assert run is not None
    assert run.workflow.id == workflow_id
    assert run.succeeded
    assert run.initial_context == invocation.initial_context

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.output == "success"
    assert execution.metrics is not None
    assert execution.metrics.provider == "test-provider"
    assert execution.metrics.model == "expensive"
