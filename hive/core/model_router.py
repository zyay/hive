"""
Intelligent Model Router — selects the best model based on task requirements.
Uses Artificial Analysis Aug 2026 rankings for decision making.
"""

from dataclasses import dataclass
from hive.core.config import settings


@dataclass
class ModelRecommendation:
    provider: str
    model: str
    reason: str
    intelligence: int
    speed_tier: str
    cost_tier: str
    estimated_cost_per_1k: float


def select_model(
    task: str = "",
    priority: str = "balanced",
    privacy: bool = False,
    context_length: int = 0,
    vision: bool = False,
) -> ModelRecommendation:
    """
    Select the best model for a given task.

    Args:
        task: Description of the task (coding, reasoning, chat, etc.)
        priority: "intelligence" | "speed" | "budget" | "balanced"
        privacy: If True, prefer local/open-weights models
        context_length: Required context window size
        vision: If True, model must support vision

    Returns:
        ModelRecommendation with provider, model, reasoning
    """
    task_lower = task.lower()

    # Privacy → open-weights/local
    if privacy:
        if context_length > 100_000:
            return _rec("ollama", "llama3.3", "Privacy required + long context → local Llama 3.3")
        return _rec("local", "kimi-k3-max", "Privacy required → Kimi K3 (best open-weights, Index: 60)")

    # Long context (>500K) → Gemini 2.5 Pro (2M context, free)
    if context_length > 500_000:
        return _rec("gemini", "gemini-2.5-pro", f"Context {context_length} tokens → Gemini 2.5 Pro (2M context, free)")

    # Vision required
    if vision:
        if priority == "budget":
            return _rec("gemini", "gemini-2.5-flash", "Vision + budget → Gemini 2.5 Flash (free tier)")
        return _rec("openai", "gpt-4.1-mini", "Vision + balanced → GPT-4.1 Mini (1M context, $0.40/M)")

    # Task-specific routing
    is_coding = any(w in task_lower for w in ["code", "program", "debug", "refactor", "function", "class", "api"])
    is_reasoning = any(w in task_lower for w in ["reason", "analyze", "complex", "math", "logic", "prove"])
    is_creative = any(w in task_lower for w in ["write", "creative", "story", "poem", "essay"])
    is_simple = any(w in task_lower for w in ["translate", "summarize", "format", "convert", "simple"])

    # Coding → Claude Opus 5 (Code Arena winner)
    if is_coding and priority in ("intelligence", "balanced"):
        return _rec("anthropic", "claude-sonnet-4-20250514", "Coding task → Claude Sonnet 4 (Code Arena top performer)")

    # Complex reasoning → Claude Opus 5 (Intelligence Index: 63, #1)
    if is_reasoning and priority == "intelligence":
        return _rec("anthropic", "claude-opus-5-max", "Complex reasoning → Claude Opus 5 Max (Intelligence Index: 63, #1)")

    # Priority-based routing
    if priority == "intelligence":
        return _rec("anthropic", "claude-opus-5-max", "Maximum intelligence → Claude Opus 5 Max (Index: 63)")

    if priority == "speed":
        return _rec("groq", "llama-3.3-70b-versatile", "Maximum speed → Groq Llama 3.3 (ultra-fast inference)")

    if priority == "budget":
        if is_simple:
            return _rec("openai", "gpt-4.1-nano", "Simple task + budget → GPT-4.1 Nano ($0.10/M)")
        return _rec("openai", "gpt-5.6-luna-low", "Budget → GPT-5.6 Luna Low ($0.01/task)")

    # Balanced (default)
    if is_creative:
        return _rec("anthropic", "claude-fable-5", "Creative task → Claude Fable 5 (balanced + creative)")
    if is_simple:
        return _rec("openai", "gpt-4.1-mini", "Simple task → GPT-4.1 Mini (fast + cheap)")
    return _rec("anthropic", "claude-sonnet-4-20250514", "Balanced → Claude Sonnet 4 (best all-rounder)")


def _rec(provider: str, model: str, reason: str) -> ModelRecommendation:
    """Build a ModelRecommendation from config data."""
    info = settings.MODEL_INFO.get(model, {})
    pricing = settings.PRICING.get(model, (0.0, 0.0))
    return ModelRecommendation(
        provider=provider,
        model=model,
        reason=reason,
        intelligence=info.get("intelligence", 0),
        speed_tier=info.get("speed_tier", "unknown"),
        cost_tier=info.get("cost_tier", "unknown"),
        estimated_cost_per_1k=round((pricing[0] + pricing[1]) / 2000, 6),
    )


def compare_models(models: list[str]) -> list[dict]:
    """Compare multiple models side-by-side with all metrics."""
    result = []
    for model in models:
        info = settings.MODEL_INFO.get(model, {})
        pricing = settings.PRICING.get(model, (0.0, 0.0))
        # Find provider
        provider = "unknown"
        for pname, pcfg in settings.PROVIDERS.items():
            if pcfg["model"] == model:
                provider = pname
                break
        result.append({
            "model": model,
            "provider": provider,
            "intelligence": info.get("intelligence", 0),
            "context_window": info.get("context", 0),
            "vision": info.get("vision", False),
            "tools": info.get("tools", False),
            "speed_tier": info.get("speed_tier", "unknown"),
            "cost_tier": info.get("cost_tier", "unknown"),
            "cost_in_per_m": pricing[0],
            "cost_out_per_m": pricing[1],
        })
    return sorted(result, key=lambda x: -x["intelligence"])
