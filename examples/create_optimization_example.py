"""Create and serialize a minimal Azathoth optimization example."""

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import ExpectedOutcome, OutcomeComparison
from azathoth.goals import Goal
from azathoth.optimization import OptimizationExample


def main() -> None:
    """Build and print an optimization example."""

    goal = Goal(
        name="Classify customer support requests",
        description="Identify the correct support category for each request.",
        success_criteria=("The predicted category matches the expected category.",),
        constraints=("Do not include private customer information in the result.",),
    )

    context = Context().append(
        ContextEvent(
            event_type="customer.message.received",
            payload={
                "message": "I was charged twice for the same purchase.",
            },
            producer="example",
            provenance="synthetic-demo",
        )
    )

    expected_outcome = ExpectedOutcome(
        description="The request is classified as a duplicate charge.",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    )

    example = OptimizationExample(
        name="Duplicate billing charge",
        goal=goal,
        context=context,
        expected_outcome=expected_outcome,
        tags=("billing", "classification"),
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
