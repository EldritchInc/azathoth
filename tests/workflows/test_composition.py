"""Tests for composing workflows from independently configured steps."""

from uuid import UUID

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelModality,
    ModelQuery,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("655d78a7-a033-43af-90d6-a656b72077d8")
CLASSIFICATION_STEP_ID = UUID("aa2d758a-328d-49e1-8087-6090e2495a70")
REASONING_STEP_ID = UUID("78647012-e073-468a-966e-a979ff893dc4")
CLASSIFICATION_STRATEGY_ID = UUID("5e73dd70-dd38-4413-8fd4-f60d2c9738e7")
REASONING_STRATEGY_ID = UUID("6dde2eb1-ee7d-4761-a438-09437fef4895")


def create_classification_step() -> WorkflowStepSpecification:
    """Create a low-cost structured classification step."""

    return WorkflowStepSpecification(
        id=CLASSIFICATION_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=CLASSIFICATION_STRATEGY_ID,
                name="Classify request",
                description=("Determine whether the request contains a math problem."),
                version="1.0.0",
            ),
            prompt=Prompt(
                text=(
                    "Determine whether the supplied request contains math. "
                    "Return structured output."
                ),
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(
                    required_capabilities=frozenset(
                        {
                            ModelCapability.STRUCTURED_OUTPUT,
                        }
                    ),
                    minimum_context_window_tokens=8_000,
                )
            ),
        ),
    )


def require_portfolio_requirements(
    specification: PromptStrategySpec,
) -> ModelRequirements:
    """Return requirements from a portfolio-selected prompt specification."""

    selection = specification.model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )

    return selection.requirements


def require_prompt_specification(
    step: WorkflowStepSpecification,
) -> PromptStrategySpec:
    """Return a prompt specification from a prompt-backed workflow step."""

    specification = step.specification

    assert isinstance(
        specification,
        PromptStrategySpec,
    )

    return specification


def create_reasoning_step() -> WorkflowStepSpecification:
    """Create a larger-context tool-capable reasoning step."""

    return WorkflowStepSpecification(
        id=REASONING_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=REASONING_STRATEGY_ID,
                name="Reason about request",
                description=("Reason about the request using tools when needed."),
                version="1.0.0",
            ),
            prompt=Prompt(
                text=(
                    "Solve the supplied request. Use an appropriate tool "
                    "when the task requires one."
                ),
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(
                    required_capabilities=frozenset(
                        {
                            ModelCapability.TOOL_USE,
                        }
                    ),
                    required_input_modalities=frozenset(
                        {
                            ModelModality.TEXT,
                        }
                    ),
                    minimum_context_window_tokens=128_000,
                )
            ),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow whose steps have independent requirements."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Classify and resolve request",
            description=("Classify a request before routing it to a reasoning step."),
            version="1.0.0",
        ),
        steps=(
            create_classification_step(),
            create_reasoning_step(),
        ),
    )


def test_workflow_steps_preserve_independent_model_requirements() -> None:
    workflow = create_workflow()

    classification_requirements = require_portfolio_requirements(
        require_prompt_specification(workflow.steps[0])
    )
    reasoning_requirements = require_portfolio_requirements(
        require_prompt_specification(workflow.steps[1])
    )

    assert classification_requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=8_000,
    )

    assert reasoning_requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        minimum_context_window_tokens=128_000,
    )

    assert classification_requirements != reasoning_requirements


def test_workflow_does_not_define_global_model_requirements() -> None:
    assert "model_requirements" not in WorkflowSpecification.model_fields


def test_workflow_steps_preserve_independent_specifications() -> None:
    workflow = create_workflow()

    classification = require_prompt_specification(workflow.steps[0])
    reasoning = require_prompt_specification(workflow.steps[1])

    assert classification.metadata.name == "Classify request"
    assert reasoning.metadata.name == "Reason about request"

    assert classification.prompt != reasoning.prompt
    assert classification.metadata.id != reasoning.metadata.id


def test_workflow_round_trip_preserves_step_scoped_requirements() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(workflow.model_dump_json())

    assert restored == workflow

    classification = require_prompt_specification(restored.steps[0])
    reasoning = require_prompt_specification(restored.steps[1])

    assert require_portfolio_requirements(classification) != require_portfolio_requirements(
        reasoning
    )

    classification_requirements = require_portfolio_requirements(classification)
    assert ModelCapability.STRUCTURED_OUTPUT in classification_requirements.required_capabilities
    reasoning_requirements = require_portfolio_requirements(reasoning)
    assert ModelCapability.TOOL_USE in reasoning_requirements.required_capabilities


def test_each_workflow_step_can_discover_different_eligible_models() -> None:
    workflow = create_workflow()

    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="classifier",
                display_name="Provider A Classifier",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=32_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="reasoner",
                display_name="Provider B Reasoner",
                capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                context_window_tokens=200_000,
            ),
            ModelMetadata(
                provider="provider-c",
                model="basic",
                display_name="Provider C Basic",
                context_window_tokens=128_000,
            ),
        )
    )

    classification_requirements = require_portfolio_requirements(
        require_prompt_specification(workflow.steps[0])
    )
    reasoning_requirements = require_portfolio_requirements(
        require_prompt_specification(workflow.steps[1])
    )

    classification_models = catalog.find(ModelQuery.from_requirements(classification_requirements))
    reasoning_models = catalog.find(ModelQuery.from_requirements(reasoning_requirements))

    assert tuple(model.identifier for model in classification_models) == ("provider-a/classifier",)

    assert tuple(model.identifier for model in reasoning_models) == ("provider-b/reasoner",)
