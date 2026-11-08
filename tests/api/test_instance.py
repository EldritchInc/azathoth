"""Contract tests for opening, describing and closing an Azathoth instance (ADR 0120)."""

import inspect
import sqlite3
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

import azathoth
from azathoth import api
from azathoth.persistence import (
    MISSING_DRIVER_MESSAGE,
    SCHEMA_VERSION,
    DatabaseUnavailableError,
)
from azathoth.persistence.postgres import PostgresDriver


def test_an_instance_describes_itself(
    instance: api.Azathoth,
    location: str,
) -> None:
    description = instance.describe()

    backend = "postgres" if location.startswith("postgresql://") else "sqlite"

    assert description.backend == backend
    assert description.azathoth_version == azathoth.__version__
    assert description.schema_version == SCHEMA_VERSION
    assert description.api_stability == api.API_STABILITY

    if backend == "sqlite":
        assert description.database == location


def test_a_postgresql_instance_is_described_without_its_password(
    instance: api.Azathoth,
    location: str,
) -> None:
    if not location.startswith("postgresql://"):
        pytest.skip("Only a PostgreSQL URL carries a password.")

    database = instance.describe().database

    assert database.startswith("postgresql://")
    assert ":azathoth@" not in database


def test_the_api_is_provisional_until_it_is_declared_stable() -> None:
    assert api.API_STABILITY == "provisional"


def test_a_description_is_its_own_json(
    instance: api.Azathoth,
) -> None:
    description = instance.describe()

    assert api.InstanceDescription.model_validate_json(description.model_dump_json()) == description
    assert set(description.model_dump(mode="json")) == {
        "database",
        "backend",
        "azathoth_version",
        "schema_version",
        "api_stability",
    }


def test_an_instance_closes_when_its_block_ends(
    location: str,
) -> None:
    with api.open(location) as opened:
        assert not opened.closed

    assert opened.closed


def test_an_instance_closes_when_its_block_raises(
    location: str,
) -> None:
    with pytest.raises(RuntimeError, match="^inside$"), api.open(location) as opened:
        raise RuntimeError("inside")

    assert opened.closed


def test_a_closed_instance_refuses_every_call(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError, match=r"^This Azathoth instance is closed\.$"):
        opened.describe()


def test_closing_twice_is_harmless(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()
    opened.close()

    assert opened.closed


def test_a_missing_sqlite_file_is_refused_and_not_created(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "azathoth.db"

    with pytest.raises(api.InstanceNotFoundError) as raised:
        api.open(path)

    assert str(raised.value) == f"Database {path} does not exist; run azathoth init."
    assert not path.exists()
    assert not path.parent.exists()


def test_an_existing_sqlite_file_opens_by_path_as_well_as_by_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    sqlite3.connect(path).close()

    with api.open(path) as opened:
        assert opened.describe().database == str(path)


def test_postgresql_without_its_driver_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_driver() -> PostgresDriver:
        raise DatabaseUnavailableError()

    monkeypatch.setattr("azathoth.persistence.postgres.psycopg_driver", no_driver)

    url = f"postgresql://azathoth@127.0.0.1:1/{uuid.uuid4().hex}"

    with pytest.raises(api.InstanceUnavailableError) as raised:
        api.open(url)

    assert str(raised.value) == MISSING_DRIVER_MESSAGE
    assert isinstance(raised.value.__cause__, DatabaseUnavailableError)


def test_an_uninitialized_postgresql_database_is_refused(
    empty_postgres_url: str,
) -> None:
    with pytest.raises(api.InstanceSchemaError, match=r"is not initialized; run azathoth init\.$"):
        api.open(empty_postgres_url)


def test_every_error_carries_a_distinct_code() -> None:
    errors = tuple(
        public
        for name in api.__all__
        if isinstance(public := getattr(api, name), type) and issubclass(public, api.ApiError)
    )

    assert {error.__name__: error.code for error in errors} == {
        "ApiError": "error",
        "ConflictError": "conflict",
        "InstanceClosedError": "instance_closed",
        "InstanceNotFoundError": "instance_not_found",
        "InstanceSchemaError": "instance_schema",
        "InstanceUnavailableError": "instance_unavailable",
        "InvalidArgumentError": "invalid_argument",
        "ModelInUseError": "model_in_use",
        "NotFoundError": "not_found",
        "ProviderConfigurationError": "provider_configuration",
        "ProviderUnavailableError": "provider_unavailable",
        "RevisionNotFoundError": "revision_not_found",
    }
    assert len({error.code for error in errors}) == len(errors)


def test_an_errors_code_is_part_of_the_instance_too() -> None:
    assert api.InstanceClosedError().code == "instance_closed"


def test_api_models_are_frozen_and_refuse_unknown_fields() -> None:
    description = api.InstanceDescription(
        database="azathoth.db",
        backend="sqlite",
        azathoth_version="1.3.0",
        schema_version=2,
        api_stability="provisional",
    )

    field = "database"

    with pytest.raises(ValidationError):
        setattr(description, field, "other.db")

    with pytest.raises(ValidationError):
        api.InstanceDescription.model_validate(
            {**description.model_dump(), "extra": "field"},
        )


def test_every_public_name_is_documented() -> None:
    undocumented = tuple(
        name
        for name in api.__all__
        if (isinstance(public := getattr(api, name), type) or inspect.isfunction(public))
        and not (public.__doc__ or "").strip()
    )

    assert undocumented == ()
