import argparse
import asyncio
import json
import sys

from .config import load_config
from .logger import CallLogger, score as compute_score
from .server import Proxy

def _parse_kv_args(pairs: list[str]) -> dict:
    result = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--arg must be key=value, got: {pair!r}")
        key, _, value = pair.partition("=")
        result[key] = value
    return result

def cmd_config_check(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Config invalid: {e}", file=sys.stderr)
        return 1
    print(f"Config OK: {args.config}")
    print(f"  proxy name: {config.proxy.name}")
    print(f"  log path: {config.proxy.log_path}")
    print(f"  downstream servers ({len(config.downstream_servers)}):")
    for s in config.downstream_servers:
        tool_names = ", ".join(t.name for t in s.tools) or "(non configured)"
        target = s.url if s.transport != "stdio" else f"{s.command} {' '.join(s.args)}"
        print(f"    - {s.id} [{s.transport}] {target}")
        print(f"      tools: {tool_names}")
    policies = ", ".join(config.fallback_policies.keys()) or "(none configured)"
    print(f"  fallback policies: {policies}")
    return 0

def cmd_call(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    proxy = Proxy(config)
    arguments = _parse_kv_args(args.arg)

    async def _run():
        try:
            result = await proxy.call(
                args.tool,
                arguments,
                calling_agent=args.agent,
                intent=args.intent,
                session_id=args.session
            )
            print(json.dumps(result, indent=2))
            return 0
        except Exception as e:
            print(f"Call failed: {e}", file=sys.stderr)
            return 1

    return asyncio.run(_run())

def cmd_score(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    records = CallLogger(config.proxy.log_path).load()
    print(json.dumps(compute_score(records, tool=args.tool), indent=2))
    return 0

def cmd_session_start(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    proxy = Proxy(config)
    session = proxy.sessions.create(args.goal)
    print(json.dumps({"session_id": session.session_id, "goal": session.goal}, indent=2))
    return 0

def cmd_session_close(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    proxy = Proxy(config)
    session = proxy.sessions.close(args.session_id, outcome=args.outcome)
    print(json.dumps(
        {"session_id": session.session_id, "status": session.status, "outcome": session.outcome},
        indent=2
    ))
    return 0

def cmd_serve(args: argparse.Namespace) -> int:
    print("`serve` is not implemented yet.", file=sys.stderr)
    return 2

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-mesh-proxy")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("config_check", help="Validate config.yaml and prints a summary")
    p_check.set_defaults(func=cmd_config_check)

    p_call = sub.add_parser("call", help="Make a single ad-hoc call through the proxy")
    p_call.add_argument("tool", help="Tool name to call")
    p_call.add_argument(
        "--arg", action="append", default=[],
        help="Tool argument as key=value. Repeatable."
    )
    p_call.add_argument("--agent", default="cli", help="calling_agent label for logging")
    p_call.add_argument(
        "--intent", default=None,
        help="Session id to attach this call to (see: python -m proxy.cli session-start)"
    )
    p_call.set_defaults(func=cmd_call)

    p_score = sub.add_parser("score", help="Print performance stats from the call log")
    p_score.add_argument("--tool", default=None, help="Filter to a single tool")
    p_score.set_defaults(func=cmd_score)

    p_sess_start = sub.add_parser("session-start", help="Start a new multi-hop interaction session")
    p_sess_start.add_argument("goal", help="What this session is trying to accomplish overall")
    p_sess_start.set_defaults(func=cmd_session_start)

    p_sess_close = sub.add_parser("session-close", help="Close a session and record its outcome")
    p_sess_close.add_argument("session_id")
    p_sess_close.add_argument(
        "--outcome", choices=["success", "failure"], default=None,
        help="Whether the overall multi-hop task succeeded"
    )
    p_sess_close.set_defaults(func=cmd_session_close)

    p_serve = sub.add_parser("serve", help="[not yet implemented] run as a long-lived MCP server")
    p_serve.set_defaults(func=cmd_serve)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())

