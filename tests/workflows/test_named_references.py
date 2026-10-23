"""Tests for name-only workflow value references and their validation."""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
    declaring_step_ids,
    resolve_named_value,
)
from azathoth.workflows.document import (
    decode_workflow_document,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("c3a1d6e2-4b5f-4e70-9a81-2b3c4d5e6f01")

PRIMARY_STEP_ID = UUID("c3a1d6e2-4b5f-4e70-9a81-2b3c4d5e6f11")
FALLBACK_STEP_ID = UUID("c3a1d6e2-4b5f-4e70-9a81-2b3c4d5e6f12")
UNRELATED_STEP_ID = UUID("c3a1d6e2-4b5f-4e70-9a81-2b3c4d5e6f13")
CONSUMER_STEP_ID = UUID("c3a1d6e2-4b5f-4e70-9a81-2b3c4d5e6f14")

NAMED_INPUT_ERROR = (
    "Workflow input bindings must name a value declared by a step the consumer depends on."
)

ADDRESS_OUTPUT = (
    WorkflowValueBinding(
        name="address",
        path=("address",),
    ),
)


def create_step(
    *,
    step_id: UUID,
    name: str,
    depends_on: tuple[UUID, ...] = (),
    inputs: tuple[WorkflowInputBinding, ...] = (),
    outputs: tuple[WorkflowValueBinding, ...] = (),
) -> WorkflowStepSpecification:
    """Create a deterministic prompt-backed workflow step specification."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                name=name,
                description=f"Execute the {name.lower()} step.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text=f"Perform the {name.lower()} step.",
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(),
            ),
        ),
        depends_on=depends_on,
        inputs=inputs,
        outputs=outputs,
    )


def named_address_input() -> WorkflowInputBinding:
    """Return a step input that names the address value alone."""

    return WorkflowInputBinding(
        name="address",
        source=WorkflowNamedValueReference(
            name="address",
        ),
    )


def create_workflow(
    *,
    consumer_depends_on: tuple[UUID, ...] = (
        PRIMARY_STEP_ID,
        FALLBACK_STEP_ID,
    ),
    fallback_outputs: tuple[WorkflowValueBinding, ...] = ADDRESS_OUTPUT,
) -> WorkflowSpecification:
    """Create a workflow whose consumer names a redundantly produced value."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Redundant address lookup",
            description="Look an address up two ways and use whichever answered.",
            version="1.0.0",
        ),
        steps=(
            create_step(
                step_id=PRIMARY_STEP_ID,
                name="Primary",
                outputs=ADDRESS_OUTPUT,
            ),
            create_step(
                step_id=FALLBACK_STEP_ID,
                name="Fallback",
                outputs=fallback_outputs,
            ),
            create_step(
                step_id=UNRELATED_STEP_ID,
                name="Unrelated",
                outputs=ADDRESS_OUTPUT,
            ),
            create_step(
                step_id=CONSUMER_STEP_ID,
                name="Consumer",
                depends_on=consumer_depends_on,
                inputs=(named_address_input(),),
            ),
        ),
    )


def address_value(
    producer_step_id: UUID,
    value: str,
) -> WorkflowValue:
    """Return one committed address value."""

    return WorkflowValue(
        name="address",
        value=value,
        producer_step_id=producer_step_id,
    )


def test_named_reference_records_its_name() -> None:
    reference = WorkflowNamedValueReference(
        name="address",
    )

    assert reference.name == "address"


def test_named_reference_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowNamedValueReference(
            name="",
        )


def test_named_reference_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkflowNamedValueReference.model_validate(
            {
                "name": "address",
                "producer": "Primary",
            }
        )


def test_named_reference_is_immutable() -> None:
    reference = WorkflowNamedValueReference(
        name="address",
    )

    with pytest.raises(ValidationError):
        reference.name = "other"


def test_input_binding_decodes_name_only_source() -> None:
    binding = WorkflowInputBinding.model_validate_json(
        json.dumps(
            {
                "name": "location",
                "source": {
                    "name": "address",
                },
            }
        )
    )

    assert binding.source == WorkflowNamedValueReference(
        name="address",
    )


def test_input_binding_still_decodes_explicit_source() -> None:
    binding = WorkflowInputBinding.model_validate_json(
        json.dumps(
            {
                "name": "location",
                "source": {
                    "producer_step_id": str(PRIMARY_STEP_ID),
                    "name": "address",
                },
            }
        )
    )

    assert binding.source == WorkflowValueReference(
        producer_step_id=PRIMARY_STEP_ID,
        name="address",
    )


def test_input_binding_still_decodes_context_source() -> None:
    binding = WorkflowInputBinding.model_validate_json(
        json.dumps(
            {
                "name": "request",
                "source": {
                    "event_type": "workflow.input.received",
                    "field_name": "input",
                },
            }
        )
    )

    assert binding.source == WorkflowContextReference(
        event_type="workflow.input.received",
        field_name="input",
    )


def test_name_only_source_dumps_only_its_name() -> None:
    dumped = named_address_input().model_dump(
        mode="json",
    )

    assert dumped == {
        "name": "address",
        "source": {
            "name": "address",
        },
    }


def test_declaring_step_ids_keep_the_given_step_order() -> None:
    workflow = create_workflow()

    assert declaring_step_ids(
        "address",
        workflow.steps,
    ) == (
        PRIMARY_STEP_ID,
        FALLBACK_STEP_ID,
        UNRELATED_STEP_ID,
    )


