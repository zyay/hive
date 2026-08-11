"""Tests for MCP integrations and benchmark suite."""

import pytest


class TestMCPIntegrations:
    def test_registry_register(self):
        from hive.core.mcp_integrations import IntegrationRegistry
        reg = IntegrationRegistry()
        conn = reg.register("test-server", "/path/to/server.py")
        assert "test-server" in reg.connections
        assert conn.name == "test-server"

    @pytest.mark.asyncio
    async def test_registry_execute_invalid_format(self):
        from hive.core.mcp_integrations import IntegrationRegistry
        reg = IntegrationRegistry()
        result = await reg.execute("invalid_format", {})
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_registry_execute_unknown_server(self):
        from hive.core.mcp_integrations import IntegrationRegistry
        reg = IntegrationRegistry()
        result = await reg.execute("unknown__tool", {})
        assert "not registered" in result

    def test_get_all_tool_schemas_empty(self):
        from hive.core.mcp_integrations import IntegrationRegistry
        reg = IntegrationRegistry()
        schemas = reg.get_all_tool_schemas()
        assert schemas == []

    def test_tool_proxy_creation(self):
        from hive.core.mcp_integrations import MCPServerConnection
        conn = MCPServerConnection("test", "/path/server.py")
        proxy = conn.get_tool_proxy("my_tool")
        assert proxy.tool_name == "my_tool"
        assert proxy.server_path == "/path/server.py"


class TestBenchmarkSuite:
    def test_benchmarks_exist(self):
        from hive.core.benchmark_suite import BENCHMARKS
        assert "reasoning" in BENCHMARKS
        assert "coding" in BENCHMARKS
        assert "factual" in BENCHMARKS
        assert "creative" in BENCHMARKS

    def test_benchmark_has_prompts(self):
        from hive.core.benchmark_suite import BENCHMARKS
        for category, prompts in BENCHMARKS.items():
            assert len(prompts) >= 3, f"{category} has too few prompts"

    def test_benchmark_prompt_format(self):
        from hive.core.benchmark_suite import BENCHMARKS
        for category, prompts in BENCHMARKS.items():
            for p in prompts:
                assert "prompt" in p
                assert "expected_keywords" in p
                assert len(p["prompt"]) > 10

    def test_benchmark_result_dataclass(self):
        from hive.core.benchmark_suite import BenchmarkResult
        r = BenchmarkResult(
            model="test", provider="test", category="reasoning",
            score=0.8, avg_latency_ms=200, total_cost_usd=0.01,
            total_tokens=500, num_prompts=5,
        )
        assert r.score == 0.8
        assert r.provider == "test"

    def test_format_comparison_table(self):
        from hive.core.benchmark_suite import BenchmarkResult, format_comparison_table
        results = [
            BenchmarkResult("p1", "model-alpha", "cat", 0.9, 100, 0.01, 500, 5),
            BenchmarkResult("p2", "model-beta", "cat", 0.7, 200, 0.02, 600, 5),
        ]
        table = format_comparison_table(results)
        assert "model-alpha" in table
        assert "model-beta" in table
