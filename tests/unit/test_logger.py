import uuid 

from proxy.logger import CallLogger, CallRecord, score

def make_record(**overrides) -> CallRecord:
    defaults = dict(
        call_id=str(uuid.uuid4()),
        timestamp=1000.0,
        tool="test_tool",
        downstream_server_id="mock-agent",
        calling_agent="tester",
        latency_ms=100.0,
        attempt=1,
        outcome="success"
    )
    defaults.update(overrides)
    return CallRecord(**defaults)

def test_record_and_load_roundtrip(tmp_path):
    logger = CallLogger(tmp_path / "calls.jsonl")
    rec = make_record()
    logger.record(rec)

    loaded = logger.load()
    assert len(loaded) == 1
    assert loaded[0]["tool"] == "test_tool"
    assert loaded[0]["outcome"] == "success"

def test_load_empty_log_returns_empty_list(tmp_path):
    logger = CallLogger(tmp_path / "does_not_exist.jsonl")
    assert logger.load() == []

def test_score_success_rate_and_latency(tmp_path):
    logger = CallLogger(tmp_path / "calls.jsonl")
    logger.record(make_record(latency_ms=100.0, outcome="success"))
    logger.record(make_record(latency_ms=200.0, outcome="success"))
    logger.record(make_record(latency_ms=300.0, outcome="error"))

    result = score(logger.load())
    print(result)
    assert result["count"] == 3
    assert result["success_rate"] == round((2 / 3), 4)
    assert result["outcomes"]["success"] == 2
    assert result["outcomes"]["error"] == 1

def test_score_filters_by_tool(tmp_path):
    logger = CallLogger(tmp_path / "calls.jsonl")
    logger.record(make_record(tool="tool_a", outcome="success"))
    logger.record(make_record(tool="tool_b", outcome="error"))

    result = score(logger.load(), tool="tool_a")
    assert result["count"] == 1
    assert result["success_rate"] == 1.0

def test_score_fallback_rate(tmp_path):
    logger = CallLogger(tmp_path / "calls.jsonl")
    logger.record(make_record(outcome="success", fallback_action=None))
    logger.record(make_record(outcome="success", fallback_action="retry"))

    result = score(logger.load())
    assert result["fallback_rate"] == 0.5

def test_score_empty_records_returns_zero_count():
    assert score([]) == {"count": 0}

def test_score_token_totals_split_by_source(tmp_path):
    logger = CallLogger(tmp_path / "calls.jsonl")

    logger.record(make_record())
    result = score(logger.load())
    assert "downstream_tokens" not in result

    logger.record(make_record(downstream_input_tokens=500, downstream_output_tokens=120))
    result = score(logger.load())
    assert result["downstream_tokens"] == {"input_total": 500, "output_total": 120}
