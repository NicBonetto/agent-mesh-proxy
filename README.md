# agent-mesh-proxy (v0)

A verification / fallback / performance-measurement proxy for agent-to-agent
(and agent-to-tool) calls over MCP. It sits between a calling agent and one
or more downstream MCP servers, and for every tool call it:

1. **Checks the circuit breaker** before attempting anything, so a known-bad
   downstream pairing fails fast instead of hanging every caller
2. **Makes the call**, timed, over whatever transport the downstream server
   is configured for (`streamable_http` / `sse` / `stdio`)
3. **Validates the response structurally** against a per-tool JSON schema
4. **Applies fallback policy** on timeout / schema mismatch / error — retry
   with backoff, circuit-break, or route to an alternate downstream server
5. **Logs every attempt** (JSONL). Outcome, latency,
   token usage, whether it was part of a multi-hop session
6. **Ties related calls together** into a session, if the caller says a call
   belongs to one, so a multi-agent delegation chain can eventually be
   scored as a single task instead of N disconnected calls

**Current limitation:** `Proxy.call()` (`server.py`) is the client-side path
only (proxy to downstream agent). There is no MCP server exposed by this
proxy for an upstream calling agent to connect to yet. That's a TODO task
not implemented yet. For now, use this as a library from your agent front-end,
not as a standalone service something else connects to.

## Install & quickstart (uv)

```bash
uv sync
cp config.example.yaml config.yaml   # edit with your downstream server details
```

```bash
# Validate config loads correctly
uv run agent-mesh-proxy config-check --config config.yaml

# Make an ad-hoc call through the proxy
uv run agent-mesh-proxy call <tool_name> --arg key=value \
    --intent "what you're trying to accomplish" --config config.yaml

# Tie a chain of calls to one higher-level goal
uv run agent-mesh-proxy session-start "reprice the west region for Q4" --config config.yaml
uv run agent-mesh-proxy call <tool_name> --session <session_id> --intent "..." --config config.yaml
uv run agent-mesh-proxy session-close <session_id> --outcome success --config config.yaml

# Performance / verification stats from the call log
uv run agent-mesh-proxy score --tool <tool_name> --config config.yaml

# Equivalent dev entrypoint without the installed console script:
uv run main.py config-check --config config.yaml
```

As a library, from your agent front-end:

```python
from proxy.config import load_config
from proxy.server import Proxy

config = load_config("config.yaml")
proxy = Proxy(config)

result = await proxy.call(
    "solve_markdown_schedule",
    {"store_id": 42},
    calling_agent="pricing-agent",
    intent="get a markdown schedule that maximizes SKU-level margin",
)
```

## How verification actually works

Two layers, run in order, with different guarantees:

| Layer | Question it answers | Runs when | Code |
|---|---|---|---|
| Circuit breaker | "Has this pairing failed too much to bother trying?" | Before every call | `fallback.py` |
| Structural | "Is the response shaped correctly?" | Every successful call | `validator.py` |
| Session | "Which calls belong to the same higher-level task?" | Only if `session_id` given | `session.py` |

Walking through `Proxy.call()` for a single call:

**1. Route to the right downstream server** (`server.py: _server_for_tool`)
Looks up which configured downstream agent exposes the requested tool.

**2. Circuit breaker check** (`server.py`, calling into `fallback.py`)
If this `(server, tool)` pairing has failed past its configured threshold
recently, fail fast without attempting the call at all.

**3. Make the call** (`mcp_client.py`)
The actual request to the downstream agent, over its configured transport,
with a timeout.

**4. Structural validation** (`validator.py`)
```python
validation = validate_response(result.data, tool_config.response_schema)
```
Checks the response against a JSON Schema you configured per tool —
required fields, types. Answers "does this look like a valid response," not
"is this a *good* response." A downstream agent can return technically
valid but useless data and this layer will say `ok=True`.

**5. Logging** (`logger.py`)
Every attempt - `success`, `timeout`, `schema_mismatch`, `error`, `circuit_open` -
becomes one `CallRecord`. This is what makes it possible to later ask "what 
fraction of structurally-valid responses actually satisfied intent" via `logger.score()`.

**6. Session linkage** (`session.py`)
If the call carried a `session_id`, its `call_id` gets appended to that
session's `call_ids` list. This is the mechanism for eventually asking "did this
whole multi-agent delegation chain accomplish what was needed," not just
"did each individual call succeed."

## Roadmap after v0

- Develop semantic verification (LLM-as-a-judge)
- Session-level (task) outcome judging — right now `session-close --outcome`
  is manually specified, not derived from the actual call chain
- A queryable delegation tree from `parent_call_id`, not just raw links
- Expose the proxy itself as an MCP server for upstream agents to connect to
- Multi-agent fallback routing (not just retry same agent)
- Dashboard (Streamlit or simple React) reading from the JSONL log / a DB
- Move JSONL → Postgres/BigQuery
- Non-MCP transport (plain HTTP/REST or A2A) so non-MCP agents can go through
  the same proxy — validates that validator/fallback/logger are genuinely
  transport-agnostic, not MCP-coupled

