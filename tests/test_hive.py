"""Tests for Hive core modules."""

import pytest
from hive.core.config import Settings, settings
from hive.core.agent import AgentConfig, ToolRegistry, tool_registry, _safe_eval
from hive.core.llm import estimate_cost, get_providers


class TestConfig:
    def test_settings_loads(self):
        assert settings.HOST == "127.0.0.1"
        assert settings.PORT == 8000

    def test_providers_defined(self):
        assert "ollama" in settings.PROVIDERS
        assert "openai" in settings.PROVIDERS
        assert "anthropic" in settings.PROVIDERS
        assert "groq" in settings.PROVIDERS

    def test_pricing_defined(self):
        assert "gpt-4o-mini" in settings.PRICING
        assert "llama3.2" in settings.PRICING


class TestAgentConfig:
    def test_defaults(self):
        config = AgentConfig(name="test", system_prompt="hello")
        assert config.provider == "ollama"
        assert config.temperature == 0.7
        assert config.max_iterations == 10

    def test_custom(self):
        config = AgentConfig(name="test", system_prompt="hi", provider="openai", model="gpt-4o-mini")
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"


class TestCostEstimation:
    def test_known_model(self):
        cost = estimate_cost("gpt-4o-mini", 1000, 500)
        assert cost > 0
        assert cost < 0.01  # should be very cheap

    def test_free_model(self):
        cost = estimate_cost("llama3.2", 1000, 500)
        assert cost == 0.0

    def test_unknown_model(self):
        cost = estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


class TestToolRegistry:
    def test_builtin_tools_registered(self):
        schemas = tool_registry.get_schema()
        names = [s["function"]["name"] for s in schemas]
        assert "calculator" in names
        assert "get_time" in names

    def test_get_schema_filtered(self):
        schemas = tool_registry.get_schema(["calculator"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "calculator"

    def test_register_custom_tool(self):
        registry = ToolRegistry()
        registry.register("test_tool", "A test tool", {"type": "object", "properties": {}}, lambda: "ok")
        schemas = registry.get_schema()
        assert len(schemas) == 1

    @pytest.mark.asyncio
    async def test_execute_calculator(self):
        result = await tool_registry.execute("calculator", '{"expression": "2 + 3"}')
        assert result == "5"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        result = await tool_registry.execute("nonexistent", '{}')
        assert "Error" in result


class TestSafeEval:
    def test_addition(self):
        import ast
        node = ast.parse("2 + 3", mode="eval")
        assert _safe_eval(node.body) == 5

    def test_division_by_zero(self):
        import ast
        node = ast.parse("1 / 0", mode="eval")
        with pytest.raises(ValueError):
            _safe_eval(node.body)


class TestProviders:
    def test_get_providers(self):
        providers = get_providers()
        assert len(providers) >= 5
        names = [p["name"] for p in providers]
        assert "ollama" in names
        assert "openai" in names

    def test_ollama_configured(self):
        providers = get_providers()
        ollama = next(p for p in providers if p["name"] == "ollama")
        assert ollama["configured"] is True  # ollama doesn't potrebuje key
