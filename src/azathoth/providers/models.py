"""Language model request and response models."""

from pydantic import BaseModel, ConfigDict


class Prompt(BaseModel):
    """A rendered prompt sent to a language model."""

    model_config = ConfigDict(frozen=True)

    text: str


class ModelResponse(BaseModel):
    """The response returned by a language model."""

    model_config = ConfigDict(frozen=True)

    text: str
