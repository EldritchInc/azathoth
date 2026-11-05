"""Tests for keeping a runtime until production moves on (ADR 0111)."""

from uuid import UUID

from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import LanguageModelRegistry, ModelCatalog, ModelPortfolio, Prompt
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp.runtimes import RuntimeProvider

WORKFLOW_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

OTHER_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")


def production_state(
    workflow_id: UUID,
    version: str = "1.0.0",
) -> WorkflowProductionState:
    """Return a one-step production state of one workflow at one version."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name="runtime-workflow",
                description="Exercise the runtime provider.",
                version=version,
            ),
            steps=(
                WorkflowStepSpecification(
                    id=UUID(int=1),
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=UUID(int=2),
                            name="runtime-step",
                            description="Exercise the runtime provider.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(text="Go."),
                        model_selection=FixedModelSelection(provider="test-provider", model="m"),
                    ),
                ),
            ),
        ),
    )


class Loader:
    """Compose runtimes holding whatever states are current, counting each."""

    def __init__(
        self,
        *states: WorkflowProductionState,
    ) -> None:
        self.states = states
        self.loads = 0

    def __call__(
        self,
    ) -> AzathothRuntime:
        self.loads += 1

        return AzathothRuntime(
            workflows=WorkflowCatalog(),
            production_states=self.states,
            models=ModelCatalog(),
            portfolio=ModelPortfolio(),
            language_models=LanguageModelRegistry({}),
        )


def test_the_first_call_composes_a_runtime() -> None:
    loader = Loader(production_state(WORKFLOW_ID))
    provider = RuntimeProvider(loader)

    runtime = provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))

    assert loader.loads == 1
    assert runtime.production_state(WORKFLOW_ID) == production_state(WORKFLOW_ID)


def test_the_runtime_is_kept_while_it_holds_the_state() -> None:
    loader = Loader(production_state(WORKFLOW_ID), production_state(OTHER_ID))
    provider = RuntimeProvider(loader)

    first = provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))
    second = provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))
    third = provider.runtime_for(OTHER_ID, production_state(OTHER_ID))

    assert first is second is third
    assert loader.loads == 1


def test_a_runtime_holding_another_state_is_composed_again() -> None:
    loader = Loader(production_state(WORKFLOW_ID))
    provider = RuntimeProvider(loader)

    first = provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))

    loader.states = (production_state(WORKFLOW_ID, version="2.0.0"),)

    second = provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID, version="2.0.0"))

    assert second is not first
    assert loader.loads == 2
    assert second.production_state(WORKFLOW_ID) == production_state(WORKFLOW_ID, version="2.0.0")


def test_a_runtime_without_the_workflow_is_composed_again() -> None:
    loader = Loader()
    provider = RuntimeProvider(loader)

    provider.runtime_for(WORKFLOW_ID, None)
    provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))

    assert loader.loads == 2


def test_preloading_composes_the_runtime_the_first_call_keeps() -> None:
    loader = Loader(production_state(WORKFLOW_ID))
    provider = RuntimeProvider(loader)

    provider.preload()

    assert loader.loads == 1

    provider.runtime_for(WORKFLOW_ID, production_state(WORKFLOW_ID))

    assert loader.loads == 1


def test_preloading_again_composes_again() -> None:
    loader = Loader(production_state(WORKFLOW_ID))
    provider = RuntimeProvider(loader)

    provider.preload()
    provider.preload()

    assert loader.loads == 2
