"""Tests proving checked-in workflow examples remain valid documents."""

from pathlib import Path
from uuid import UUID

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelModality,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

SIMPLE_PROMPT_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "simple-prompt.json"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_simple_prompt_workflow() -> WorkflowSpecification:
    """Create the canonical workflow represented by the example document."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="simple prompt",
            description=("Return a concise answer to one request."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="answer request",
                        description=("Answer one request with a language model."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Answer the request concisely.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
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


def read_simple_prompt_document() -> str:
    """Read the checked-in simple prompt workflow document."""

    return SIMPLE_PROMPT_DOCUMENT.read_text(encoding="utf-8")


def test_simple_prompt_example_is_valid_workflow_document() -> None:
    specification = decode_workflow_document(read_simple_prompt_document())

    assert specification == create_simple_prompt_workflow()


def test_simple_prompt_example_matches_canonical_serialization() -> None:
    document = read_simple_prompt_document()

    canonical = encode_workflow_document(create_simple_prompt_workflow())

    assert document.rstrip("\n") == canonical


def test_simple_prompt_example_has_stable_workflow_identity() -> None:
    specification = decode_workflow_document(read_simple_prompt_document())

    assert specification.metadata.id == WORKFLOW_ID
    assert specification.metadata.name == "simple prompt"
    assert specification.metadata.version == "1.0.0"


def test_simple_prompt_example_contains_prompt_step() -> None:
    specification = decode_workflow_document(read_simple_prompt_document())

    assert len(specification.steps) == 1

    step = specification.steps[0]

    assert step.id == STEP_ID

    assert isinstance(
        step.specification,
        PromptStrategySpec,
    )

    assert step.specification.metadata.id == STRATEGY_ID

    assert step.specification.prompt.text == "Answer the request concisely."


def test_simple_prompt_example_uses_default_model_requirements() -> None:
    specification = decode_workflow_document(read_simple_prompt_document())

    prompt = specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    requirements = require_portfolio_requirements(prompt)

    assert requirements.required_capabilities == frozenset()

    assert requirements.required_input_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert requirements.required_output_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert requirements.minimum_context_window_tokens is None
    assert requirements.minimum_output_tokens is None

    assert requirements.maximum_input_usd_per_million_tokens is None

    assert requirements.maximum_output_usd_per_million_tokens is None

    assert not requirements.require_known_pricing


def test_simple_prompt_example_uses_default_workflow_behavior() -> None:
    specification = decode_workflow_document(read_simple_prompt_document())

    step = specification.steps[0]

    assert step.depends_on == ()
    assert step.inputs == ()
    assert step.outputs == ()
    assert step.conditions == ()

    assert step.retry_policy == WorkflowRetryPolicy()

    assert step.failure_policy == WorkflowFailurePolicy.FAIL_WORKFLOW
