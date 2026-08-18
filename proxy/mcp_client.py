import asyncio
import time 
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import DownstreamServer

class DownstreamTimeout(Exception):
    pass

class DownstreamError(Exception):
    pass

@dataclass
class ToolCallResult:
    data: Any
    latency_ms: float

def _auth_headers(server: DownstreamServer) -> dict[str, str]:
    token = server.auth.resolve_token()
    if token is None:
        return {}
    if server.auth.type == "bearer":
        return {"Authorization": f"Bearer {token}"}
    if server.auth.type == "api_key":
        return {server.auth.header_name: token}
    return {}

@asynccontextmanager
async def _session(server: DownstreamServer) -> AsyncIterator[ClientSession]:
    if server.transport == "streamable_http":
        headers = _auth_headers(server)
        async with streamablehttp_client(server.url, headers=headers) as (
            read, write, _get_session_id
        ):
            async with ClientSession(read, write) as session:
                yield session
    elif server.transport == "sse":
        headers = _auth_headers(server)
        async with sse_client(server.url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                yield session
    elif server.transport == "stdio":
        params = StdioServerParameters(command=server.command, args=server.args)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                yield session
    else:
        raise ValueError(f"Unknown transport {server.transport!r} for server {server.id!r}")

async def call_tool(
    server: DownstreamServer,
    tool_name: str,
    arguments: dict
) -> ToolCallResult:
    start = time.monotonic()

    async def _do_call():
        async with _session(server) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments=arguments)

    try:
        result = await asyncio.wait_for(_do_call(), timeout=server.timeout_seconds)
    except asyncio.TimeoutError as e:
        raise DownstreamTimeout(
            f"{server.id}:{tool_name} exceeded {server.timeout_seconds}s"
        ) from e 
    except Exception as e:
        raise DownstreamError(f"{server.id}:{tool_name} failed: {e}") from e 

    latency_ms = (time.monotonic() - start) * 1000

    if getattr(result, "isError", False):
        raise DownstreamError(f"{server.id}:{tool_name} returned an error result: {result}")

    data = _extract_content(result)
    return ToolCallResult(data=data, latency_ms=latency_ms)

def _extract_content(result: Any) -> Any:
    blocks = getattr(result, "content", None) or []
    texts = [b.text for b in blocks if getattr(b, "type", None) == "text"]
    if not texts:
        return None
    if len(texts) == 1:
        return _maybe_json(texts[0])
    return [_maybe_json(t) for t in texts]

def _maybe_json(text: str) -> Any:
    import json
    try:
        return json.loads(text)
    except (json.JSONDecodError, TypeError):
        return text
