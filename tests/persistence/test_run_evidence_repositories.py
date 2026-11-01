"""Contract tests of the run-evidence repositories, on SQLite and PostgreSQL (ADR 0102).

Runs, run evaluations, feedback, experiments and benchmark executions behave
the same in either database: what is saved reads back exactly, in insertion
order, a duplicate is refused without writing anything, and a second
repository over the same database sees everything the first saved.
"""

from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

import pytest

from azathoth.persistence import Database, Table
from azathoth.workflows import (
    WORKFLOW_BENCHMARK_EXECUTION_TABLES,
    WORKFLOW_EXPERIMENT_TABLES,
    WORKFLOW_RUN_EVALUATION_TABLES,
    WORKFLOW_RUN_FEEDBACK_TABLES,
    WORKFLOW_RUN_TABLES,
    SqlWorkflowBenchmarkExecutionRepository,
    SqlWorkflowExperimentRepository,
    SqlWorkflowRunEvaluationRepository,
    SqlWorkflowRunFeedbackRepository,
    SqlWorkflowRunRepository,
    WorkflowBenchmarkExecutionRepository,
    WorkflowExperimentRepository,
    WorkflowRunEvaluationRepository,
    WorkflowRunFeedbackDisposition,
    WorkflowRunFeedbackRepository,
    WorkflowRunRepository,
)
from tests.workflows.test_benchmark_execution_repository import (
    FIRST_BENCHMARK_ID,
    FIRST_EXECUTION_ID,
    FIRST_WORKFLOW_ID,
    SECOND_BENCHMARK_ID,
    SECOND_WORKFLOW_ID,
    THIRD_WORKFLOW_ID,
    create_executions,
    identifier,
)
from tests.workflows.test_experiment_repository import create_experiment
from tests.workflows.test_feedback_repository import create_feedback
from tests.workflows.test_run_evaluation_repository import create_run_evaluation
from tests.workflows.test_run_repository import create_execution, create_run

FIRST = UUID("10000000-0000-4000-8000-000000000001")
SECOND = UUID("10000000-0000-4000-8000-000000000002")
THIRD = UUID("10000000-0000-4000-8000-000000000003")

RUN = UUID("20000000-0000-4000-8000-000000000001")
OTHER_RUN = UUID("20000000-0000-4000-8000-000000000002")

WORKFLOW = UUID("30000000-0000-4000-8000-000000000001")
OTHER_WORKFLOW = UUID("30000000-0000-4000-8000-000000000002")

STRATEGY = UUID("40000000-0000-4000-8000-000000000001")

Repository = TypeVar("Repository")


def initialized(
    database: Database,
    tables: tuple[Table, ...],
    factory: Callable[[Database], Repository],
) -> Repository:
    """Initialize a database with a repository's tables, then open the repository."""

    database.initialize(tables)

    return factory(database)


# Runs


def runs(
    database: Database,
) -> WorkflowRunRepository:
    return initialized(database, WORKFLOW_RUN_TABLES, SqlWorkflowRunRepository)


def test_a_run_reads_back_exactly(
    database: Database,
) -> None:
    repository = runs(database)
    run = create_run(run_id=RUN)

    repository.save(run)

    assert repository.get(RUN) == run
    assert repository.get(OTHER_RUN) is None


def test_runs_keep_insertion_order_and_filter_by_workflow(
    database: Database,
) -> None:
    repository = runs(database)

    saved = (
        create_run(run_id=THIRD, workflow_id=WORKFLOW),
        create_run(run_id=FIRST, workflow_id=OTHER_WORKFLOW),
        create_run(run_id=SECOND, workflow_id=WORKFLOW),
    )

    for run in saved:
        repository.save(run)

    assert repository.runs() == saved
    assert repository.runs_for_workflow(WORKFLOW) == (saved[0], saved[2])
    assert repository.runs_for_workflow(UUID(int=0)) == ()


def test_a_duplicate_run_is_refused(
    database: Database,
) -> None:
    repository = runs(database)
    repository.save(create_run(run_id=RUN))

    with pytest.raises(ValueError, match=f"Workflow run {RUN} already exists."):
        repository.save(create_run(run_id=RUN, workflow_name="another"))

    assert [run.workflow.name for run in repository.runs()] == ["test workflow"]


