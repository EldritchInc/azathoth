"""Tests for judge calls and cost in rendered experiment records."""

from pydantic import JsonValue

from azathoth.cli import render_workflow_experiment
from azathoth.workflows import WorkflowExperimentRecord
from tests.cli.test_experiment_rendering import (
    LOSING_OBSERVATION_ID,
    WINNING_OBSERVATION_ID,
    create_experiment,
    create_legacy_experiment,
)


def with_case_judging(
    experiment: WorkflowExperimentRecord,
    judging: dict[str, tuple[tuple[int, float], ...]],
) -> WorkflowExperimentRecord:
    """Return the experiment with judge calls and cost on some observations' cases.

    The judging maps an observation ID to one call count and cost per case,
    in case order. Observations it does not name keep no judge evidence.
    """

    payload = experiment.model_dump(mode="json")

    observations = payload["observations"]

    assert isinstance(observations, list)

    for observation in observations:
        assert isinstance(observation, dict)

        case_judging = judging.get(str(observation["id"]))

        if case_judging is None:
            continue

        cases = observation["cases"]

        assert isinstance(cases, list)

        for case, (calls, cost) in zip(
            cases,
            case_judging,
            strict=True,
        ):
            assert isinstance(case, dict)

            case["judge_calls"] = calls
            case["judge_cost_usd"] = cost

    return WorkflowExperimentRecord.model_validate(payload)


def observation_lines(
    rendered: str,
    rank: int,
) -> list[str]:
    """Return the rendered lines of one ranked observation."""

    lines = rendered.splitlines()

    start = lines.index(f"Rank {rank}")

    following = [
        index for index, line in enumerate(lines) if index > start and line.startswith("Rank ")
    ]

    end = following[0] - 1 if following else len(lines)

    return lines[start:end]


def judged_experiment() -> WorkflowExperimentRecord:
    """Return the rendered experiment with judging on the winner only."""

    return with_case_judging(
        create_experiment(),
        {
            str(WINNING_OBSERVATION_ID): (
                (1, 0.25),
                (2, 0.125),
            ),
        },
    )


def test_detail_ends_a_judged_observation_with_its_judge_calls_and_cost() -> None:
    lines = observation_lines(
        render_workflow_experiment(judged_experiment()),
        1,
    )

    assert lines[-3:] == [
        "Rationale: Correct and inexpensive.",
        "Judge Calls: 3",
        "Judge Cost: $0.375000",
    ]


def test_detail_shows_no_judge_lines_for_an_unjudged_observation() -> None:
    lines = observation_lines(
        render_workflow_experiment(judged_experiment()),
        2,
    )

    assert lines[-1] == "Overall: 0.400000"
    assert not any(line.startswith("Judge ") for line in lines)


def test_detail_keeps_judging_out_of_the_scores() -> None:
    plain = render_workflow_experiment(create_experiment()).splitlines()
    judged = render_workflow_experiment(judged_experiment()).splitlines()

    assert [line for line in judged if not line.startswith("Judge ")] == plain


def test_detail_renders_judging_on_every_judged_observation() -> None:
    experiment = with_case_judging(
        create_experiment(),
        {
            str(WINNING_OBSERVATION_ID): (
                (1, 0.5),
                (1, 0.5),
            ),
            str(LOSING_OBSERVATION_ID): (
                (0, 0.0),
                (4, 2.0),
            ),
        },
    )

    rendered = render_workflow_experiment(experiment)

    assert observation_lines(rendered, 1)[-2:] == [
        "Judge Calls: 2",
        "Judge Cost: $1.000000",
    ]
    assert observation_lines(rendered, 2)[-2:] == [
        "Judge Calls: 4",
        "Judge Cost: $2.000000",
    ]


def test_detail_of_a_legacy_experiment_shows_no_judge_lines() -> None:
    rendered = render_workflow_experiment(create_legacy_experiment())

    assert "Judge " not in rendered


def test_judged_payload_round_trips_through_json() -> None:
    experiment = judged_experiment()

    decoded: JsonValue = experiment.model_dump(mode="json")

    assert WorkflowExperimentRecord.model_validate(decoded) == experiment
