"""Tests for model router — intelligent model selection."""

import pytest


class TestModelRouter:
    def test_select_budget(self):
        from hive.core.model_router import select_model
        rec = select_model(priority="budget")
        assert rec.cost_tier == "budget"
        assert "luna" in rec.model.lower() or "nano" in rec.model.lower()

    def test_select_intelligence(self):
        from hive.core.model_router import select_model
        rec = select_model(priority="intelligence")
        assert rec.intelligence >= 60
        assert "opus" in rec.model.lower()

    def test_select_speed(self):
        from hive.core.model_router import select_model
        rec = select_model(priority="speed")
        assert rec.speed_tier == "ultra"

    def test_select_privacy(self):
        from hive.core.model_router import select_model
        rec = select_model(privacy=True)
        assert rec.cost_tier == "free"
        assert "kimi" in rec.model.lower() or "llama" in rec.model.lower()

    def test_select_long_context(self):
        from hive.core.model_router import select_model
        rec = select_model(context_length=600_000)
        assert "gemini" in rec.model.lower()

    def test_select_vision(self):
        from hive.core.model_router import select_model
        rec = select_model(vision=True)
        from hive.core.config import settings
        info = settings.MODEL_INFO.get(rec.model, {})
        assert info.get("vision", False) is True

    def test_select_coding(self):
        from hive.core.model_router import select_model
        rec = select_model(task="write a Python function to sort a list")
        assert "claude" in rec.model.lower()

    def test_select_reasoning(self):
        from hive.core.model_router import select_model
        rec = select_model(task="analyze this complex logic problem", priority="intelligence")
        assert rec.intelligence >= 60

    def test_compare_models(self):
        from hive.core.model_router import compare_models
        result = compare_models(["claude-opus-5-max", "gpt-4.1-mini", "gemini-2.5-flash"])
        assert len(result) == 3
        # Should be sorted by intelligence (descending)
        assert result[0]["intelligence"] >= result[-1]["intelligence"]

    def test_recommendation_has_all_fields(self):
        from hive.core.model_router import select_model
        rec = select_model(task="hello")
        assert rec.provider
        assert rec.model
        assert rec.reason
        assert isinstance(rec.intelligence, int)
        assert rec.speed_tier
        assert rec.cost_tier


class TestConfig2026:
    def test_claude_opus_5_in_pricing(self):
        from hive.core.config import settings
        assert "claude-opus-5-max" in settings.PRICING
        assert "claude-opus-5-high" in settings.PRICING

    def test_gpt_56_in_pricing(self):
        from hive.core.config import settings
        assert "gpt-5.6-sol-max" in settings.PRICING
        assert "gpt-5.6-luna-low" in settings.PRICING

    def test_speed_champions_in_pricing(self):
        from hive.core.config import settings
        assert "celeris-1" in settings.PRICING
        assert "mercury-2" in settings.PRICING

    def test_open_weights_in_pricing(self):
        from hive.core.config import settings
        assert "kimi-k3-max" in settings.PRICING
        assert "llama-4-scout" in settings.PRICING

    def test_model_info_has_intelligence(self):
        from hive.core.config import settings
        assert settings.MODEL_INFO["claude-opus-5-max"]["intelligence"] == 63
        assert settings.MODEL_INFO["kimi-k3-max"]["intelligence"] == 60

    def test_providers_include_new(self):
        from hive.core.config import settings
        assert "xai" in settings.PROVIDERS
        assert "deepseek" in settings.PROVIDERS
        assert len(settings.PROVIDERS) >= 10
