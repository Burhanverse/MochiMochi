"""Tests for executor pool lifecycle and mid-flight rebuilding."""

import asyncio
import time

import pytest

from resources import ResourceManager


def _slow_work(duration: float):
    time.sleep(duration)
    return "done"


@pytest.mark.asyncio
async def test_cpu_pool_mid_flight_rebuild():
    rm = ResourceManager()
    loop = asyncio.get_running_loop()

    # Submit slow work to current CPU pool
    future = loop.run_in_executor(rm.get_cpu_pool(), _slow_work, 0.2)

    # Rebuild pool mid-flight
    rm.rebuild_cpu_pool(4)

    # Assert old job still completes cleanly without error
    result = await future
    assert result == "done"

    await rm.shutdown()