def test_a_run_survives_a_new_repository(
    database: Database,
) -> None:
    runs(database).save(create_run(run_id=RUN))

    assert SqlWorkflowRunRepository(database).get(RUN) == create_run(run_id=RUN)


def test_a_run_keeps_its_whole_execution_evidence(
    database: Database,
) -> None:
    repository = runs(database)
    run = create_run(run_id=RUN)

    repository.save(run)

    loaded = repository.get(RUN)

    assert loaded is not None
    assert loaded.model_dump_json() == run.model_dump_json()
    assert loaded.steps[0].execution == create_execution()


# Run evaluations


def evaluations(
    database: Database,
) -> WorkflowRunEvaluationRepository:
    return initialized(
        database,
        WORKFLOW_RUN_EVALUATION_TABLES,
        SqlWorkflowRunEvaluationRepository,
    )


def test_run_evaluations_read_back_in_order_and_filter_by_run(
    database: Database,
) -> None:
    repository = evaluations(database)

    saved = (
        create_run_evaluation(evaluation_id=SECOND, run_id=RUN, evaluator_name="exact", score=1.0),
        create_run_evaluation(
            evaluation_id=FIRST, run_id=OTHER_RUN, evaluator_name="judge", score=0.5
        ),
        create_run_evaluation(evaluation_id=THIRD, run_id=RUN, evaluator_name="judge", score=0.0),
    )

    for evaluation in saved:
        repository.save(evaluation)

    assert repository.get(saved[1].id) == saved[1]
    assert repository.get(UUID(int=0)) is None
    assert repository.evaluations() == saved
    assert repository.evaluations_for_run(RUN) == (saved[0], saved[2])


def test_a_duplicate_run_evaluation_is_refused(
    database: Database,
) -> None:
    repository = evaluations(database)
    evaluation = create_run_evaluation(
        evaluation_id=FIRST, run_id=RUN, evaluator_name="exact", score=1.0
    )

    repository.save(evaluation)

    with pytest.raises(ValueError, match=f"Workflow run evaluation {evaluation.id} already"):
        repository.save(evaluation)

    assert repository.evaluations() == (evaluation,)


# Feedback


def feedback(
    database: Database,
) -> WorkflowRunFeedbackRepository:
    return initialized(database, WORKFLOW_RUN_FEEDBACK_TABLES, SqlWorkflowRunFeedbackRepository)


def test_feedback_reads_back_in_order_and_filters_by_run(
    database: Database,
) -> None:
    repository = feedback(database)

    saved = (
        create_feedback(
            feedback_id=SECOND,
            run_id=RUN,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
        ),
        create_feedback(
            feedback_id=FIRST,
            run_id=OTHER_RUN,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="Wrong — and it's 100% wrong?",
        ),
        create_feedback(
            feedback_id=THIRD,
            run_id=RUN,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="Missed the second clause.",
        ),
    )

    for record in saved:
        repository.save(record)

    assert repository.get(FIRST) == saved[1]
    assert repository.get(UUID(int=0)) is None
    assert repository.feedback() == saved
    assert repository.feedback_for_run(RUN) == (saved[0], saved[2])


