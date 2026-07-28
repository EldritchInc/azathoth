"""Execute a deterministic Azathoth strategy and print its trace."""

import asyncio

from azathoth.context import Context, ContextEvent
from azathoth.execution import StrategyExecutor
from azathoth.strategies import EventFieldStrategy, StrategyMetadata


async def main() -> None:
    """Execute a strategy against structured context."""

    context = Context().append(
        ContextEvent(
            event_type="customer.message.received",
            payload={
                "message": "I was charged twice for the same purchase.",
            },
            producer="example",
            provenance="synthetic-support-case",
            confidence=1.0,
        )
    )

    strategy = EventFieldStrategy(
        metadata=StrategyMetadata(
            name="Extract customer message",
            description="Extract the latest customer support message.",
            version="1.0.0",
        ),
        event_type="customer.message.received",
        field_name="message",
        output_event_type="customer.message.extracted",
    )

    result = await StrategyExecutor().execute(strategy, context)

    print("Output:")
    print(result.output)

    print("\nExecution trace:")

    for event in result.final_context.events:
        print(f"- {event.occurred_at.isoformat()}  {event.event_type}")


if __name__ == "__main__":
    asyncio.run(main())
