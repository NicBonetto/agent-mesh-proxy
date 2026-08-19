import time 

from proxy.config import FallbackRule
from proxy.fallback import FallbackEngine

def make_rule(**overrides) -> FallbackRule:
    defaults = dict(
        on="error",
        action="circuit_break",
        failure_threshold=3,
        window_seconds=10.0,
        cooldown_seconds=0.2
    )
    defaults.update(overrides)
    return FallbackRule(**defaults)

def test_circuit_closed_initially():
    engine = FallbackEngine()
    assert not engine.circuit_is_open("server-a", "tool-a")

def test_circuit_opens_after_threshold_failures():
    engine = FallbackEngine()
    rule = make_rule(failure_threshold=3)

    for _ in range(2):
        opened = engine.note_failure("server-a", "tool-a", rule)
        assert opened is False

    opened = engine.note_failure("server-a", "tool-a", rule)
    assert opened is True
    assert engine.circuit_is_open("server-a", "tool-a")

def test_circuit_recovers_after_cooldown():
    engine = FallbackEngine()
    rule = make_rule(failure_threshold=1, cooldown_seconds=0.1)

    engine.note_failure("server-a", "tool-a", rule)
    assert engine.circuit_is_open("server-a", "tool-a")

    time.sleep(0.15)
    assert not engine.circuit_is_open("server-a", "tool-a")

def test_circuits_are_independent_per_server_and_tool():
    engine = FallbackEngine()
    rule = make_rule(failure_threshold=1)

    engine.note_failure("server-a", "tool-a", rule)
    assert engine.circuit_is_open("server-a", "tool-a")
    assert not engine.circuit_is_open("server-a", "tool-b")
    assert not engine.circuit_is_open("server-b", "tool-a")

def test_backoff_delay_fixed():
    rule = make_rule(backoff="fixed", backoff_base_seconds=1.0)
    assert FallbackEngine.backoff_delay(rule, attempt=1) == 1.0
    assert FallbackEngine.backoff_delay(rule, attempt=2) == 1.0

def test_backoff_delay_exponential():
    rule = make_rule(backoff="exponential", backoff_base_seconds=1.0)
    assert FallbackEngine.backoff_delay(rule, attempt=1) == 1.0
    assert FallbackEngine.backoff_delay(rule, attempt=2) == 2.0
    assert FallbackEngine.backoff_delay(rule, attempt=3) == 4.0

def test_rule_for_outcome_matches_correctly():
    engine = FallbackEngine()
    rules = [
        make_rule(on="timeout", action="retry"),
        make_rule(on="error", action="circuit_break")
    ]
    assert engine.rule_for_outcome(rules, "timeout").action == "retry"
    assert engine.rule_for_outcome(rules, "error").action == "circuit_break"
    assert engine.rule_for_outcome(rules, "schema_mismatch") is None
