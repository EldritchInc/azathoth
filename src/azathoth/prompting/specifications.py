"""Model-independent specifications for prompt-backed strategies."""

from typing import Any, Final, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from azathoth.prompting.model_selection import ModelSelection
from azathoth.prompting.models import PromptTemplate
from azathoth.prompting.output_format import PromptOutputFormat
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata


def _without_text_output_format(
    serialized: dict[str, Any],
) -> dict[str, Any]:
    """Drop the default text output format, so existing documents keep their digests."""

    if serialized.get("output_format") == PromptOutputFormat.TEXT:
        serialized.pop("output_format", None)

    return serialized


class PromptStrategySpec(BaseModel):
    """Describe a fixed-prompt strategy without binding it to a language model.

    The output format defaults to text. A specification with text output
    serializes without it, so its documents and content digests are unchanged.
    """

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    prompt: Prompt
    model_selection: ModelSelection
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT

    @model_serializer(mode="wrap")
    def serialize_without_text_output_format(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the specification, omitting the default text output format."""

        return _without_text_output_format(handler(self))


class ContextPromptStrategySpec(BaseModel):
    """Describe a context-rendered strategy without binding it to a model.

    The output format defaults to text. A specification with text output
    serializes without it, so its documents and content digests are unchanged.
    """

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    template: PromptTemplate
    model_selection: ModelSelection
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT

    @model_serializer(mode="wrap")
    def serialize_without_text_output_format(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the specification, omitting the default text output format."""

        return _without_text_output_format(handler(self))


PromptSpecification: TypeAlias = PromptStrategySpec | ContextPromptStrategySpec
"""Any prompt-backed step specification, for annotations.

Keep it in step with `PROMPT_SPECIFICATIONS`; a test holds them equal.
"""

PROMPT_SPECIFICATIONS: Final = (
    PromptStrategySpec,
    ContextPromptStrategySpec,
)
"""Every prompt-backed step specification kind, for `isinstance` checks.

Ask "is this step prompt-backed?" with
`isinstance(specification, PROMPT_SPECIFICATIONS)`, never with a hand-written
tuple, so a new prompt kind cannot be missed. mypy narrows both branches of
the check.
"""
