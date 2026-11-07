"""Model-independent specifications for prompt-backed strategies."""

from typing import Any, Final, Self, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.prompting.citations import CitationPolicy
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

    @model_validator(mode="after")
    def refuse_fixed_content(
        self,
    ) -> Self:
        """Refuse a fixed prompt that shows content (ADR 0115).

        Content reaches a prompt through a template variable bound to a
        handle the run received; a handle written into a workflow document
        would name content no run was ever given.

        Raises:
            ValueError: The fixed prompt holds content parts.
        """

        if self.prompt.parts:
            raise ValueError(
                f"Prompt strategy {self.metadata.name!r} shows content in a fixed prompt; "
                "content reaches a prompt only through a template variable bound to a "
                "content handle."
            )

        return self

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

    `citations` makes the step a cited one (ADR 0116): every citation its
    JSON reply holds is checked against the extraction it names, replaced by
    its check, and kept. A specification without it serializes without it.
    """

    model_config = ConfigDict(frozen=True)

    metadata: StrategyMetadata
    template: PromptTemplate
    model_selection: ModelSelection
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT
    citations: CitationPolicy | None = None

    @model_validator(mode="after")
    def require_json_for_citations(
        self,
    ) -> Self:
        """Require a JSON reply of a cited step, and a text reply of a natively cited one.

        Raises:
            ValueError: The step checks its reply's citations, but its output
                is text, or its provider's, but its output is JSON.
        """

        if self.citations is None:
            return self

        if self.citations.native and self.output_format is not PromptOutputFormat.TEXT:
            raise ValueError(
                f"Prompt strategy {self.metadata.name!r} checks native citations, which its "
                "model returns beside a text reply; its output format is json."
            )

        if not self.citations.native and self.output_format is not PromptOutputFormat.JSON:
            raise ValueError(
                f"Prompt strategy {self.metadata.name!r} checks citations, which only a JSON "
                "reply holds; its output format is text."
            )

        return self

    @model_serializer(mode="wrap")
    def serialize_without_text_output_format(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the specification, omitting the default text output format and no policy."""

        serialized = _without_text_output_format(handler(self))

        if serialized.get("citations") is None:
            serialized.pop("citations", None)

        return serialized


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
