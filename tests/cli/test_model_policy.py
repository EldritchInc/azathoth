"""Tests that operators declare what a model's provider does with data (ADR 0123)."""

from pathlib import Path

import pytest

from azathoth.cli import main
from azathoth.providers import (
    ModelCatalog,
    ModelPortfolio,
    ModelPortfolioEntry,
    SQLiteModelPortfolioRepository,
)
from azathoth.revisions import AUTHOR_VARIABLE
from azathoth.sensitivity import (
    PRIVATE_DATA_POLICY,
    RESTRICTED_REFUSAL_HINT,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    PolicyAnswer,
)
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_models import configure_authorization_runtime, create_first_model
from tests.cli.test_workflow_run import configure_database

MODEL = create_first_model()

ENTRY = ModelPortfolioEntry(provider=MODEL.provider, model=MODEL.model)


def run(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


def authorized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entry: ModelPortfolioEntry = ENTRY,
) -> SQLiteModelPortfolioRepository:
    """Return a database whose portfolio holds one entry, and a CLI that cannot load a runtime."""

    database = configure_database(monkeypatch, tmp_path)
    repository = SQLiteModelPortfolioRepository(database)

    repository.save(entry)
    forbid_runtime(monkeypatch)

    return repository


def policy_of(
    repository: SQLiteModelPortfolioRepository,
) -> DataPolicy:
    entry = repository.get(ENTRY.identifier)

    assert entry is not None

    return entry.data_policy


# Authorizing


@pytest.mark.parametrize(
    ("options", "policy"),
    [
        ((), UNKNOWN_DATA_POLICY),
        (("--no-retention", "--no-training"), PRIVATE_DATA_POLICY),
        (("--no-retention",), DataPolicy(retains_data=PolicyAnswer.NO)),
        (
            ("--retains-data", "yes", "--trains-on-data", "no"),
            DataPolicy(retains_data=PolicyAnswer.YES, trains_on_data=PolicyAnswer.NO),
        ),
    ],
    ids=["undeclared", "private", "retention-only", "spelled-out"],
)
def test_authorizing_a_model_declares_its_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    options: tuple[str, ...],
    policy: DataPolicy,
) -> None:
    database = tmp_path / "azathoth.db"
    monkeypatch.setenv(AUTHOR_VARIABLE, "Eris")

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(models=(MODEL,)),
        portfolio=ModelPortfolio(),
    )

    status, out, err = run(capsys, "model", "authorize", MODEL.identifier, *options)

    assert (status, out, err) == (0, f"Authorized model {MODEL.identifier}.\n", "")
    assert SQLiteModelPortfolioRepository(database).entries() == (
        ENTRY.model_copy(update={"data_policy": policy}),
    )


# Showing


def test_the_policy_is_shown_without_loading_the_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authorized(monkeypatch, tmp_path)

    assert run(capsys, "model", "policy", ENTRY.identifier) == (
        0,
        "Retains Data: unknown\nTrains On Data: unknown\nRestricted Input: refused\n",
        "",
    )


def test_a_private_models_policy_allows_restricted_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authorized(monkeypatch, tmp_path, ENTRY.model_copy(update={"data_policy": PRIVATE_DATA_POLICY}))

    assert run(capsys, "model", "policy", ENTRY.identifier) == (
        0,
        "Retains Data: no\nTrains On Data: no\nRestricted Input: allowed\n",
        "",
    )


# Declaring


def test_declaring_both_answers_allows_restricted_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = authorized(monkeypatch, tmp_path)

    assert run(capsys, "model", "policy", ENTRY.identifier, "--no-retention", "--no-training") == (
        0,
        f"Declared the data policy of model {ENTRY.identifier}.\n"
        "Retains Data: no\nTrains On Data: no\nRestricted Input: allowed\n",
        "",
    )
    assert policy_of(repository) == PRIVATE_DATA_POLICY


def test_an_answer_not_given_is_kept(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = authorized(
        monkeypatch,
        tmp_path,
        ENTRY.model_copy(update={"data_policy": PRIVATE_DATA_POLICY}),
    )

    status, out, _ = run(capsys, "model", "policy", ENTRY.identifier, "--trains-on-data", "yes")

    assert status == 0
    assert out.endswith("Retains Data: no\nTrains On Data: yes\nRestricted Input: refused\n")
    assert policy_of(repository) == DataPolicy(
        retains_data=PolicyAnswer.NO,
        trains_on_data=PolicyAnswer.YES,
    )

    run(capsys, "model", "policy", ENTRY.identifier, "--retains-data", "unknown")

    assert policy_of(repository) == DataPolicy(trains_on_data=PolicyAnswer.YES)


def test_the_refusal_hints_command_declares_the_model_private(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = authorized(monkeypatch, tmp_path)

    hint = RESTRICTED_REFUSAL_HINT.format(model=ENTRY.identifier)
    command = hint.split("`")[1].split()

    assert command[0] == "azathoth"

    status, _, err = run(capsys, *command[1:])

    assert (status, err) == (0, "")
    assert policy_of(repository) == PRIVATE_DATA_POLICY


def test_the_policy_of_a_model_not_authorized_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = authorized(monkeypatch, tmp_path)

    for options in ((), ("--no-retention",)):
        assert run(capsys, "model", "policy", "openrouter/example/missing", *options) == (
            1,
            "",
            "Model 'openrouter/example/missing' is not authorized.\n",
        )

    assert repository.entries() == (ENTRY,)


# Usage


@pytest.mark.parametrize("action", ["authorize", "policy"])
@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            ("--no-retention", "--retains-data", "yes"),
            "argument --retains-data: not allowed with argument --no-retention",
        ),
        (
            ("--no-training", "--trains-on-data", "no"),
            "argument --trains-on-data: not allowed with argument --no-training",
        ),
        (
            ("--retains-data", "maybe"),
            "argument --retains-data: invalid choice: 'maybe'",
        ),
    ],
    ids=["retention-twice", "training-twice", "unknown-answer"],
)
def test_contradictory_or_unknown_answers_are_usage_errors(
    capsys: pytest.CaptureFixture[str],
    action: str,
    options: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(("model", action, ENTRY.identifier, *options))

    assert exited.value.code == 2
    assert message in capsys.readouterr().err


def test_the_policy_options_are_described_in_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for action in ("authorize", "policy"):
        with pytest.raises(SystemExit):
            main(("model", action, "--help"))

        out = capsys.readouterr().out

        for option in ("--no-retention", "--retains-data", "--no-training", "--trains-on-data"):
            assert option in out


def test_the_documented_policy_output_is_the_one_shown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authorized(monkeypatch, tmp_path)

    _, out, _ = run(
        capsys,
        "model",
        "policy",
        ENTRY.identifier,
        "--no-retention",
        "--no-training",
    )
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

    documented = out.replace(ENTRY.identifier, "<MODEL_IDENTIFIER>")

    assert f"```text\n{documented}```" in readme.read_text(encoding="utf-8")
