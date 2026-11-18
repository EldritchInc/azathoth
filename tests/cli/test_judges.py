"""Tests for semantic judge rotation commands in the Azathoth CLI (ADR 0129)."""

from pathlib import Path

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
import azathoth.cli.judges as judge_commands
from azathoth import api
from azathoth.cli import (
    CliRuntimeConfiguration,
    add_judge,
    list_judges,
    remove_judge,
)
from azathoth.evaluation import (
    JudgeEntry,
    SQLiteJudgeRotationRepository,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import (
    ModelCatalog,
    ModelMetadata,
    ModelPortfolioEntry,
    ProviderModel,
)
from tests.api.test_models import StaticDirectory

ALPHA = ProviderModel(
    provider="openrouter",
    model="example/alpha",
    display_name="Alpha",
)

BETA = ProviderModel(
    provider="openrouter",
    model="example/beta",
    display_name="Beta",
)

UNKNOWN_IDENTIFIER = "openrouter/example/missing"


def configure(
    *,
    monkeypatch: pytest.MonkeyPatch,
    database: Path,
    models: tuple[ProviderModel, ...] = (ALPHA, BETA),
    authorized: tuple[ProviderModel, ...] = (ALPHA, BETA),
) -> SQLiteJudgeRotationRepository:
    """Point the CLI at an isolated database whose providers serve `models`.

    The portfolio authorizes `authorized`, and the service API the judge
    commands call reaches providers that serve `models` and nothing else.
    """

    configuration = CliRuntimeConfiguration(
        database=database,
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    stores = open_repositories(database)

    for model in authorized:
        stores.portfolio.save(ModelPortfolioEntry(provider=model.provider, model=model.model))

    monkeypatch.setattr(
        judge_commands,
        "provider_instance",
        lambda _configuration: api.Azathoth(
            open_repositories(database),
            directories=(StaticDirectory("openrouter", models),),
        ),
    )

    return SQLiteJudgeRotationRepository(database)


def forbid_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail the test if a command reaches the providers."""

    def fail(
        _configuration: CliRuntimeConfiguration,
    ) -> api.Azathoth:
        raise AssertionError("Providers must not be reached.")

    monkeypatch.setattr(
        judge_commands,
        "provider_instance",
        fail,
    )


def test_judge_add_appends_authorized_available_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    assert add_judge(BETA.identifier) == 0
    assert add_judge(ALPHA.identifier) == 0

    captured = capsys.readouterr()

    assert captured.out == (f"Added judge {BETA.identifier}.\nAdded judge {ALPHA.identifier}.\n")
    assert captured.err == ""
    assert repository.rotation().entries == (
        JudgeEntry(
            provider="openrouter",
            model="example/beta",
        ),
        JudgeEntry(
            provider="openrouter",
            model="example/alpha",
        ),
    )


def test_judge_add_sees_the_models_every_command_discovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    configuration = CliRuntimeConfiguration(database=database)

    monkeypatch.setattr(CliRuntimeConfiguration, "from_environment", lambda: configuration)
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(ModelMetadata(provider="openrouter", model="example/alpha", display_name="A"),)
        ),
    )

    stores = open_repositories(database)

    for model in (ALPHA, BETA):
        stores.portfolio.save(ModelPortfolioEntry(provider=model.provider, model=model.model))

    assert add_judge(ALPHA.identifier) == 0
    assert add_judge(BETA.identifier) == 1

    captured = capsys.readouterr()

    assert captured.out == f"Added judge {ALPHA.identifier}.\n"
    assert captured.err == f"Model {BETA.identifier!r} is not currently available.\n"
    assert SQLiteJudgeRotationRepository(database).rotation().identifiers == (ALPHA.identifier,)


def test_judge_add_rejects_model_not_currently_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    assert add_judge(UNKNOWN_IDENTIFIER) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Model {UNKNOWN_IDENTIFIER!r} is not currently available.\n"
    assert repository.rotation().entries == ()


def test_judge_add_rejects_unauthorized_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
        authorized=(ALPHA,),
    )

    assert add_judge(BETA.identifier) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Model {BETA.identifier!r} is not authorized.\n"
    assert repository.rotation().entries == ()


def test_judge_add_rejects_judge_already_in_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    assert add_judge(ALPHA.identifier) == 0

    capsys.readouterr()

    assert add_judge(ALPHA.identifier) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Judge {ALPHA.identifier!r} is already in the rotation.\n"
    assert repository.rotation().identifiers == (ALPHA.identifier,)


def test_judge_remove_removes_judge_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    add_judge(ALPHA.identifier)
    add_judge(BETA.identifier)

    capsys.readouterr()

    forbid_runtime(monkeypatch)

    assert remove_judge(ALPHA.identifier) == 0

    captured = capsys.readouterr()

    assert captured.out == f"Removed judge {ALPHA.identifier}.\n"
    assert captured.err == ""
    assert repository.rotation().identifiers == (BETA.identifier,)


def test_judge_remove_rejects_unknown_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    forbid_runtime(monkeypatch)

    assert remove_judge(ALPHA.identifier) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Judge {ALPHA.identifier!r} is not in the rotation.\n"


def test_judge_list_prints_rotation_in_order_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    add_judge(BETA.identifier)
    add_judge(ALPHA.identifier)

    capsys.readouterr()

    forbid_runtime(monkeypatch)

    assert list_judges() == 0

    captured = capsys.readouterr()

    assert captured.out == f"{BETA.identifier}\n{ALPHA.identifier}\n"
    assert captured.err == ""


def test_judge_list_prints_nothing_for_empty_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        monkeypatch=monkeypatch,
        database=tmp_path / "azathoth.db",
    )

    forbid_runtime(monkeypatch)

    assert list_judges() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
