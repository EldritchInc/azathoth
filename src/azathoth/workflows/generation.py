"""Generate executable workflow candidates."""

from azathoth.prompting import (
    ContextPromptStrategySpec,
    PromptStrategySpec,
    generate_context_prompt_candidates,
    generate_prompt_candidates,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
)
from azathoth.tools import (
    RuntimeToolExecutor,
    ToolImplementationResolver,
    ToolResolver,
    ToolStrategy,
    unsupported_runtime_message,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateStep,
)
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.steps import ToolStepSpecification, WorkflowStepSpecification


class WorkflowGenerationError(Exception):
    """Raised when a workflow specification cannot become executable."""


def generate_workflow_candidate(
    specification: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    *,
    portfolio: ModelPortfolio,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
    revision: int | None = None,
) -> WorkflowCandidate:
    """Generate one executable candidate from a workflow specification.

    The revision names the imported specification revision being generated,
    and is carried by the candidate into its signature and every run.
    """

    executable_steps: list[WorkflowCandidateStep] = []

    for workflow_step in specification.steps:
        strategies = generate_step_strategies(
            workflow_step,
            catalog,
            registry,
            portfolio=portfolio,
            tool_resolver=tool_resolver,
            tool_implementation_resolver=tool_implementation_resolver,
        )

        if not strategies:
            kind = (
                "context prompt"
                if isinstance(workflow_step.specification, ContextPromptStrategySpec)
                else "prompt"
            )

            raise WorkflowGenerationError(
                f"No executable {kind} candidate could be generated for "
                f"workflow step {workflow_step.id}."
            )

        strategy = strategies[0]

        executable_steps.append(
            WorkflowCandidateStep(
                id=workflow_step.id,
                strategy=strategy,
                depends_on=workflow_step.depends_on,
                inputs=workflow_step.inputs,
                outputs=workflow_step.outputs,
                conditions=workflow_step.conditions,
                retry_policy=workflow_step.retry_policy,
                failure_policy=workflow_step.failure_policy,
                message=workflow_step.message,
                emit_values=workflow_step.emit_values,
                confidence=workflow_step.confidence,
            )
        )

    return WorkflowCandidate(
        metadata=specification.metadata,
        steps=tuple(executable_steps),
        result=specification.result,
        revision=revision,
    )


def generate_step_strategies(
    workflow_step: WorkflowStepSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    *,
    portfolio: ModelPortfolio,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> tuple[Strategy, ...]:
    """Return the executable strategies one step could run as, in the order they are tried.

    A tool step resolves to the one implementation it would run. A prompt
    step's strategies are one per model it could run on, the first being the
    one a candidate uses; there are none when no model it may use is served.

    Raises:
        WorkflowGenerationError: A tool step's tool cannot be resolved, or
            its implementation cannot be run.
    """

    step_specification = workflow_step.specification

    if isinstance(step_specification, ToolStepSpecification):
        return (
            _generate_tool_strategy(
                step_specification,
                tool_resolver=tool_resolver,
                tool_implementation_resolver=tool_implementation_resolver,
            ),
        )

    if isinstance(step_specification, ContextPromptStrategySpec):
        return generate_context_prompt_candidates(
            specification=step_specification,
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
        )

    assert isinstance(step_specification, PromptStrategySpec)

    return generate_prompt_candidates(
        specification=step_specification,
        catalog=catalog,
        registry=registry,
        portfolio=portfolio,
    )


def _generate_tool_strategy(
    specification: ToolStepSpecification,
    *,
    tool_resolver: ToolResolver | None,
    tool_implementation_resolver: ToolImplementationResolver | None,
) -> ToolStrategy:
    """Resolve one tool-backed step into an executable strategy."""

    if tool_resolver is None:
        raise WorkflowGenerationError("Tool-backed workflow steps require a tool resolver.")

    if tool_implementation_resolver is None:
        raise WorkflowGenerationError(
            "Tool-backed workflow steps require a tool implementation resolver."
        )

    definitions = tool_resolver.resolve(
        specification.requirement,
    )

    if not definitions:
        raise WorkflowGenerationError(
            f"No tool definition satisfies requirement {specification.requirement.name!r}."
        )

    for definition in definitions:
        implementations = tool_implementation_resolver.resolve_for_requirement(
            definition,
            specification.requirement,
        )

        if not implementations:
            continue

        implementation = implementations[0]

        executor = RuntimeToolExecutor()

        #
        # Fail fast: an implementation no executor can run is rejected
        # before any workflow step executes.
        #
        if not executor.supports(implementation.runtime):
            raise WorkflowGenerationError(
                unsupported_runtime_message(implementation),
            )

        return ToolStrategy(
            metadata=StrategyMetadata(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                version=definition.version,
            ),
            implementation=implementation,
            executor=executor,
        )

    raise WorkflowGenerationError(
        "No executable tool implementation satisfies requirement "
        f"{specification.requirement.name!r}."
    )
