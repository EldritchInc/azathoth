"""How a model call's cost is known (ADR 0132).

A provider that reports what it charged gives a `billed` cost; one priced by
Azathoth from a price its operator configured gives an `estimated` one. A
call with no cost has no basis: unknown is never free, and never billed.
"""

from typing import Final, Literal, get_args

CostBasis = Literal["billed", "estimated"]
"""How one call's cost is known."""

COST_BASES: Final[tuple[CostBasis, ...]] = get_args(CostBasis)
"""Every basis a cost can have, billed first."""

BILLING_PROVIDERS: Final = frozenset({"openrouter"})
"""The providers whose recorded costs are what they charged.

A cost recorded before 1.5 names no basis, so it is read from its provider:
OpenRouter's was its `usage.cost`, a bill; any other provider's was priced
by Azathoth, an estimate.
"""


def cost_basis_of(
    provider: str | None,
    cost_usd: float | None,
    basis: CostBasis | None,
) -> CostBasis | None:
    """Return how one call's cost is known, from its own basis or its provider.

    A cost with no basis was recorded before 1.5, and is billed when its
    provider bills and estimated otherwise. A call with no cost, or no
    provider to tell it by, has none.
    """

    if cost_usd is None:
        return None
    if basis is not None:
        return basis
    if provider is None:
        return None

    return "billed" if provider in BILLING_PROVIDERS else "estimated"


def require_cost_for_basis(
    cost_usd: float | None,
    basis: CostBasis | None,
) -> None:
    """Refuse a basis for a call with no cost.

    Raises:
        ValueError: A basis is given, but no cost.
    """

    if basis is not None and cost_usd is None:
        raise ValueError("A call with no cost has no cost basis.")


__all__ = [
    "BILLING_PROVIDERS",
    "COST_BASES",
    "CostBasis",
    "cost_basis_of",
    "require_cost_for_basis",
]
