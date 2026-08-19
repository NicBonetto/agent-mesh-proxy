import time 
from collections import deque
from dataclasses import dataclass, field

from .config import FallbackRule

@dataclass
class CircuitState:
    failures: deque = field(default_factory=deque) # timestamps of recent failures
    opened_at: float | None = None
    cooldown_seconds: float = 30.0

    def record_failure(self, window_seconds: float) -> None:
        now = time.time()
        self.failures.append(now)
        cutoff = now - window_seconds
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.cooldown_seconds:
            self.opened_at = None
            self.failures.clear()
            return False
        return True

    def open(self, cooldown_seconds: float) -> None:
        self.opened_at = time.time()
        self.cooldown_seconds = cooldown_seconds

class FallbackEngine:
    def __init__(self):
        self._circuits: dict[str, CircuitState] = {}

    def _circuit(self, key: str) -> CircuitState:
        return self._circuits.setdefault(key, CircuitState())

    def circuit_is_open(self, server_id: str, tool: str) -> bool:
        return self._circuit(f"{server_id}:{tool}").is_open()

    def rule_for_outcome(self, rules: list[FallbackRule], outcome: str) -> FallbackRule | None:
        for rule in rules:
            if rule.on == outcome:
                return rule
        return None

    def note_failure(self, server_id: str, tool: str, rule: FallbackRule) -> bool:
        circuit = self._circuit(f"{server_id}:{tool}")
        circuit.record_failure(rule.window_seconds)
        if len(circuit.failures) >= rule.failure_threshold:
            circuit.open(rule.cooldown_seconds)
            return True
        return False

    @staticmethod
    def backoff_delay(rule: FallbackRule, attempt: int) -> float:
        if rule.backoff == "exponential":
            return rule.backoff_base_seconds * (2 ** (attempt - 1))
        return rule.backoff_base_seconds
