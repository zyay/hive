"""Tests for adaptive reasoning, cost optimizer, and arena benchmarking."""

import pytest


class TestAdaptiveReasoning:
    def test_simple_task(self):
        from hive.core.adaptive import analyze_task
        result = analyze_task("What is the capital of France?")
        assert result.complexity == "simple"
        assert result.recommended_effort == "low"

    def test_complex_task(self):
        from hive.core.adaptive import analyze_task
        result = analyze_task("Analyze and compare the architectural designs of these two systems, evaluate their tradeoffs and optimize the deployment strategy")
        assert result.complexity == "complex"
        assert result.recommended_effort == "maximum"

    def test_coding_task(self):
        from hive.core.adaptive import analyze_task
        result = analyze_task("Write a Python function to implement binary search")
        assert result.category == "coding"

    def test_creative_task(self):
        from hive.core.adaptive import analyze_task
        result = analyze_task("Write a creative story about a robot learning to paint")
        assert result.category == "creative"

    def test_long_prompt(self):
        from hive.core.adaptive import analyze_task
        long_prompt = "word " * 300
        result = analyze_task(long_prompt)
        assert result.estimated_tokens > 100

    def test_all_fields_present(self):
        from hive.core.adaptive import analyze_task
        result = analyze_task("test prompt")
        assert result.complexity in ("simple", "moderate", "complex")
        assert result.category in ("coding", "creative", "chat", "analysis", "reasoning")
        assert result.recommended_effort in ("low", "balanced", "maximum")
        assert result.recommended_provider
        assert result.recommended_model


class TestCostOptimizer:
    def test_empty_usage(self):
        from hive.core.cost_optimizer import analyze_usage
        result = analyze_usage([])
        assert result["total_cost"] == 0
        assert result["recommendations"] == []

    def test_with_usage_data(self):
        from hive.core.cost_optimizer import analyze_usage
        logs = [
            {"model": "gpt-4.1-mini", "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001, "latency_ms": 200},
            {"model": "gpt-4.1-mini", "tokens_in": 200, "tokens_out": 100, "cost_usd": 0.002, "latency_ms": 300},
        ]
        result = analyze_usage(logs)
        assert result["total_requests"] == 2
        assert result["total_cost"] > 0
        assert "gpt-4.1-mini" in result["by_model"]

    def test_premium_model_recommendation(self):
        from hive.core.cost_optimizer import analyze_usage
        logs = [
            {"model": "claude-opus-5-max", "tokens_in": 1000, "tokens_out": 500, "cost_usd": 0.05, "latency_ms": 5000}
            for _ in range(60)
        ]
        result = analyze_usage(logs)
        assert len(result["recommendations"]) > 0
        assert result["potential_savings"] > 0


class TestArenaBenchmark:
    def test_benchmark_prompts_exist(self):
        from hive.core.arena import BENCHMARK_PROMPTS
        assert "reasoning" in BENCHMARK_PROMPTS
        assert "coding" in BENCHMARK_PROMPTS
        assert "creative" in BENCHMARK_PROMPTS
        assert "factual" in BENCHMARK_PROMPTS

    def test_benchmark_result_dataclass(self):
        from hive.core.arena import BenchmarkResult
        r = BenchmarkResult(
            model="test", provider="test", category="reasoning",
            score=0.8, avg_latency_ms=200, total_cost_usd=0.01,
            total_tokens=500, num_prompts=3,
        )
        assert r.score == 0.8
        assert r.model == "test"

    def test_format_benchmark_table(self):
        from hive.core.arena import BenchmarkResult, format_benchmark_table
        results = [
            BenchmarkResult("model-a", "prov", "cat", 0.9, 100, 0.01, 500, 3),
            BenchmarkResult("model-b", "prov", "cat", 0.7, 200, 0.02, 600, 3),
        ]
        table = format_benchmark_table(results)
        assert "model-a" in table
        assert "model-b" in table
        assert "🏆" in table
