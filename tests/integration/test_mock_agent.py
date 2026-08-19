import asyncio
from pathlib import Path

import pytest

from proxy.config import load_config
from proxy.server import Proxy

TEST_CONFIG_PATH = Path(__file__).parent.parent / "configs" / "test_config.yaml"

@pytest.fixture
def proxy(tmp_path, monkeypatch):
    config = load_config(TEST_CONFIG_PATH)
    config.proxy.log_path = str(tmp_path / "calls.jsonl")
    monkeypatch.chdir(Path(__file__).parent.parent.parent)
    return Proxy(config)

@pytest.mark.asyncio
async def test_success_call_returns_data(proxy):
    result = await proxy.call("test_tool", {"mode": "success"}, calling_agent="pytest")
    assert result == {"status": "ok", "value": 42}

    records = proxy.logger.load()
    assert records[-1]["outcome"] == "success"

@pytest.mark.asyncio
async def test_malformed_response_retries_then_fails(proxy):
    with pytest.raises(RuntimeError):
        await proxy.call("test_tool", {"mode": "malformed"}, calling_agent="pytest")

    records = proxy.logger.load()
    outcomes = [r["outcome"] for r in records]

    assert outcomes.count("schema_mismatch") == 1
    assert all(r["tool"] == "test_tool" for r in records)

@pytest.mark.asyncio
async def test_slow_response_time_out_and_retries(proxy):
    with pytest.raises(RuntimeError):
        await proxy.call("test_tool", {"mode": "slow"}, calling_agent="pytest")

    records = proxy.logger.load()
    outcomes = [r["outcome"] for r in records]

    assert outcomes.count("timeout") == 2

@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_threshold_and_blocks_further_calls(proxy):
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await proxy.call("test_tool", {"mode": "error"}, calling_agent="pytest")

    with pytest.raises(RuntimeError, match="Circuit open"):
        await proxy.call("test_tool", {"mode": "error"}, calling_agent="pytest")

    records = proxy.logger.load()
    assert any(r["outcome"] == "circuit_open" for r in records)

@pytest.mark.asyncio
async def test_circuit_breaker_recovers_after_cooldown(proxy):
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await proxy.call("test_tool", {"mode": "error"}, calling_agent="pytest")
    
    assert proxy.fallback.circuit_is_open("mock-agent", "test_tool")

    await asyncio.sleep(5.2)

    result = await proxy.call("test_tool", {"mode": "success"}, calling_agent="pytest")
    assert result == {"status": "ok", "value": 42}

