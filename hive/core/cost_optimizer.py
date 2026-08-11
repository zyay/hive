"""
Cost Optimization Dashboard — analyze usage and suggest savings.
"""

import logging
from hive.core.config import settings

logger = logging.getLogger(__name__)


def analyze_usage(usage_logs: list[dict]) -> dict:
    """
    Analyze usage patterns and suggest cost optimizations.

    Args:
        usage_logs: List of usage log dicts from the database.

    Returns:
        Dict with analysis, recommendations, and potential savings.
    """
    if not usage_logs:
        return {"total_cost": 0, "recommendations": [], "potential_savings": 0}

    # Group by model
    by_model = {}
    for log in usage_logs:
        model = log.get("model", "unknown")
        if model not in by_model:
            by_model[model] = {"requests": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "latency_sum": 0.0}
        by_model[model]["requests"] += 1
        by_model[model]["tokens_in"] += log.get("tokens_in", 0)
        by_model[model]["tokens_out"] += log.get("tokens_out", 0)
        by_model[model]["cost"] += log.get("cost_usd", 0.0)
        by_model[model]["latency_sum"] += log.get("latency_ms", 0.0)

    # Calculate averages
    for model, data in by_model.items():
        if data["requests"] > 0:
            data["avg_latency_ms"] = round(data["latency_sum"] / data["requests"], 1)
            data["avg_cost_per_request"] = round(data["cost"] / data["requests"], 6)
        else:
            data["avg_latency_ms"] = 0
            data["avg_cost_per_request"] = 0

    total_cost = sum(d["cost"] for d in by_model.values())
    total_requests = sum(d["requests"] for d in by_model.values())

    # Generate recommendations
    recommendations = []

    for model, data in by_model.items():
        info = settings.MODEL_INFO.get(model, {})
        cost_tier = info.get("cost_tier", "unknown")

        # Suggest cheaper alternatives for high-volume premium models
        if cost_tier in ("premium", "high") and data["requests"] > 50:
            cheaper = _find_cheaper_alternative(model)
            if cheaper:
                savings_pct = 0.6  # Assume 60% of requests could use cheaper model
                potential_savings = data["cost"] * savings_pct * 0.5
                recommendations.append({
                    "type": "model_downgrade",
                    "current_model": model,
                    "suggested_model": cheaper[1],
                    "suggested_provider": cheaper[0],
                    "requests": data["requests"],
                    "current_cost": round(data["cost"], 4),
                    "potential_savings": round(potential_savings, 4),
                    "reason": f"{data['requests']} requests on {cost_tier} model — consider routing simple tasks to cheaper model",
                })

        # Suggest caching for repeated high-cost queries
        if data["avg_cost_per_request"] > 0.01 and data["requests"] > 20:
            recommendations.append({
                "type": "enable_caching",
                "model": model,
                "requests": data["requests"],
                "potential_savings": round(data["cost"] * 0.2, 4),
                "reason": f"Enable response caching — repeated queries could save 20%",
            })

        # Suggest speed optimization for slow models
        if data["avg_latency_ms"] > 5000 and data["requests"] > 10:
            recommendations.append({
                "type": "speed_optimization",
                "model": model,
                "current_latency": data["avg_latency_ms"],
                "suggested_model": "groq/llama-3.3-70b-versatile",
                "potential_savings": round(data["cost"] * 0.3, 4),
                "reason": f"High latency ({data['avg_latency_ms']:.0f}ms) — consider Groq for faster inference",
            })

    potential_savings = sum(r["potential_savings"] for r in recommendations)

    return {
        "total_requests": total_requests,
        "total_cost": round(total_cost, 4),
        "by_model": {k: {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in by_model.items()},
        "recommendations": recommendations,
        "potential_savings": round(potential_savings, 4),
        "savings_pct": round(potential_savings / total_cost * 100, 1) if total_cost > 0 else 0,
    }


def _find_cheaper_alternative(model: str) -> tuple[str, str] | None:
    """Find a cheaper alternative for a given model."""
    alternatives = {
        "claude-opus-5-max": ("anthropic", "claude-fable-5"),
        "claude-opus-5-xhigh": ("anthropic", "claude-sonnet-4-20250514"),
        "claude-opus-4-20250514": ("anthropic", "claude-sonnet-4-20250514"),
        "gpt-5.6-sol-max": ("openai", "gpt-4.1-mini"),
        "gpt-4.1": ("openai", "gpt-4.1-mini"),
        "gpt-4o": ("openai", "gpt-4.1-mini"),
        "grok-3": ("xai", "grok-3-mini"),
        "mistral-large-latest": ("mistral", "mistral-small-latest"),
    }
    return alternatives.get(model)
