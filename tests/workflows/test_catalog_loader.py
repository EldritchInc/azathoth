"""Tests for loading immutable workflow catalogs from repositories."""

from pathlib import Path
from uuid import UUID

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryWorkflowRepository,
    SQLiteWorkflowRepository,
    WorkflowCatalog,
    WorkflowCatalogLoader,
    WorkflowMetadata,
    WorkflowRepository,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
FIRST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
FIRST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
) -> WorkflowSpecification:
    """Create one deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{name} strategy",
                        description=f"Execute the {name} strategy.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=f"Execute {name}.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
            ),
        ),
    )


def create_first_workflow() -> WorkflowSpecification:
    """Create the first persisted workflow."""

    return create_workflow(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        name="first workflow",
    )


def create_second_workflow() -> WorkflowSpecification:
    """Create the second persisted workflow."""

    return create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
        name="second workflow",
    )


def populate_repository(
    repository: WorkflowRepository,
) -> tuple[
    WorkflowSpecification,
    WorkflowSpecification,
]:
    """Persist two workflows in deterministic order."""

    first = create_first_workflow()
    second = create_second_workflow()

    repository.save(first)
    repository.save(second)

    return (
        first,
        second,
    )


def assert_loaded_catalog(
    repository: WorkflowRepository,
) -> None:
    """Assert repository state hydrates one deterministic catalog."""

    expected = populate_repository(repository)

    catalog = WorkflowCatalogLoader(
        repository,
    ).load_catalog()

    assert catalog == WorkflowCatalog(
        specifications=expected,
    )

    assert catalog.specifications == expected

    assert catalog.identifiers == (
        FIRST_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )


def test_loader_loads_in_memory_repository() -> None:
    assert_loaded_catalog(InMemoryWorkflowRepository())


def test_loader_loads_sqlite_repository(
    tmp_path: Path,
) -> None:
    assert_loaded_catalog(SQLiteWorkflowRepository(tmp_path / "workflows.db"))


def test_loader_returns_empty_catalog_for_empty_repository() -> None:
    catalog = WorkflowCatalogLoader(InMemoryWorkflowRepository()).load_catalog()

    assert catalog == WorkflowCatalog()


def test_sqlite_loader_reads_reconstructed_repository(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflows.db"

    repository = SQLiteWorkflowRepository(database)

    expected = populate_repository(repository)

    reconstructed_repository = SQLiteWorkflowRepository(database)

    catalog = WorkflowCatalogLoader(
        reconstructed_repository,
    ).load_catalog()

    assert catalog.specifications == expected


def test_loader_accepts_repository_protocol() -> None:
    repository: WorkflowRepository = InMemoryWorkflowRepository()

    catalog = WorkflowCatalogLoader(
        repository,
    ).load_catalog()

    assert catalog == WorkflowCatalog()
