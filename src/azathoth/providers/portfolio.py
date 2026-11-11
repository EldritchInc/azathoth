"""Organizational authorization of models available to Azathoth."""

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.sensitivity import UNKNOWN_DATA_POLICY, DataPolicy


class ModelPortfolioEntry(BaseModel):
    """Authorize one provider model for general Azathoth selection.

    `data_policy` is what whoever authorized the model declared its provider
    does with data it is sent (ADR 0123). Azathoth never assumes a
    provider's terms, so it is unknown until declared, and an entry whose
    policy is unknown serializes without it: no existing entry's digest
    changes.
    """

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)

    model: str = Field(min_length=1)

    data_policy: DataPolicy = UNKNOWN_DATA_POLICY

    @model_serializer(mode="wrap")
    def omit_unknown_data_policy(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Leave out `data_policy` while neither of its answers is declared."""

        serialized: dict[str, Any] = handler(self)

        if self.data_policy.unknown:
            serialized.pop("data_policy", None)

        return serialized

    @property
    def identifier(
        self,
    ) -> str:
        """Return the provider-qualified model identifier."""

        return f"{self.provider}/{self.model}"


class ModelPortfolio(BaseModel):
    """Describe the ordered models authorized for Azathoth selection."""

    model_config = ConfigDict(frozen=True)

    entries: tuple[
        ModelPortfolioEntry,
        ...,
    ] = ()

    @model_validator(mode="after")
    def reject_duplicate_identifiers(
        self,
    ) -> "ModelPortfolio":
        """Reject duplicate provider-qualified model identities."""

        identifiers = tuple(entry.identifier for entry in self.entries)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Model portfolio cannot contain duplicate model identifiers.")

        return self

    @property
    def identifiers(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        """Return authorized model identifiers in portfolio order."""

        return tuple(entry.identifier for entry in self.entries)

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one authorized model by provider-qualified identifier."""

        return next(
            (entry for entry in self.entries if entry.identifier == identifier),
            None,
        )
