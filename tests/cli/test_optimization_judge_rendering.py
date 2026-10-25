"""Tests for judge calls and cost in rendered optimization sessions."""

from azathoth.cli import render_workflow_optimization_session
from azathoth.optimization import (
    WorkflowOptimizationResult,
    WorkflowOptimizationSession,
)
from azathoth.workflows import (
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
)
from tests.cli.test_optimization_rendering import create_session


def with_judging(
    session: WorkflowOptimizationSession,
    judging: tuple[tuple[tuple[int, float], ...], ...],
) -> WorkflowOptimizationSession:
    """Return the session with judge calls and cost on each generation's evidence.

    The judging holds one entry per generation, each holding one call count
    and cost per evaluated candidate in evidence order.
    """

    generations = []

    for result, generation_judging in zip(
        session.generations,
        judging,
        strict=True,
    ):
        experiment = result.previous_experiment

        generations.append(
            WorkflowOptimizationResult(
                generation=result.generation,
                previous_experiment=WorkflowExperimentResult(
                    id=experiment.id,
                    evidence=tuple(
                        WorkflowExperimentEvidence(
                            candidate_signature=observation.candidate_signature,
                            scorecard=observation.scorecard,
                            judge_calls=calls,
                            judge_cost_usd=cost,
                        )
                        for observation, (calls, cost) in zip(
                            experiment.evidence,
                            generation_judging,
                            strict=True,
                        )
                    ),
                    ranking=experiment.ranking,
                ),
                candidates=result.candidates,
            )
        )

    return WorkflowOptimizationSession(
        initial_candidates=session.initial_candidates,
        generations=tuple(generations),
    )


def judged_session() -> WorkflowOptimizationSession:
    """Return the two-generation session with judging in both generations."""

    return with_judging(
        create_session(),
        (
            ((2, 0.25),),
            (
                (3, 0.5),
                (1, 0.125),
            ),
        ),
    )


def generation_lines(
    rendered: str,
    generation: int,
) -> list[str]:
    """Return the rendered lines of one generation, up to the next one."""

    lines = rendered.splitlines()

    start = lines.index(f"Generation {generation}")

    following = [
        index
        for index, line in enumerate(lines)
        if index > start and line.startswith("Generation ")
    ]

    return lines[start : following[0] if following else len(lines)]


def test_render_totals_judging_after_the_summary() -> None:
    rendered = render_workflow_optimization_session(judged_session())

    lines = rendered.splitlines()

    generations = lines.index("Generations: 2")

    assert lines[generations + 1] == "Total Judge Calls: 6"
    assert lines[generations + 2] == "Total Judge Cost: $0.875000"


def test_render_reports_each_generations_judging_over_every_candidate() -> None:
    rendered = render_workflow_optimization_session(judged_session())

    first = generation_lines(rendered, 1)
    second = generation_lines(rendered, 2)

    assert first[2:5] == [
        "Evaluated Candidates: 1",
        "Judge Calls: 2",
        "Judge Cost: $0.250000",
    ]
    assert second[2:5] == [
        "Evaluated Candidates: 2",
        "Judge Calls: 4",
        "Judge Cost: $0.625000",
    ]


def test_render_reports_zero_judging_without_judges() -> None:
    rendered = render_workflow_optimization_session(create_session())

    assert "Total Judge Calls: 0\n" in rendered
    assert "Total Judge Cost: $0.000000\n" in rendered

    for generation in (1, 2):
        lines = generation_lines(rendered, generation)

        assert "Judge Calls: 0" in lines
        assert "Judge Cost: $0.000000" in lines


def test_render_keeps_judging_out_of_the_winner_scores() -> None:
    plain = render_workflow_optimization_session(create_session())
    judged = render_workflow_optimization_session(judged_session())

    def scores(rendered: str) -> list[str]:
        return [line for line in rendered.splitlines() if line.startswith("  ")]

    assert scores(judged) == scores(plain)


def test_render_without_generations_totals_zero_judging() -> None:
    session = WorkflowOptimizationSession(
        initial_candidates=create_session().initial_candidates,
    )

    rendered = render_workflow_optimization_session(session)

    assert rendered.splitlines()[-2:] == [
        "Total Judge Calls: 0",
        "Total Judge Cost: $0.000000",
    ]
