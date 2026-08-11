"""
Monitoring & observability — in-memory metrics collection.
Exposes metrics via /api/metrics endpoint.
"""

import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Simple in-memory metrics collector."""

    def __init__(self):
        self._counters = defaultdict(int)
        self._histograms = defaultdict(list)
        self._gauges = {}
        self._start_time = time.time()

    def inc(self, name: str, value: int = 1, labels: dict = None):
        """Increment a counter."""
        key = self._make_key(name, labels)
        self._counters[key] += value

    def observe(self, name: str, value: float, labels: dict = None):
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        # Keep last 1000 observations
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def set_gauge(self, name: str, value: float, labels: dict = None):
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def get_counter(self, name: str, labels: dict = None) -> int:
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_histogram_stats(self, name: str, labels: dict = None) -> dict:
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "sum": round(sum(sorted_vals), 2),
            "avg": round(sum(sorted_vals) / n, 2),
            "p50": round(sorted_vals[n // 2], 2),
            "p95": round(sorted_vals[int(n * 0.95)], 2),
            "p99": round(sorted_vals[int(n * 0.99)], 2),
        }

    def summary(self) -> dict:
        """Return full metrics summary."""
        uptime = time.time() - self._start_time
        return {
            "uptime_seconds": round(uptime, 1),
            "counters": dict(self._counters),
            "histograms": {
                k: self.get_histogram_stats(k.split("{")[0])
                for k in self._histograms
            },
            "gauges": dict(self._gauges),
        }

    def prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        for key, value in self._counters.items():
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")
        for key, values in self._histograms.items():
            name = key.split("{")[0]
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count {len(values)}")
            lines.append(f"{name}_sum {round(sum(values), 2)}")
        for key, value in self._gauges.items():
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")
        return "\n".join(lines)

    def _make_key(self, name: str, labels: dict = None) -> str:
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name


# Global metrics instance
metrics = MetricsCollector()
