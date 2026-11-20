"""Contract tests for an instance's reusable goals through the service API (ADR 0133)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli import import_goal, list_goals, show_goal
from azathoth.goals import Goal, encode_goal_document
from azathoth.persistence.repositories import open_repositories
from tests.api.test_browse import MISSING_ID, parses
from tests.cli.test_experiment_commands import configure_database

FIRST_GOAL_ID = UUID("9a000000-0000-4000-8000-000000000001")

SECOND_GOAL_ID = UUID("9a000000-0000-4000-8000-000000000002")


def answer_accurately() -> Goal:
    """Return a goal with constraints."""

    return Goal(
        id=FIRST_GOAL_ID,
        name="Answer accurately",
        description="Produce the correct answer for the supplied request.",
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
        ),
        constraints=("Do not rely on unavailable external state.",),
    )


def answer_briefly() -> Goal:
    """Return a goal without constraints."""

    return Goal(
        id=SECOND_GOAL_ID,
        name="Answer briefly",
        description="Answer in as few words as the answer needs.",
        success_criteria=("The answer is one sentence.",),
    )


def save_goals(
    location: str,
    *goals: Goal,
) -> None:
    """Save each goal, in order."""

    repository = open_repositories(location).goals

    for goal in goals:
        repository.save(goal)


#
# Reading
#


def test_goals_are_listed_in_import_order(
    location: str,
    instance: api.Azathoth,
) -> None:
    save_goals(location, answer_briefly(), answer_accurately())

    listed = instance.goals.list()

    assert [goal.id for goal in listed] == [SECOND_GOAL_ID, FIRST_GOAL_ID]
    assert listed[1] == api.GoalSummary(
        id=FIRST_GOAL_ID,
        name="Answer accurately",
        description="Produce the correct answer for the supplied request.",
        command=f"azathoth goal show {FIRST_GOAL_ID}",
    )
    assert all(parses(goal.command) for goal in listed)


def test_an_instance_without_goals_lists_none(
    instance: api.Azathoth,
) -> None:
    assert instance.goals.list() == ()


def test_a_goal_is_shown_whole_with_its_document(
    location: str,
    instance: api.Azathoth,
) -> None:
    save_goals(location, answer_accurately())

    goal = instance.goals.get(FIRST_GOAL_ID)

    assert goal.success_criteria == answer_accurately().success_criteria
    assert goal.constraints == ("Do not rely on unavailable external state.",)
    assert goal.document == json.loads(encode_goal_document(answer_accurately()))


def test_a_goal_without_constraints_has_none(
    location: str,
    instance: api.Azathoth,
) -> None:
    save_goals(location, answer_briefly())

    assert instance.goals.get(SECOND_GOAL_ID).constraints == ()


def test_an_unknown_goal_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        instance.goals.get(MISSING_ID)

    assert str(raised.value) == f"Goal {MISSING_ID} is not configured."
    assert raised.value.code == "not_found"


#
# Importing
#


def test_a_goal_document_is_imported_as_text_or_values(
    instance: api.Azathoth,
) -> None:
    from_text = instance.goals.import_document(encode_goal_document(answer_accurately()))
    from_values = instance.goals.import_document(json.loads(encode_goal_document(answer_briefly())))

    assert from_text.goal == instance.goals.get(FIRST_GOAL_ID)
    assert from_values.goal == instance.goals.get(SECOND_GOAL_ID)


def test_a_document_that_is_not_a_goal_is_refused(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidDocumentError) as raised:
        instance.goals.import_document('{"name": "No criteria"}')

    assert str(raised.value) == "Goal document is not a valid Goal."
    assert raised.value.code == "invalid_document"
    assert instance.goals.list() == ()


def test_a_goal_whose_id_is_taken_is_never_replaced(
    location: str,
    instance: api.Azathoth,
) -> None:
    save_goals(location, answer_accurately())
    renamed = answer_accurately().model_copy(update={"name": "Renamed"})

    with pytest.raises(api.ConflictError) as raised:
        instance.goals.import_document(encode_goal_document(renamed))

    assert str(raised.value) == f"Goal {FIRST_GOAL_ID} already exists."
    assert raised.value.code == "conflict"
    assert instance.goals.get(FIRST_GOAL_ID).name == "Answer accurately"


def test_a_closed_instance_refuses_goals(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.goals.list()


#
# The commands
#


def test_the_goal_commands_print_what_the_api_returns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    location = str(configure_database(monkeypatch, tmp_path))
    document = tmp_path / "goal.json"
    document.write_text(encode_goal_document(answer_accurately()), encoding="utf-8")

    assert import_goal(document) == 0
    assert capsys.readouterr().out == f"Imported goal {FIRST_GOAL_ID}.\n"

    save_goals(location, answer_briefly())

    assert list_goals() == 0
    assert capsys.readouterr().out == (
        f"{FIRST_GOAL_ID}  Answer accurately\n{SECOND_GOAL_ID}  Answer briefly\n"
    )

    assert show_goal(SECOND_GOAL_ID) == 0
    assert capsys.readouterr().out == (
        f"ID: {SECOND_GOAL_ID}\n"
        "Name: Answer briefly\n"
        "Description: Answer in as few words as the answer needs.\n"
        "Success Criteria:\n"
        "  - The answer is one sentence.\n"
        "Constraints:\n"
        "  None\n"
    )


def test_the_goal_commands_say_what_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(monkeypatch, tmp_path)
    document = tmp_path / "goal.json"
    document.write_text(encode_goal_document(answer_accurately()), encoding="utf-8")

    assert show_goal(MISSING_ID) == 1
    assert capsys.readouterr().err == f"Goal {MISSING_ID} is not configured.\n"
    assert import_goal(document) == 0
    capsys.readouterr()
    assert import_goal(document) == 1
    assert capsys.readouterr().err == f"Goal {FIRST_GOAL_ID} already exists.\n"
