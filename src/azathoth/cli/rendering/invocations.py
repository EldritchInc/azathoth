"""Human-readable production invocation rendering."""

from azathoth.cli.rendering._json import render_json_value
from azathoth.workflows import (
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
)


def render_production_invocation_result(
    result: ProductionInvocationResult,
) -> str:
    """Render one caller-visible production invocation result."""

    if isinstance(
        result,
        ProductionInvocationSuccess,
    ):
        return "\n".join(
            (
                f"Invocation ID: {result.invocation_id}",
                "Status: succeeded",
                "Result:",
                render_json_value(result.result),
            )
        )

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    lines = [
        f"Invocation ID: {result.invocation_id}",
        "Status: failed",
        f"Error: {result.error_code.value}",
        f"Message: {result.message}",
    ]

    if result.metadata:
        lines.extend(
            (
                "Metadata:",
                render_json_value(result.metadata),
            )
        )

    return "\n".join(lines)
