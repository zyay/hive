"""
Adaptive Reasoning Engine — auto-adjusts model effort based on task complexity.
Inspired by Claude Opus 5's adaptive reasoning (Aug 2026).
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TaskAnalysis:
    complexity: str  # "simple" | "moderate" | "complex"
    category: str  # "coding" | "reasoning" | "creative" | "chat" | "analysis"
    estimated_tokens: int
    recommended_effort: str  # "low" | "balanced" | "maximum"
    recommended_model: str
    recommended_provider: str


# Complexity indicators
COMPLEX_KEYWORDS = {
    "analyze", "compare", "evaluate", "design", "architect", "optimize",
    "refactor", "debug", "investigate", "diagnose", "synthesize",
    "prove", "derive", "formalize", "benchmark", "profile",
}
SIMPLE_KEYWORDS = {
    "what", "how", "when", "where", "list", "name", "define",
    "translate", "format", "convert", "count", "check",
}
CODING_KEYWORDS = {
    "code", "function", "class", "implement", "fix", "bug", "error",
    "refactor", "test", "deploy", "api", "database", "sql", "python",
    "javascript", "rust", "compile", "runtime", "algorithm",
}
CREATIVE_KEYWORDS = {
    "write", "story", "poem", "essay", "creative", "imagine",
    "draft", "compose", "narrative", "blog", "article",
}


def analyze_task(prompt: str) -> TaskAnalysis:
    """Analyze a prompt and recommend the best model/effort level."""
    words = set(re.findall(r'\w+', prompt.lower()))
    word_count = len(prompt.split())

    # Estimate tokens (~1.3 tokens per word)
    estimated_tokens = int(word_count * 1.3) + 500  # +500 for response

    # Detect category
    if words & CODING_KEYWORDS:
        category = "coding"
    elif words & CREATIVE_KEYWORDS:
        category = "creative"
    elif words & COMPLEX_KEYWORDS:
        category = "analysis"
    elif any(w in prompt.lower() for w in ["why", "explain", "reason", "logic"]):
        category = "reasoning"
    else:
        category = "chat"

    # Detect complexity
    complex_hits = len(words & COMPLEX_KEYWORDS)
    simple_hits = len(words & SIMPLE_KEYWORDS)

    if complex_hits >= 2 or word_count > 200:
        complexity = "complex"
        recommended_effort = "maximum"
    elif complex_hits >= 1 or word_count > 50:
        complexity = "moderate"
        recommended_effort = "balanced"
    else:
        complexity = "simple"
        recommended_effort = "low"

    # Recommend model based on category + complexity
    provider, model = _route(category, complexity, estimated_tokens)

    return TaskAnalysis(
        complexity=complexity,
        category=category,
        estimated_tokens=estimated_tokens,
        recommended_effort=recommended_effort,
        recommended_model=model,
        recommended_provider=provider,
    )


def _route(category: str, complexity: str, tokens: int) -> tuple[str, str]:
    """Route to the best model based on task analysis."""

    # Long context → Gemini 2.5 Pro (2M, free)
    if tokens > 100_000:
        return ("gemini", "gemini-2.5-pro")

    # Coding tasks
    if category == "coding":
        if complexity == "complex":
            return ("anthropic", "claude-opus-5-max")  # Code Arena #1
        return ("anthropic", "claude-sonnet-4-20250514")  # Great coder

    # Creative tasks
    if category == "creative":
        return ("anthropic", "claude-fable-5")  # Best creative balance

    # Analysis / reasoning
    if category in ("analysis", "reasoning"):
        if complexity == "complex":
            return ("anthropic", "claude-opus-5-max")  # Intelligence Index: 63
        if complexity == "moderate":
            return ("anthropic", "claude-sonnet-4-20250514")
        return ("openai", "gpt-4.1-mini")

    # Simple chat
    if complexity == "simple":
        return ("openai", "gpt-4.1-nano")  # Cheapest

    # Default balanced
    return ("anthropic", "claude-fable-5")


def estimate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD for a request."""
    from hive.core.config import settings
    pricing = settings.PRICING.get(model, (0.0, 0.0))
    return (tokens_in * pricing[0] + tokens_out * pricing[1]) / 1_000_000
