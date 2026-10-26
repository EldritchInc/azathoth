"""Tests for model substitution in context-prompt workflow steps."""

from uuid import UUID

from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptInputBinding,
    PromptOutputFormat,
    PromptStrategy,
    PromptStrategySpec,
    PromptTemplate,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    generate_model_substitutions,
    generate_workflow_candidate,
)
from tests.optimization.test_model_substitution import (
    CHEAPER_IDENTIFIER,
    CHEAPEST_IDENTIFIER,
    EXPENSIVE_IDENTIFIER,
    create_catalog,
    create_registry,
)

WORKFLOW_ID = UUID("c7000000-0000-4000-8000-000000000001")

TRIAGE_STEP_ID = UUID("c7000000-0000-4000-8000-000000000011")
SUMMARY_STEP_ID = UUID("c7000000-0000-4000-8000-000000000012")

TRIAGE_STRATEGY_ID = UUID("c7000000-0000-4000-8000-000000000021")
SUMMARY_STRATEGY_ID = UUID("c7000000-0000-4000-8000-000000000022")

STRUCTURED_OUTPUT = ModelRequirements(
    required_capabilities=frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
        }
    ),
)

TEMPLATE = PromptTemplate(
    text="Triage this ticket: {ticket}",
    bindings=(
        PromptInputBinding(
            variable_name="ticket",
            input_name="ticket",
        ),
    ),
)


def triage_step(
    *,
    fixed: bool = False,
) -> WorkflowStepSpecification:
    """Create a context-prompt step that triages the workflow's ticket."""

    return WorkflowStepSpecification(
        id=TRIAGE_STEP_ID,
        specification=ContextPromptStrategySpec(
            metadata=StrategyMetadata(
                id=TRIAGE_STRATEGY_ID,
                name="triage",
                description="Triage one ticket.",
                version="1.0.0",
            ),
            template=TEMPLATE,
            model_selection=(
                FixedModelSelection(provider="test", model="example/expensive")
                if fixed
                else PortfolioModelSelection(requirements=STRUCTURED_OUTPUT)
            ),
            output_format=PromptOutputFormat.JSON,
        ),
        inputs=(
            WorkflowInputBinding(
                name="ticket",
                source=WorkflowContextReference(
                    event_type="workflow.input.received",
                    field_name="input",
                ),
            ),
        ),
    )


def summary_step() -> WorkflowStepSpecification:
    """Create a fixed-prompt step that runs beside the triage step."""

    return WorkflowStepSpecification(
        id=SUMMARY_STEP_ID,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=SUMMARY_STRATEGY_ID,
                name="summarize",
                description="Summarize the queue.",
                version="1.0.0",
            ),
            prompt=Prompt(text="Summarize the queue."),
            model_selection=PortfolioModelSelection(requirements=STRUCTURED_OUTPUT),
        ),
    )


def create_workflow(
    *steps: WorkflowStepSpecification,
) -> WorkflowSpecification:
    """Create one workflow from the given steps."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="ticket triage",
            description="Exercise context-prompt model substitution.",
            version="1.0.0",
        ),
        steps=steps,
    )


def expensive_candidate(
    workflow: WorkflowSpecification,
) -> WorkflowCandidate:
    """Create a candidate whose every prompt step is bound to the expensive model."""

    expensive = create_catalog().get(EXPENSIVE_IDENTIFIER)

    assert expensive is not None

    return generate_workflow_candidate(
        specification=workflow,
        catalog=ModelCatalog(models=(expensive,)),
        registry=create_registry(),
    )


def substitute(
    workflow: WorkflowSpecification,
) -> tuple[WorkflowCandidate, ...]:
    """Generate every model substitution for the expensive candidate."""

    return generate_model_substitutions(
        specification=workflow,
        candidate=expensive_candidate(workflow),
        catalog=create_catalog(),
        registry=create_registry(),
    )


def bound_models(
    candidate: WorkflowCandidate,
) -> tuple[str, ...]:
    """Return the model identifier each prompt step of a candidate is bound to."""

    identifiers: list[str] = []

    for step in candidate.steps:
        strategy = step.strategy

        assert isinstance(strategy, (PromptStrategy, ContextPromptStrategy))
        assert strategy.model_binding is not None

        identifiers.append(strategy.model_binding.identifier)

    return tuple(identifiers)


def test_context_prompt_steps_are_substituted_with_strictly_cheaper_models() -> None:
    substitutions = substitute(create_workflow(triage_step()))

    assert tuple(bound_models(substitution) for substitution in substitutions) == (
        (CHEAPER_IDENTIFIER,),
        (CHEAPEST_IDENTIFIER,),
    )


def test_context_prompt_substitution_keeps_template_and_output_format() -> None:
    substitutions = substitute(create_workflow(triage_step()))

    assert substitutions

    for substitution in substitutions:
        strategy = substitution.steps[0].strategy

        assert isinstance(strategy, ContextPromptStrategy)
        assert strategy.template == TEMPLATE
        assert strategy.output_format == PromptOutputFormat.JSON
        assert substitution.steps[0].inputs == triage_step().inputs


def test_context_prompt_substitution_regenerates_strategy_identity() -> None:
    workflow = create_workflow(triage_step())

    original = expensive_candidate(workflow).steps[0].strategy
    replacement = substitute(workflow)[0].steps[0].strategy

    assert replacement.metadata.id != original.metadata.id


def test_fixed_context_prompt_steps_are_never_substituted() -> None:
    assert substitute(create_workflow(triage_step(fixed=True))) == ()


def test_each_prompt_step_is_substituted_one_at_a_time() -> None:
    substitutions = substitute(create_workflow(triage_step(), summary_step()))

    assert tuple(bound_models(substitution) for substitution in substitutions) == (
        (CHEAPER_IDENTIFIER, EXPENSIVE_IDENTIFIER),
        (CHEAPEST_IDENTIFIER, EXPENSIVE_IDENTIFIER),
        (EXPENSIVE_IDENTIFIER, CHEAPER_IDENTIFIER),
        (EXPENSIVE_IDENTIFIER, CHEAPEST_IDENTIFIER),
    )
