"""Tests for v0.3 features: vector memory, auth, cron, metrics, streaming."""

import time
import pytest


class TestCronParser:
    def test_every_minute(self):
        from hive.core.cron_parser import is_due, describe_cron
        assert is_due("* * * * *") is True
        assert "every minute" in describe_cron("* * * * *")

    def test_every_5_minutes(self):
        from hive.core.cron_parser import describe_cron
        desc = describe_cron("*/5 * * * *")
        assert "5" in desc

    def test_specific_time(self):
        from hive.core.cron_parser import describe_cron
        desc = describe_cron("30 9 * * *")
        assert "09" in desc or "9" in desc

    def test_next_run_time(self):
        from hive.core.cron_parser import next_run_time
        from datetime import datetime
        result = next_run_time("* * * * *")
        assert isinstance(result, datetime)
        assert result > datetime.now()

    def test_invalid_expression(self):
        from hive.core.cron_parser import next_run_time
        with pytest.raises(ValueError):
            next_run_time("invalid")

    def test_is_due_with_last_run(self):
        from hive.core.cron_parser import is_due
        # Should be due if last run was 2 minutes ago with */1 schedule
        assert is_due("* * * * *", time.time() - 120) is True


class TestAuth:
    def test_create_and_verify_token(self):
        from hive.core.auth import create_token, verify_token
        token = create_token("test-user", "admin")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "test-user"
        assert payload["role"] == "admin"

    def test_invalid_token(self):
        from hive.core.auth import verify_token
        assert verify_token("invalid.token.here") is None

    def test_expired_token(self):
        from hive.core.auth import create_token, verify_token
        import hive.core.auth as auth_module
        original = auth_module.TOKEN_EXPIRY
        auth_module.TOKEN_EXPIRY = -1  # already expired
        token = create_token("test-user")
        auth_module.TOKEN_EXPIRY = original
        assert verify_token(token) is None

    def test_token_has_required_fields(self):
        from hive.core.auth import create_token, verify_token
        token = create_token("user1")
        payload = verify_token(token)
        assert "sub" in payload
        assert "iat" in payload
        assert "exp" in payload


class TestMetrics:
    def test_counter(self):
        from hive.core.metrics import MetricsCollector
        m = MetricsCollector()
        m.inc("requests", labels={"method": "GET"})
        m.inc("requests", labels={"method": "GET"})
        assert m.get_counter("requests", {"method": "GET"}) == 2

    def test_histogram(self):
        from hive.core.metrics import MetricsCollector
        m = MetricsCollector()
        for v in [10, 20, 30, 40, 50]:
            m.observe("latency", v)
        stats = m.get_histogram_stats("latency")
        assert stats["count"] == 5
        assert stats["avg"] == 30.0

    def test_gauge(self):
        from hive.core.metrics import MetricsCollector
        m = MetricsCollector()
        m.set_gauge("temperature", 22.5)
        assert m._gauges["temperature"] == 22.5

    def test_summary(self):
        from hive.core.metrics import MetricsCollector
        m = MetricsCollector()
        m.inc("test_counter")
        s = m.summary()
        assert "uptime_seconds" in s
        assert "counters" in s

    def test_prometheus_format(self):
        from hive.core.metrics import MetricsCollector
        m = MetricsCollector()
        m.inc("http_requests_total")
        output = m.prometheus_format()
        assert "http_requests_total" in output
        assert "counter" in output


class TestVectorMemory:
    def test_remember_and_recall(self):
        from hive.core.vector_memory import VectorMemory
        mem = VectorMemory("test-agent-vec")
        mem.clear()
        mem.remember("Python is a programming language")
        mem.remember("The weather is sunny today")
        results = mem.recall("programming")
        assert len(results) >= 1
        assert any("Python" in r["content"] for r in results)
        mem.clear()

    def test_count(self):
        from hive.core.vector_memory import VectorMemory
        mem = VectorMemory("test-agent-count")
        mem.clear()
        assert mem.count == 0
        mem.remember("test memory")
        assert mem.count == 1
        mem.clear()

    def test_clear(self):
        from hive.core.vector_memory import VectorMemory
        mem = VectorMemory("test-agent-clear")
        mem.remember("temp")
        count = mem.clear()
        assert count >= 0
        assert mem.count == 0

    def test_list_all(self):
        from hive.core.vector_memory import VectorMemory
        mem = VectorMemory("test-agent-list")
        mem.clear()
        mem.remember("memory one")
        mem.remember("memory two")
        all_mem = mem.list_all()
        assert len(all_mem) >= 2
        mem.clear()
