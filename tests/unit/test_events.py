from __future__ import annotations

import asyncio

from jarvis.events import EventBus, EventEnvelope


def test_publish_from_thread_reaches_subscriber() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        bus.bind_loop(asyncio.get_running_loop())
        sub = bus.subscribe()
        await asyncio.to_thread(bus.publish, EventEnvelope(type="t.one", payload={"a": 1}))
        got = await sub.next(1.0)
        assert got is not None
        return [got.type]

    assert asyncio.run(scenario()) == ["t.one"]


def test_slow_subscriber_is_disconnected_not_silently_lossy() -> None:
    async def scenario() -> bool:
        bus = EventBus(queue_size=2)
        bus.bind_loop(asyncio.get_running_loop())
        sub = bus.subscribe()
        for i in range(3):
            bus.publish(EventEnvelope(type=f"t.{i}"))
        await asyncio.sleep(0.05)
        return sub.overflowed

    assert asyncio.run(scenario()) is True


def test_envelope_shape() -> None:
    env = EventEnvelope(type="x").model_dump()
    assert set(env) == {"type", "id", "ts", "task_id", "schema_version", "payload"}
