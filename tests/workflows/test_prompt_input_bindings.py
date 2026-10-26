"""Tests for workflow prompt steps that bind template variables to step inputs."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import Context
from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptInputBinding,
    PromptTemplate,
)
from azathoth.providers import ModelRequirements
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
)
from tests.prompting.test_context_strategy import RecordingLanguageModel

WORKFLOW_ID = UUID("c4000000-0000-4000-8000-000000000001")

PLAN_STEP_ID = UUID("c4000000-0000-4000-8000-000000000011")
NOTES_STEP_ID = UUID("c4000000-0000-4000-8000-000000000012")
WRITE_STEP_ID = UUID("c4000000-0000-4000-8000-000000000013")

PLAN_STRATEGY_ID = UUID("c4000000-0000-4000-8000-000000000021")
NOTES_STRATEGY_ID = UUID("c4000000-0000-4000-8000-000000000022")
WRITE_STRATEGY_ID = UUID("c4000000-0000-4000-8000-000000000023")

TEMPLATE = PromptTemplate(
    text="Plan: {plan}\nNotes: {notes}\nWrite the next chapter.",
    bindings=(
        PromptInputBinding(
            variable_name="plan",
            input_name="plan",
        ),
        PromptInputBinding(
            variable_name="notes",
            input_name="notes",
        ),
    ),
)

STEP_INPUTS = (
    WorkflowInputBinding(
        name="plan",
        source=WorkflowValueReference(
            producer_step_id=PLAN_STEP_ID,
            name="plan",
        ),
    ),
    WorkflowInputBinding(
        name="notes",
        source=WorkflowValueReference(
            producer_step_id=NOTES_STEP_ID,
            name="notes",
        ),
    ),
)


def write_specification() -> ContextPromptStrategySpec:
    """Create the durable chapter-writing prompt specification."""

    return ContextPromptStrategySpec(
        metadata=StrategyMetadata(
            id=WRITE_STRATEGY_ID,
            name="Write chapter",
            description="Write the next chapter from the plan and notes.",
            version="1.0.0",
        ),
        template=TEMPLATE,
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


class ValueStrategy:
    """Answer with one fixed JSON value."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
        output: JsonValue,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Produce {name}.",
            version="1.0.0",
        )
        self._output = output

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return the fixed output."""

        return StrategyOutcome(
            output=self._output,
        )


def test_step_accepts_input_bindings_for_declared_inputs() -> None:
    step = WorkflowStepSpecification(
        id=WRITE_STEP_ID,
        specification=write_specification(),
        depends_on=(PLAN_STEP_ID, NOTES_STEP_ID),
        inputs=STEP_INPUTS,
    )

    assert step.specification == write_specification()


def test_step_rejects_an_input_binding_for_an_undeclared_input() -> None:
    with pytest.raises(ValidationError) as raised:
        WorkflowStepSpecification(
            id=WRITE_STEP_ID,
            specification=write_specification(),
            depends_on=(PLAN_STEP_ID,),
            inputs=STEP_INPUTS[:1],
        )

    assert (
        f"Workflow step {WRITE_STEP_ID} prompt variable 'notes' binds input 'notes', "
        "which the step does not declare."
    ) in str(raised.value)


def test_prompt_step_renders_every_input_it_binds() -> None:
    model = RecordingLanguageModel("Chapter one.")

    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Write one chapter",
            description="Render a prompt from two upstream values.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=PLAN_STEP_ID,
                strategy=ValueStrategy(
                    strategy_id=PLAN_STRATEGY_ID,
                    name="Plan",
                    output={"acts": 3, "title": "Café at the End"},
                ),
                outputs=(WorkflowValueBinding(name="plan"),),
            ),
            WorkflowCandidateStep(
                id=NOTES_STEP_ID,
                strategy=ValueStrategy(
                    strategy_id=NOTES_STRATEGY_ID,
                    name="Notes",
                    output="The lighthouse keeper lied.",
                ),
                outputs=(WorkflowValueBinding(name="notes"),),
            ),
            WorkflowCandidateStep(
                id=WRITE_STEP_ID,
                strategy=ContextPromptStrategy(
                    metadata=write_specification().metadata,
                    template=TEMPLATE,
                    language_model=model,
                ),
                depends_on=(PLAN_STEP_ID, NOTES_STEP_ID),
                inputs=STEP_INPUTS,
                outputs=(WorkflowValueBinding(name="chapter"),),
            ),
        ),
    )

    run = asyncio.run(WorkflowRunner().run(candidate, Context()))

    assert run.steps[2].status == WorkflowStepStatus.EXECUTED
    assert model.received_prompt is not None
    assert model.received_prompt.text == (
        'Plan: {"acts":3,"title":"Café at the End"}\n'
        "Notes: The lighthouse keeper lied.\n"
        "Write the next chapter."
    )
