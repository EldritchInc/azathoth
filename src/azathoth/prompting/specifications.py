"""Model-independent specifications for prompt-backed strategies."""

from pydantic import BaseModel, ConfigDict

from azathoth.prompting.model_selection import ModelSelection
from azathoth.prompting.models import PromptTemplate
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata


class PromptStrategySpec(BaseModel):
    """Describe a fixed-prompt strategy without binding it to a language model."""

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    prompt: Prompt
    model_selection: ModelSelection


class ContextPromptStrategySpec(BaseModel):
    """Describe a context-rendered strategy without binding it to a model."""

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    template: PromptTemplate
    model_selection: ModelSelection
