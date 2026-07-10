import time

import pytest

from app.infrastructure.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_default_closed(self):
        cb = CircuitBreaker()
        assert cb.is_open("test") is False
        assert cb.state("test") == "closed"

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(fail_threshold=3, cooldown_seconds=0.01)
        cb.record_failure("s")
        cb.record_failure("s")
        assert cb.is_open("s") is False
        cb.record_failure("s")
        assert cb.is_open("s") is True

    def test_success_resets(self):
        cb = CircuitBreaker(fail_threshold=2, cooldown_seconds=0.01)
        cb.record_failure("s")
        assert cb.state("s") == "degraded (1/2)"
        cb.record_success("s")
        assert cb.state("s") == "closed"

    def test_cooldown_expires(self):
        cb = CircuitBreaker(fail_threshold=1, cooldown_seconds=0.001)
        cb.record_failure("s")
        assert cb.is_open("s") is True
        time.sleep(0.01)
        assert cb.is_open("s") is False
        assert cb.state("s") == "closed"

    def test_reset_specific(self):
        cb = CircuitBreaker(fail_threshold=2, cooldown_seconds=0.01)
        cb.record_failure("a")
        cb.record_failure("a")
        cb.record_failure("b")
        assert cb.is_open("a") is True
        cb.reset("a")
        assert cb.is_open("a") is False
        assert cb.state("b") == "degraded (1/2)"

    def test_reset_all(self):
        cb = CircuitBreaker(fail_threshold=2, cooldown_seconds=0.01)
        cb.record_failure("a")
        cb.record_failure("a")
        cb.record_failure("b")
        cb.record_failure("b")
        assert cb.is_open("a") is True
        assert cb.is_open("b") is True
        cb.reset()
        assert cb.is_open("a") is False
        assert cb.is_open("b") is False

    def test_allow_returns_false_when_open(self):
        cb = CircuitBreaker(fail_threshold=1, cooldown_seconds=0.01)
        assert cb.allow("s") is True
        cb.record_failure("s")
        assert cb.allow("s") is False
