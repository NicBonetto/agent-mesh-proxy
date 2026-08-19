import json
import statistics
import time 
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

@dataclass
class CallRecord:
    call_id: str
    timestamp: float
    tool: str
    downstream_server_id: str
    calling_agent: Optional[str]
    latency_ms: float
    attempt: int
    outcome: str
    fallback_action: Optional[str] = None
    request_preview: Optional[str] = None
    response_preview: Optional[str] = None
    error: Optional[str] = None
    intent: Optional[str] = None
    session_id: Optional[str] = None
    parent_call_id: Optional[str] = None
    downstream_input_tokens: Optional[int] = None
    downstream_output_tokens: Optional[int] = None

class CallLogger:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, rec: CallRecord) -> None:
        with self.log_path.open("a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")

    def load(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        with self.log_path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

def score(records: list[dict[str, Any]], tool: Optional[str] = None) -> dict[str, Any]:
    rows = [r for r in records if tool is None or r["tool"] == tool]
    if not rows:
        return {"count": 0}

    latencies = sorted(r["latency_ms"] for r in rows)
    successes = [r for r in rows if r["outcome"] == "success"]
    fallbacks = [r for r in rows if r.get("fallback_action")]

    def pct(p: float) -> float:
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    result = {
        "count": len(rows),
        "success_rate": round(len(successes) / len(rows), 4),
        "fallback_rate": round(len(fallbacks) / len(rows), 4),
        "latency_ms_p50": pct(0.50),
        "latency_ms_p95": pct(0.95),
        "latency_ms_mean": round(statistics.mean(latencies), 1),
        "outcomes": {
            outcome: sum(1 for r in rows if r["outcome"] == outcome)
            for outcome in {r["outcome"] for r in rows}
        }
    }

    down_in = [r["downstream_input_tokens"] for r in rows if r.get("downstream_input_tokens") is not None]
    down_out = [r["downstream_output_tokens"] for r in rows if r.get("downstream_output_tokens") is not None]
    if down_in or down_out:
        result["downstream_tokens"] = {
            "input_total": sum(down_in),
            "output_total": sum(down_out)
        }
    return result

def now_ms() -> float:
    return time.time() * 1000