def test_duplicate_feedback_is_refused(
    database: Database,
) -> None:
    repository = feedback(database)
    record = create_feedback(
        feedback_id=FIRST,
        run_id=RUN,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    repository.save(record)

    with pytest.raises(ValueError, match=f"Workflow run feedback {FIRST} already exists."):
        repository.save(record)


# Experiments


def experiments(
    database: Database,
) -> WorkflowExperimentRepository:
    return initialized(database, WORKFLOW_EXPERIMENT_TABLES, SqlWorkflowExperimentRepository)


def test_experiments_read_back_in_order_and_filter_by_workflow(
    database: Database,
) -> None:
    repository = experiments(database)

    saved = (
        create_experiment(
            experiment_id=SECOND,
            workflow_id=WORKFLOW,
            strategy_id=STRATEGY,
            run_id=RUN,
            evaluation_id=FIRST,
        ),
        create_experiment(
            experiment_id=FIRST,
            workflow_id=OTHER_WORKFLOW,
            strategy_id=STRATEGY,
            run_id=OTHER_RUN,
            evaluation_id=SECOND,
        ),
        create_experiment(
            experiment_id=THIRD,
            workflow_id=WORKFLOW,
            strategy_id=STRATEGY,
            run_id=OTHER_RUN,
            evaluation_id=THIRD,
        ),
    )

    for experiment in saved:
        repository.save(experiment)

    assert repository.get(FIRST) == saved[1]
    assert repository.get(UUID(int=0)) is None
    assert repository.experiments() == saved
    assert repository.experiments_for_workflow(WORKFLOW) == (saved[0], saved[2])
    assert repository.experiments_for_workflow(UUID(int=0)) == ()


def test_an_experiment_observing_one_workflow_twice_is_found_once(
    database: Database,
) -> None:
    repository = experiments(database)
    first = create_experiment(
        experiment_id=FIRST,
        workflow_id=WORKFLOW,
        strategy_id=STRATEGY,
        run_id=RUN,
        evaluation_id=FIRST,
    )
    second = create_experiment(
        experiment_id=FIRST,
        workflow_id=WORKFLOW,
        strategy_id=STRATEGY,
        run_id=OTHER_RUN,
        evaluation_id=SECOND,
    )
    experiment = first.model_copy(
        update={
            "observations": (*first.observations, *second.observations),
            "ranking": (RUN, OTHER_RUN),
        }
    )

    repository.save(experiment)

    assert repository.experiments_for_workflow(WORKFLOW) == (experiment,)


def test_a_duplicate_experiment_is_refused_and_writes_no_index_rows(
    database: Database,
) -> None:
    repository = experiments(database)
    experiment = create_experiment(
        experiment_id=FIRST,
        workflow_id=WORKFLOW,
        strategy_id=STRATEGY,
        run_id=RUN,
        evaluation_id=FIRST,
    )

    repository.save(experiment)

    with pytest.raises(ValueError, match=f"Workflow experiment {FIRST} already exists."):
        repository.save(experiment)

    with database.transaction() as session:
        assert session.fetchone("SELECT COUNT(*) FROM workflow_experiment_observations") == (1,)


# Benchmark executions


def executions(
    database: Database,
) -> WorkflowBenchmarkExecutionRepository:
    return initialized(
        database,
        WORKFLOW_BENCHMARK_EXECUTION_TABLES,
        SqlWorkflowBenchmarkExecutionRepository,
    )


def test_benchmark_executions_read_back_and_filter(
    database: Database,
) -> None:
    repository = executions(database)
    saved = create_executions()

    for execution in saved:
        repository.save(execution)

    first_run, compare, other = saved

    assert repository.get(FIRST_EXECUTION_ID) == first_run
    assert repository.get(UUID(int=0)) is None
    assert repository.executions() == saved
    assert repository.executions_for_benchmark(FIRST_BENCHMARK_ID) == (first_run, compare)
    assert repository.executions_for_benchmark(SECOND_BENCHMARK_ID) == (other,)
    assert repository.executions_for_workflow(FIRST_WORKFLOW_ID) == (first_run, compare)
    assert repository.executions_for_workflow(SECOND_WORKFLOW_ID) == (compare,)
    assert repository.executions_for_workflow(THIRD_WORKFLOW_ID) == (other,)
    assert repository.executions_for_workflow(UUID(int=0)) == ()


def test_a_benchmark_execution_is_found_by_any_run_it_produced(
    database: Database,
) -> None:
    repository = executions(database)
    saved = create_executions()

    for execution in saved:
        repository.save(execution)

    for execution in saved:
        for candidate in execution.candidates:
            for case in candidate.cases:
                assert repository.execution_for_run(case.run_id) == execution

    assert repository.execution_for_run(identifier(99, 0)) is None


def test_a_duplicate_benchmark_execution_is_refused_and_writes_no_index_rows(
    database: Database,
) -> None:
    repository = executions(database)
    execution = create_executions()[0]

    repository.save(execution)

    with database.transaction() as session:
        before = session.fetchone("SELECT COUNT(*) FROM workflow_benchmark_execution_cases")

    with pytest.raises(ValueError, match=f"Benchmark execution {execution.id} already exists."):
        repository.save(execution)

    with database.transaction() as session:
        assert session.fetchone("SELECT COUNT(*) FROM workflow_benchmark_execution_cases") == (
            before
        )
