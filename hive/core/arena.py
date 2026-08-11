"""
Arena Benchmarking — test models against standardized benchmarks.
Integrates with Artificial Analysis and Arena.ai ranking concepts.
"""

import time
import asyncio
import logging
from dataclasses import dataclass, field

from hive.core.llm import chat, LLMResponse
from hive.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    model: str
    provider: str
    category: str
    score: float
    avg_latency_ms: float
    total_cost_usd: float
    total_tokens: int
    num_prompts: int
    details: list[dict] = field(default_factory=list)


# Built-in benchmark prompts by category
BENCHMARK_PROMPTS = {
    "reasoning": [
        {"prompt": "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly? Explain your reasoning step by step.", "expected_keywords": ["no", "not necessarily", "invalid"]},
        {"prompt": "A train travels at 60 mph for 2.5 hours, then at 80 mph for 1.5 hours. What is the average speed for the entire journey?", "expected_keywords": ["67.5", "mph"]},
        {"prompt": "Explain the difference between correlation and causation with a real-world example.", "expected_keywords": ["correlation", "causation", "example"]},
    ],
    "coding": [
        {"prompt": "Write a Python function that checks if a string is a palindrome. Include edge cases.", "expected_keywords": ["def", "return", "reverse"]},
        {"prompt": "What is the time complexity of binary search? Explain why.", "expected_keywords": ["O(log n)", "logarithmic", "half"]},
        {"prompt": "Write a SQL query to find the second highest salary from an employees table.", "expected_keywords": ["SELECT", "ORDER BY", "LIMIT"]},
    ],
    "creative": [
        {"prompt": "Write a haiku about artificial intelligence.", "expected_keywords": []},
        {"prompt": "Explain quantum computing to a 10-year-old using an analogy.", "expected_keywords": ["like", "imagine"]},
    ],
    "factual": [
        {"prompt": "What is the capital of Australia? When was it established as the capital?", "expected_keywords": ["canberra"]},
        {"prompt": "Who wrote 'One Hundred Years of Solitude' and in what year was it first published?", "expected_keywords": ["garcía", "márquez", "1967"]},
    ],
}


async def benchmark_model(
    provider: str,
    model: str,
    categories: list[str] = None,
) -> BenchmarkResult:
    """
    Run a model against standardized benchmark prompts.

    Args:
        provider: LLM provider name
        model: Model name
        categories: List of categories to test (default: all)

    Returns:
        BenchmarkResult with scores and metrics
    """
    if categories is None:
        categories = list(BENCHMARK_PROMPTS.keys())

    all_details = []
    total_score = 0
    total_prompts = 0
    total_latency = 0
    total_cost = 0.0
    total_tokens = 0

    for category in categories:
        prompts = BENCHMARK_PROMPTS.get(category, [])
        for item in prompts:
            start = time.time()
            try:
                resp = await chat(
                    provider=provider,
                    model=model,
                    messages=[{"role": "user", "content": item["prompt"]}],
                    max_tokens=1024,
                )
                latency = (time.time() - start) * 1000

                # Score based on keyword matching
                response_lower = resp.content.lower()
                if item["expected_keywords"]:
                    hits = sum(1 for kw in item["expected_keywords"] if kw.lower() in response_lower)
                    score = hits / len(item["expected_keywords"])
                else:
                    score = 0.5 if len(resp.content) > 20 else 0.0  # Creative = just check it responded

                total_score += score
                total_latency += latency
                total_cost += resp.cost_usd
                total_tokens += resp.tokens_in + resp.tokens_out

                all_details.append({
                    "category": category,
                    "prompt": item["prompt"][:80],
                    "score": round(score, 2),
                    "latency_ms": round(latency, 1),
                    "tokens": resp.tokens_in + resp.tokens_out,
                })
                total_prompts += 1

            except Exception as e:
                logger.warning(f"Benchmark failed for {model}: {e}")
                all_details.append({
                    "category": category,
                    "prompt": item["prompt"][:80],
                    "score": 0.0,
                    "error": str(e),
                })
                total_prompts += 1

    avg_score = total_score / total_prompts if total_prompts > 0 else 0
    avg_latency = total_latency / total_prompts if total_prompts > 0 else 0

    return BenchmarkResult(
        model=model,
        provider=provider,
        category=",".join(categories),
        score=round(avg_score, 3),
        avg_latency_ms=round(avg_latency, 1),
        total_cost_usd=round(total_cost, 6),
        total_tokens=total_tokens,
        num_prompts=total_prompts,
        details=all_details,
    )


async def benchmark_multiple(
    models: list[tuple[str, str]],
    categories: list[str] = None,
) -> list[BenchmarkResult]:
    """Benchmark multiple models and return sorted results."""
    tasks = [benchmark_model(p, m, categories) for p, m in models]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid = [r for r in results if isinstance(r, BenchmarkResult)]
    return sorted(valid, key=lambda r: -r.score)


def format_benchmark_table(results: list[BenchmarkResult]) -> str:
    """Format benchmark results as a comparison table."""
    lines = [
        f"{'Model':<30} {'Score':>6} {'Latency':>10} {'Cost':>10} {'Tokens':>8}",
        "─" * 70,
    ]
    for r in results:
        trophy = "🏆" if r == results[0] else "  "
        lines.append(
            f"{trophy} {r.model:<28} {r.score:>5.1%} {r.avg_latency_ms:>8.0f}ms ${r.total_cost_usd:>8.4f} {r.total_tokens:>6}"
        )
    return "\n".join(lines)
