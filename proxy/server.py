import asyncio
import uuid

from .config import Config, DownstreamServer, load_config
from .fallback import FallbackEngine
from .logger import CallLogger, CallRecord, now_ms
from .mcp_client import DownstreamError, DownstreamTimeout, call_tool
from .validator import validate_response
from .session import SessionStore

class Proxy:
    def __init__(self, config: Config, session_store: SessionStore | None = None):
        self.config = config
        self.logger = CallLogger(config.proxy.log_path)
        self.fallback = FallbackEngine()
        self.sessions = session_store or SessionStore(
            str(config.proxy.log_path).rsplit(".", 1)[0] + ".sessions.jsonl"
        )

    def _server_for_tool(self, tool_name: str) -> DownstreamServer:
        for server in self.config.downstream_servers:
            if server.tool(tool_name) is not None:
                return server
            raise KeyError(f"No downstream server exposes tool {tool_name!r}")

    async def call(
        self,
        tool_name: str,
        arguments: dict,
        calling_agent: str | None = None,
        intent: str | None = None,
        session_id: str | None = None,
        parent_call_id: str | None = None
    ) -> dict:
        server = self._server_for_tool(tool_name)
        rules = self.config.policy_for(tool_name)
        attempt = 1
        last_outcome = "error"
        last_error: str | None = None

        while True:
            call_id = str(uuid.uuid4())

            if self.fallback.circuit_is_open(server.id, tool_name):
                self._log(
                    call_id,
                    tool_name,
                    server.id,
                    calling_agent,
                    0.0,
                    attempt,
                    "circuit_open",
                    intent,
                    session_id,
                    parent_call_id,
                    fallback_action="circuit_open"
                )
                open_rule = self.fallback.rule_for_outcome(rules, "circuit_open")
                if open_rule and open_rule.action == "route_to" and open_rule.target:
                    server = self.config.server(open_rule.target)
                    continue
                raise RuntimeError(f"Circuit open for {server.id}:{tool_name}, no fallback configured")

            start = now_ms()
            try:
                result = await call_tool(server, tool_name, arguments)
                validation = validate_response(
                    result.data,
                    (server.tool(tool_name) or _empty_tool()).response_schema
                )
                if validation.ok:
                    self._log(
                        call_id,
                        tool_name,
                        server.id,
                        calling_agent,
                        result.latency_ms,
                        attempt,
                        "success",
                        intent,
                        session_id,
                        parent_call_id,
                        downstream_tokens=_extract_downstream_tokens(result.data)
                    )
                    if session_id:
                        self.sessions.append_call(session_id, call_id)
                    return result.data

                last_outcome = "schema_mismatch"
                last_error = "; ".join(validation.errors)

            except DownstreamTimeout as e:
                last_outcome, last_error = "timeout", str(e)
            except DownstreamError as e:
                last_outcome, last_error = "error", str(e)

            latency_ms = now_ms() - start
            rule = self.fallback.rule_for_outcome(rules, last_outcome)
            action = rule.action if rule else "fail_fast"

            self._log(
                call_id,
                tool_name,
                server.id,
                calling_agent,
                latency_ms,
                attempt,
                last_outcome,
                intent,
                session_id,
                parent_call_id,
                fallback_action=action,
                error=last_error
            )

            if last_outcome == "error" and rule and rule.action == "circuit_break":
                self.fallback.note_failure(server.id, tool_name, rule)

            if rule and rule.action == "retry" and attempt < rule.max_attempts:
                await asyncio.sleep(self.fallback.backoff_delay(rule, attempt))
                attempt += 1
                continue

            if rule and rule.action == "route_to" and rule.target:
                server = self.config.server(rule.target)
                attempt += 1
                continue

            raise RuntimeError(f"Call to {tool_name} on {server.id} failed ({last_outcome}): {last_error}")

    def _log(self, call_id, tool, server_id, calling_agent, latency_ms, attempt, outcome,
             intent, session_id, parent_call_id, fallback_action=None, error=None,
             downstream_tokens=None):
        record = CallRecord(
            call_id=call_id,
            timestamp=now_ms(),
            tool=tool,
            downstream_server_id=server_id,
            calling_agent=calling_agent,
            latency_ms=latency_ms,
            attempt=attempt,
            outcome=outcome,
            fallback_action=fallback_action,
            error=error,
            intent=intent,
            session_id=session_id,
            parent_call_id=parent_call_id
        )

        if downstream_tokens is not None:
            record.downstream_input_tokens = downstream_tokens[0]
            record.downstream_output_tokens = downstream_tokens[1]
        self.logger.record(record)

def _extract_downstream_tokens(response_data) -> tuple[int | None, int | None] | None:
    if not isinstance(response_data, dict):
        return None
    usage = response_data.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens, output_tokens)

def _empty_tool():
    from .config import ToolConfig
    return ToolConfig(name="", response_schema={})
