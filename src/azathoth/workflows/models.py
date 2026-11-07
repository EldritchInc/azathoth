"""Domain models describing model-independent workflows."""

from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from azathoth.evaluation import json_schema_validator
from azathoth.workflows.references import declaring_step_ids
from azathoth.workflows.steps import WorkflowStepSpecification
from azathoth.workflows.value import (
    WorkflowNamedValueReference,
    WorkflowResultReference,
    WorkflowValueReference,
)


class WorkflowMetadata(BaseModel):
    """Stable identifying information for a workflow specification."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class WorkflowSpecification(BaseModel):
    """Describe an ordered workflow without runtime dependencies.

    The optional result identifies the one declared step output that is the
    workflow's answer. Evaluation and production use exactly this value. A
    name-only result resolves to the first step, in step order, that produced
    a value with that name.

    The optional `input_schema` is a JSON Schema of the value the workflow
    receives, after resolution, so a document is its content handle; the
    optional `output_schema` is one of its declared result. Every production
    invocation is checked against the schemas of the promoted specification
    (ADR 0118). A specification without them serializes without them, so no
    existing workflow's digest changes.
    """

    model_config = ConfigDict(frozen=True)

    metadata: WorkflowMetadata
    steps: tuple[WorkflowStepSpecification, ...] = Field(
        min_length=1,
    )
    result: WorkflowResultReference | None = None
    input_schema: JsonValue | None = None
    output_schema: JsonValue | None = None

    @field_validator("input_schema", "output_schema")
    @classmethod
    def require_json_schema(
        cls,
        schema: JsonValue | None,
        info: ValidationInfo,
    ) -> JsonValue | None:
        """Refuse a schema that is not a valid JSON Schema.

        Raises:
            ValueError: The schema is not an object or a boolean, or does not
                satisfy its dialect's metaschema.
        """

        if schema is None:
            return schema

        try:
            json_schema_validator(schema)
        except ValueError as exc:
            label = (info.field_name or "schema").replace("_", " ")

            raise ValueError(f"The workflow's {label} is not usable: {exc}") from exc

        return schema

    @model_validator(mode="after")
    def require_a_result_for_an_output_schema(self) -> Self:
        """Refuse an output schema of a workflow that declares no result.

        Raises:
            ValueError: The workflow has an output schema and no result.
        """

        if self.output_schema is not None and self.result is None:
            raise ValueError(
                f"Workflow {self.metadata.id} has an output schema, which describes its "
                "result, but declares no result."
            )

        return self

    @model_serializer(mode="wrap")
    def omit_absent_schemas(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Leave out `input_schema` and `output_schema` when the workflow has none."""

        serialized: dict[str, Any] = handler(self)

        for name in ("input_schema", "output_schema"):
            if getattr(self, name) is None:
                serialized.pop(name, None)

        return serialized

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> Self:
        """Ensure every workflow step has a unique identifier."""

        step_ids = tuple(step.id for step in self.steps)

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step identifiers must be unique.")

        return self

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Self:
        """Ensure workflow dependencies and value references are valid."""

        steps_by_id = {step.id: step for step in self.steps}

        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("Workflow step dependencies must be unique.")

            if step.id in step.depends_on:
                raise ValueError("Workflow steps cannot depend on themselves.")

            for dependency_id in step.depends_on:
                if dependency_id not in steps_by_id:
                    raise ValueError(
                        "Workflow step dependencies must reference steps in the same workflow."
                    )

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(step_id: UUID) -> None:
            """Visit one workflow step while detecting dependency cycles."""

            if step_id in visited:
                return

            if step_id in visiting:
                raise ValueError("Workflow dependency graph must be acyclic.")

            visiting.add(step_id)

            for dependency_id in steps_by_id[step_id].depends_on:
                visit(
                    dependency_id,
                )

            visiting.remove(step_id)
            visited.add(step_id)

        for step in self.steps:
            visit(
                step.id,
            )

        for step in self.steps:
            output_names = tuple(binding.name for binding in step.outputs)

            if len(output_names) != len(set(output_names)):
                raise ValueError(
                    "Workflow step output names must be unique within each producer step."
                )

            input_names = tuple(binding.name for binding in step.inputs)

            if len(input_names) != len(set(input_names)):
                raise ValueError(
                    "Workflow step input names must be unique within each consumer step."
                )

            upstream_step_ids = self._upstream_step_ids(step)

            for input_binding in step.inputs:
                source = input_binding.source

                if isinstance(
                    source,
                    WorkflowNamedValueReference,
                ):
                    if not declaring_step_ids(
                        source.name,
                        (steps_by_id[dependency_id] for dependency_id in step.depends_on),
                    ):
                        raise ValueError(
                            "Workflow input bindings must name a value "
                            "declared by a step the consumer depends on."
                        )

                    continue

                if not isinstance(
                    source,
                    WorkflowValueReference,
                ):
                    continue

                producer_step_id = source.producer_step_id

                if producer_step_id not in steps_by_id:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "a producer step in the same workflow."
                    )

                producer = steps_by_id[producer_step_id]

                producer_output_names = {output.name for output in producer.outputs}

                if source.name not in producer_output_names:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "an output declared by the producer step."
                    )

                if producer_step_id not in upstream_step_ids:
                    raise ValueError(
                        "Workflow input bindings must reference "
                        "values produced by upstream workflow steps."
                    )

            for condition in step.conditions:
                producer_step_id = condition.source.producer_step_id

                if producer_step_id not in steps_by_id:
                    raise ValueError(
                        "Workflow conditions must reference a producer step in the same workflow."
                    )

                producer = steps_by_id[producer_step_id]

                producer_output_names = {output.name for output in producer.outputs}

                if condition.source.name not in producer_output_names:
                    raise ValueError(
                        "Workflow conditions must reference "
                        "an output declared by the producer step."
                    )

                if producer_step_id not in upstream_step_ids:
                    raise ValueError(
                        "Workflow conditions must reference "
                        "values produced by upstream workflow steps."
                    )

        return self

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Ensure a declared result references a declared step output.

        A name-only result needs at least one step declaring the name.
        """

        if self.result is None:
            return self

        if isinstance(
            self.result,
            WorkflowNamedValueReference,
        ):
            if not declaring_step_ids(
                self.result.name,
                self.steps,
            ):
                raise ValueError(
                    "Workflow result must name a value declared by at least one workflow step."
                )

            return self

        producer = next(
            (step for step in self.steps if step.id == self.result.producer_step_id),
            None,
        )

        if producer is None:
            raise ValueError("Workflow result must reference a producer step in the same workflow.")

        if self.result.name not in {output.name for output in producer.outputs}:
            raise ValueError(
                "Workflow result must reference an output declared by the producer step."
            )

        return self

    def execution_layers(
        self,
    ) -> tuple[tuple[WorkflowStepSpecification, ...], ...]:
        """Return dependency-safe workflow steps grouped into layers."""

        remaining = list(self.steps)
        completed_ids: set[UUID] = set()
        layers: list[tuple[WorkflowStepSpecification, ...]] = []

        while remaining:
            ready = tuple(
                step for step in remaining if set(step.depends_on).issubset(completed_ids)
            )

            if not ready:
                raise RuntimeError(
                    "Validated workflow dependency graph could not produce an execution layer."
                )

            layers.append(ready)

            ready_ids = {step.id for step in ready}
            completed_ids.update(ready_ids)

            remaining = [step for step in remaining if step.id not in ready_ids]

        return tuple(layers)

    def _upstream_step_ids(
        self,
        step: WorkflowStepSpecification,
    ) -> set[UUID]:
        """Return all transitive dependencies of a workflow step."""

        steps_by_id = {workflow_step.id: workflow_step for workflow_step in self.steps}

        upstream: set[UUID] = set()
        pending = list(step.depends_on)

        while pending:
            dependency_id = pending.pop()

            if dependency_id in upstream:
                continue

            upstream.add(dependency_id)

            dependency = steps_by_id[dependency_id]
            pending.extend(dependency.depends_on)

        return upstream