def test_declaring_step_ids_ignore_steps_without_the_output() -> None:
    workflow = create_workflow()

    assert (
        declaring_step_ids(
            "missing",
            workflow.steps,
        )
        == ()
    )


def test_resolve_named_value_prefers_the_first_candidate() -> None:
    resolved = resolve_named_value(
        "address",
        producer_step_ids=(
            PRIMARY_STEP_ID,
            FALLBACK_STEP_ID,
        ),
        values=(
            address_value(FALLBACK_STEP_ID, "fallback"),
            address_value(PRIMARY_STEP_ID, "primary"),
        ),
    )

    assert resolved == address_value(PRIMARY_STEP_ID, "primary")


def test_resolve_named_value_passes_over_candidates_without_a_value() -> None:
    resolved = resolve_named_value(
        "address",
        producer_step_ids=(
            PRIMARY_STEP_ID,
            FALLBACK_STEP_ID,
        ),
        values=(address_value(FALLBACK_STEP_ID, "fallback"),),
    )

    assert resolved == address_value(FALLBACK_STEP_ID, "fallback")


def test_resolve_named_value_ignores_non_candidate_producers() -> None:
    resolved = resolve_named_value(
        "address",
        producer_step_ids=(PRIMARY_STEP_ID,),
        values=(address_value(UNRELATED_STEP_ID, "unrelated"),),
    )

    assert resolved is None


def test_resolve_named_value_ignores_other_names() -> None:
    resolved = resolve_named_value(
        "address",
        producer_step_ids=(PRIMARY_STEP_ID,),
        values=(
            WorkflowValue(
                name="city",
                value="Brooklyn",
                producer_step_id=PRIMARY_STEP_ID,
            ),
        ),
    )

    assert resolved is None


def test_workflow_accepts_name_only_input_declared_by_a_dependency() -> None:
    workflow = create_workflow()

    consumer = workflow.steps[-1]

    assert consumer.inputs == (named_address_input(),)


def test_workflow_accepts_name_only_input_with_one_declaring_dependency() -> None:
    workflow = create_workflow(
        fallback_outputs=(),
    )

    assert workflow.steps[-1].inputs == (named_address_input(),)


def test_workflow_rejects_name_only_input_without_dependencies() -> None:
    with pytest.raises(
        ValidationError,
        match=NAMED_INPUT_ERROR,
    ):
        create_workflow(
            consumer_depends_on=(),
        )


def test_workflow_rejects_name_only_input_no_dependency_declares() -> None:
    #
    # Unrelated declares the output, but the consumer does not depend on it.
    #
    with pytest.raises(
        ValidationError,
        match=NAMED_INPUT_ERROR,
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="Undeclared address",
                description="Name a value no dependency declares.",
                version="1.0.0",
            ),
            steps=(
                create_step(
                    step_id=PRIMARY_STEP_ID,
                    name="Primary",
                ),
                create_step(
                    step_id=UNRELATED_STEP_ID,
                    name="Unrelated",
                    outputs=ADDRESS_OUTPUT,
                ),
                create_step(
                    step_id=CONSUMER_STEP_ID,
                    name="Consumer",
                    depends_on=(PRIMARY_STEP_ID,),
                    inputs=(named_address_input(),),
                ),
            ),
        )


def test_workflow_rejects_name_only_input_declared_only_transitively() -> None:
    #
    # Primary declares the output, but the consumer depends on it only
    # through Fallback, so it is not a candidate producer.
    #
    with pytest.raises(
        ValidationError,
        match=NAMED_INPUT_ERROR,
    ):
        WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="Transitive address",
                description="Name a value only a grandparent declares.",
                version="1.0.0",
            ),
            steps=(
                create_step(
                    step_id=PRIMARY_STEP_ID,
                    name="Primary",
                    outputs=ADDRESS_OUTPUT,
                ),
                create_step(
                    step_id=FALLBACK_STEP_ID,
                    name="Fallback",
                    depends_on=(PRIMARY_STEP_ID,),
                ),
                create_step(
                    step_id=CONSUMER_STEP_ID,
                    name="Consumer",
                    depends_on=(FALLBACK_STEP_ID,),
                    inputs=(named_address_input(),),
                ),
            ),
        )


def test_workflow_with_name_only_input_round_trips_through_document() -> None:
    workflow = create_workflow()

    restored = decode_workflow_document(
        encode_workflow_document(workflow),
    )

    assert restored == workflow
    assert restored.steps[-1].inputs[0].source == WorkflowNamedValueReference(
        name="address",
    )


def test_workflow_document_with_explicit_inputs_is_unchanged() -> None:
    workflow = create_workflow()

    explicit = workflow.model_copy(
        update={
            "steps": (
                *workflow.steps[:-1],
                workflow.steps[-1].model_copy(
                    update={
                        "inputs": (
                            WorkflowInputBinding(
                                name="address",
                                source=WorkflowValueReference(
                                    producer_step_id=PRIMARY_STEP_ID,
                                    name="address",
                                ),
                            ),
                        ),
                    }
                ),
            ),
        }
    )

    document = json.loads(
        encode_workflow_document(explicit),
    )

    assert document["steps"][-1]["inputs"] == [
        {
            "name": "address",
            "source": {
                "producer_step_id": str(PRIMARY_STEP_ID),
                "name": "address",
            },
        }
    ]
