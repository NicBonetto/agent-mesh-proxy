import argparse
import asyncio
import json
import logging

from .config import Config, DownstreamServer, load_config
from .fallback import FallbackEngine
from .logger import CallLogger, CallRecord, now_ms
from .mcp_client import DownstreamError, DownstreamTimeout, call_tool
from .validator import validate_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent-mesh-proxy")

class Proxy:
    def __init__(self, config: Config):
        self.config = config
        self.logger = CallLogger(config.proxy.log_path)
        self.fallback = FallbackEngine()

    def _server_for_tool(self, tool_name: str) -> DownstreamServer:
        for server in self.config.downstream_servers:
            if server.tool(tool_name) is not None:
                return server
            raise KeyError(f"No downstream server exposes tool {tool_name!r}")

    async def call(
        self,
        tool_name: str,
        arguments: dict,
        calling_agent: str | None = None
    ) -> dict:
        server = self._server_for_tool(tool_name)
        rules = self.config.policy_for(tool_name)
        attempt = 1
        last_outcome = "error"
        last_error: str | None = None

        while True:
            if self.fallback.circuit_is_open(server.id, tool_name):
                self._log(
                    tool_name,
                    server.id,
                    calling_agent,
                    0.0,
                    attempt,
                    "circuit_open",
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
                        tool_name,
                        server.id,
                        calling_agent,
                        result.latency_ms,
                        attempt,
                        "success"
                    )
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
                tool_name,
                server.id,
                calling_agent,
                latency_ms,
                attempt,
                last_outcome,
                fallback_action=action,
                error=last_error
            )

            if last_outcome == "error" and rule and rule.action == "circuit_break":
                self.fallback.note_failure(server.id, tool_name, rule)

            if rule and rule.action == "retry" and attempt < rule.max_attempts + 1:
                await asyncio.sleep(self.fallback.backoff_delay(rule, attempt))
                attempt += 1
                continue

            if rule and rule.action == "route_to" and rule.target:
                server = self.config.server(rule.target)
                attempt += 1
                continue

            raise RuntimeError(f"Call to {tool_name} on {server.id} failed ({last_outcome}): {last_error}")

    def _log(self, tool, server_id, calling_agent, latency_ms, attempt, outcome, fallback_action=None, error=None):
        self.logger.record(CallRecord(
            timestamp=now_ms(),
            tool=tool,
            downstream_server_id=server_id,
            calling_agent=calling_agent,
            latency_ms=latency_ms,
            attempt=attempt,
            outcome=outcome,
            fallback_action=fallback_action,
            error=error
        ))

def _empty_tool():
    from .config import ToolConfig
    return ToolConfig(name="", response_schema={})
