"""What a model's provider does with data, and which labels it may receive (ADR 0123)."""

from enum import StrEnum
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
)

from azathoth.sensitivity.labels import Sensitivity


class PolicyAnswer(StrEnum):
    """One answer of a data policy: yes, no, or not declared."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class DataPolicy(BaseModel):
    """Whether a model's provider retains the data it is sent, and whether it trains on it.

    Whoever authorizes the model declares it. Azathoth never assumes a
    provider's terms, so both answers are unknown until declared.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    retains_data: PolicyAnswer = PolicyAnswer.UNKNOWN

    trains_on_data: PolicyAnswer = PolicyAnswer.UNKNOWN

    @property
    def private(
        self,
    ) -> bool:
        """Return whether the provider is declared to neither retain nor train on data."""

        return self.retains_data is PolicyAnswer.NO and self.trains_on_data is PolicyAnswer.NO

    @property
    def unknown(
        self,
    ) -> bool:
        """Return whether neither answer is declared."""

        return (
            self.retains_data is PolicyAnswer.UNKNOWN
            and self.trains_on_data is PolicyAnswer.UNKNOWN
        )


UNKNOWN_DATA_POLICY: Final = DataPolicy()
"""The policy of a model whose provider's handling of data is not declared."""

PRIVATE_DATA_POLICY: Final = DataPolicy(
    retains_data=PolicyAnswer.NO,
    trains_on_data=PolicyAnswer.NO,
)
"""The policy of a model whose provider neither retains nor trains on data."""

RESTRICTED_REFUSAL_HINT: Final = (
    "If its provider neither retains nor trains on data, declare that with "
    "`azathoth model policy {model} --no-retention --no-training`; "
    "otherwise choose a model that may receive restricted input."
)
"""What to do about a refusal, with the model's identifier as `{model}`."""


def may_receive(
    policy: DataPolicy | None,
    label: Sensitivity | None,
) -> bool:
    """Return whether a model with this policy may be sent data with this label.

    Public and internal data, and data that names no label and so is
    internal, may be sent to any model. Restricted data may
    be sent only to a model declared private: its provider neither retains
    nor trains on data. A model outside the portfolio has no policy, so it
    may not.
    """

    if label is not Sensitivity.RESTRICTED:
        return True

    return policy is not None and policy.private


def restricted_refusal(
    model: str,
    policy: DataPolicy | None,
) -> str:
    """Return why a model may not receive restricted data, naming each answer that forbids it.

    Raises:
        ValueError: The model may receive restricted data.
    """

    if policy is None:
        return f"{model} cannot receive restricted input: it is not in the portfolio."

    if policy.private:
        raise ValueError(f"{model} may receive restricted input.")

    reasons: list[str] = []

    for answer, practice in (
        (policy.retains_data, "retains data"),
        (policy.trains_on_data, "trains on data"),
    ):
        subject = "it" if reasons else "its provider"

        if answer is PolicyAnswer.YES:
            reasons.append(f"says {subject} {practice}")
        elif answer is PolicyAnswer.UNKNOWN:
            reasons.append(f"does not say whether {subject} {practice}")

    return f"{model} cannot receive restricted input: its portfolio entry {', and '.join(reasons)}."


__all__ = [
    "PRIVATE_DATA_POLICY",
    "RESTRICTED_REFUSAL_HINT",
    "UNKNOWN_DATA_POLICY",
    "DataPolicy",
    "PolicyAnswer",
    "may_receive",
    "restricted_refusal",
]
