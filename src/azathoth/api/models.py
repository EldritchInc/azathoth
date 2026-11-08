"""The values the service API returns (ADR 0120).

The API returns its own models, never Azathoth's internal ones, so the
engine can change beneath it while what callers read stays put. Every model
is frozen, refuses unknown fields, and is its own JSON: a local UI server
sends `model_dump(mode="json")` as it is.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

ApiStability = Literal["provisional", "stable"]
"""Whether the API is still provisional, or covered by the 1.x promise."""

API_STABILITY: Final[ApiStability] = "provisional"
"""The API's stability in this Azathoth: provisional until 1.4.0 final."""

Backend = Literal["sqlite", "postgres"]
"""The kind of database an instance keeps its state in."""


class ApiModel(BaseModel):
    """Base of every value the service API returns: frozen, closed, and its own JSON."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class InstanceDescription(ApiModel):
    """What one open instance is: its database, and the Azathoth serving it."""

    database: str = Field(
        min_length=1,
        description=(
            "The database as messages name it: an SQLite file's path, or a PostgreSQL "
            "URL without its password."
        ),
    )

    backend: Backend

    azathoth_version: str = Field(
        min_length=1,
    )

    schema_version: int = Field(
        ge=1,
        description="The database schema version this Azathoth uses.",
    )

    api_stability: ApiStability


__all__ = [
    "API_STABILITY",
    "ApiModel",
    "ApiStability",
    "Backend",
    "InstanceDescription",
]
