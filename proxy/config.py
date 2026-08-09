from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

class ToolConfig(BaseModel):
    name: str
    response_schema: dict = Field(default_factory=dict)

class AuthConfig(BaseModel):
    type: Literal["none", "bearer", "api_key"] = "none"
    token_env: Optional[str] = None
    header_name: str = "Authorization"

    def resolve_token(self) -> Optional[str]:
        import os
        if self.type == "none" or not self.token_env:
            return None
        token = os.environ.get(self.token_env)
        if token is None:
            raise ValueError(
                f"Auth configured with token_env={self.token_env!r} but that "
                f"environment variable is not set."
            )
        return token

class DownstreamServer(BaseModel):
    id: str
    transport: Literal["streamable_http", "sse", "stdio"] = "streamable_http"
    url: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    timeout_seconds: float = 10.0
    tools: list[ToolConfig] = Field(default_factory=list)

    def tool(self, name: str) -> Optional[ToolConfig]:
        for t in self.tools:
            if t.name == name:
                return t 
        return None

    def model_post_init(self, __context) -> None:
        if self.transport in ("streamable_http", "sse") and not self.url:
            raise ValueError(
                f"downstream_server {self.id!r}: transport={self.transport!r} "
                f"requires a 'url'"
            )
        if self.transport == "stdio" and not self.command:
            raise ValueError(
                f"downstream_server {self.id!r}: transport='stdio' requires a 'command'"
            )

class FallbackRule(BaseModel):
    on: Literal["timeout", "schema_mismatch", "error", "circuit_open"]
    action: Literal["retry", "circuit_break", "route_to", "fail_fast"]
    max_attempts: int = 1
    backoff: Literal["fixed", "exponential"] = "fixed"
    backoff_base_seconds: float = 1.0
    failure_threshold: int = 5
    window_seconds: float = 60.0
    cooldown_seconds: float = 30.0
    target: Optional[str] = None

class ProxyConfig(BaseModel):
    name: str = "agent-mesh-proxy"
    log_path: str = "./logs/calls.jsonl"

class Config(BaseModel):
    proxy: ProxyConfig
    downstream_servers: list[DownstreamServer]
    fallback_policies: dict[str, list[FallbackRule]] = Field(default_factory=dict)

    def server(self, server_id: str) -> DownstreamServer:
        for s in self.downstream_servers:
            if s.id == server_id:
                return s 
        raise KeyError(f"No downstream server configured with id={server_id!r}")

    def policy_for(self, tool_name: str) -> list[FallbackRule]:
        return self.fallback_policies.get(
            tool_name, self.fallback_policies.get("default", [])
        )

def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config.model_validate(raw)
