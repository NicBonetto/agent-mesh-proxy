# agent-mesh-proxy
A verification / fallback / performance-measurement proxy for agent-to-agent calls. 

## About
This middleware sits between a calling agent and one or more downstream MCP servers, and for every tool call it:
1. Logs the request, response, latency, and outcome
2. Validates the response against a per-tool schema
3. Applies fallback policies on timeout/error
4. Scores each downstream agent over time
