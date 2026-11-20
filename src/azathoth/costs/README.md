# Costs

`azathoth.costs` says how a model call's cost is known (ADR 0132).

```python
from azathoth.costs import CostBasis, cost_basis_of
```

A call's `cost_basis` is `billed` when its provider reported what it
charged, as OpenRouter does, and `estimated` when Azathoth computed it from
a price its operator configured, as Bedrock's is. A call with no cost has
no basis: unknown is never free.

A cost recorded before 1.5 names no basis. `cost_basis_of` reads it from
the call's provider: OpenRouter's costs were billed, every other
provider's estimated.
