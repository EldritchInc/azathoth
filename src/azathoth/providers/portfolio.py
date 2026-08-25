"""Organizational authorization of models available to Azathoth."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class ModelPortfolioEntry(BaseModel):
    """Authorize one provider model for general Azathoth selection."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)

    model: str = Field(min_length=1)

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
