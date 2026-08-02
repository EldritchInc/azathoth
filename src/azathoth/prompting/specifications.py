"""Model-independent specifications for prompt-backed strategies."""

from pydantic import BaseModel, ConfigDict

from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata


class PromptStrategySpec(BaseModel):
    """Describe a prompt strategy without binding it to a language model."""

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    prompt: Prompt
    model_requirements: ModelRequirements