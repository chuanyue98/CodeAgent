from __future__ import annotations

import asyncio

import pytest

from core.services.log_broker import LogBroker


@pytest.mark.asyncio
async def test_notify_wakes_a_subscriber():
    broker = LogBroker()
    broker.register("run-1")
    subscription = broker.subscribe("run-1")

    subscription.arm()
    broker.notify("run-1")

    assert await subscription.wait(timeout=1) is True


@pytest.mark.asyncio
async def test_wait_times_out_when_nothing_is_written():
    broker = LogBroker()
    subscription = broker.subscribe("run-1")

    subscription.arm()

    assert await subscription.wait(timeout=0.05) is False


@pytest.mark.asyncio
async def test_arm_discards_a_wakeup_from_before_the_read():
    """A consumer reads the file between arm() and wait().

    That read already accounts for anything written before it, so a wake-up
    raised in that window must not end the wait -- otherwise the stream spins
    on a chunk it has already sent.
    """
    broker = LogBroker()
    subscription = broker.subscribe("run-1")

    broker.notify("run-1")
    await asyncio.sleep(0)  # let call_soon_threadsafe deliver the wake-up
    subscription.arm()

    assert await subscription.wait(timeout=0.05) is False


@pytest.mark.asyncio
async def test_finish_wakes_subscribers_and_drops_the_live_marker():
    broker = LogBroker()
    broker.register("run-1")
    subscription = broker.subscribe("run-1")

    subscription.arm()
    broker.finish("run-1")

    assert await subscription.wait(timeout=1) is True
    assert broker.is_live("run-1") is False


@pytest.mark.asyncio
async def test_notifying_a_run_nobody_watches_is_a_no_op():
    broker = LogBroker()

    broker.notify("run-1")
    broker.finish("run-1")

    assert broker.is_live("run-1") is False


@pytest.mark.asyncio
async def test_release_forgets_the_subscription():
    broker = LogBroker()
    subscription = broker.subscribe("run-1")

    subscription.release()
    subscription.release()  # idempotent

    assert broker._watchers("run-1") == []


@pytest.mark.asyncio
async def test_subscribers_are_independent():
    """Two tabs watching one run both get woken by the same write."""
    broker = LogBroker()
    broker.register("run-1")
    first = broker.subscribe("run-1")
    second = broker.subscribe("run-1")

    first.arm()
    second.arm()
    broker.notify("run-1")

    assert await first.wait(timeout=1) is True
    assert await second.wait(timeout=1) is True

    first.release()
    second.arm()
    broker.notify("run-1")

    assert await second.wait(timeout=1) is True
