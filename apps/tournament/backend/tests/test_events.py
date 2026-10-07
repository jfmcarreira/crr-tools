import asyncio

from app.events import StateChangeEvents


def test_notification_only_sse_retry_heartbeat_broadcast_and_cleanup():
    async def scenario():
        broker = StateChangeEvents(heartbeat_seconds=0.02)
        stream = broker.stream()
        assert await anext(stream) == "retry: 3000\n\n"
        broker.broadcast()
        assert await anext(stream) == 'event: state-changed\ndata: {"type":"state-changed"}\n\n'
        assert await anext(stream) == ": heartbeat\n\n"
        await stream.aclose()
        assert not broker.clients
    asyncio.run(scenario())
