"""Model-selection authority for prompt-backed specifications."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.providers import ModelRequirements


class PortfolioModelSelection(BaseModel):
    """Allow Azathoth to select a model satisfying declared requirements."""

    model_config = ConfigDict(frozen=True)

    requirements: ModelRequirements


class FixedModelSelection(BaseModel):
    """Require one exact provider-qualified model."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    @property
    def identifier(
        self,
    ) -> str:
        """Return the required provider-qualified model identifier."""

        return f"{self.provider}/{self.model}"


ModelSelection = PortfolioModelSelection | FixedModelSelection
