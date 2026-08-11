"""
Benchmark suite — automated model evaluation across providers.
Tests models on reasoning, coding, factual, and creative tasks.
"""

import time
import asyncio
import logging
from dataclasses import dataclass, field

from hive.core.llm import chat
from hive.core.config import settings

logger = logging.getLogger(__name__)


# Benchmark datasets
BENCHMARKS = {
    "reasoning": [
        {
            "prompt": "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly? Explain step by step.",
            "expected_keywords": ["no", "not necessarily", "invalid", "fallacy"],
        },
        {
            "prompt": "A train travels at 60 mph for 2.5 hours, then at 80 mph for 1.5 hours. What is the average speed for the entire journey? Show your work.",
            "expected_keywords": ["67.5", "270", "4", "average"],
        },
        {
            "prompt": "Explain the difference between correlation and causation with a concrete real-world example.",
            "expected_keywords": ["correlation", "causation", "example", "does not mean"],
        },
        {
            "prompt": "What is the time complexity of merge sort? Explain why it achieves this complexity.",
            "expected_keywords": ["O(n log n)", "divide", "conquer", "merge"],
        },
        {
            "prompt": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?",
            "expected_keywords": ["0.05", "5 cents", "$0.05"],
        },
    ],
    "coding": [
        {
            "prompt": "Write a Python function that checks if a string is a palindrome. Handle edge cases.",
            "expected_keywords": ["def", "return", "reverse", "=="],
        },
        {
            "prompt": "Write a SQL query to find the second highest salary from an employees table.",
            "expected_keywords": ["SELECT", "ORDER BY", "LIMIT", "salary"],
        },
        {
            "prompt": "Write a function to find all prime numbers up to N using the Sieve of Eratosthenes.",
            "expected_keywords": ["def", "prime", "sieve", "multiple"],
        },
        {
            "prompt": "Write a Python decorator that measures execution time of a function.",
            "expected_keywords": ["def", "wrapper", "time", "decorator"],
        },
        {
            "prompt": "Implement a binary search function in Python that returns the index of the target.",
            "expected_keywords": ["def", "binary", "mid", "return"],
        },
    ],
    "factual": [
        {
            "prompt": "What is the capital of Australia? When was it established as the capital?",
            "expected_keywords": ["canberra", "1927", "1913"],
        },
        {
            "prompt": "Who wrote 'One Hundred Years of Solitude' and in what year was it first published?",
            "expected_keywords": ["garcía", "márquez", "1967"],
        },
        {
            "prompt": "What is the speed of light in a vacuum? Express in both m/s and km/s.",
            "expected_keywords": ["299", "792", "458", "300", "000"],
        },
        {
            "prompt": "What year did the Berlin Wall fall? Name the German chancellor at the time.",
            "expected_keywords": ["1989", "koh"],
        },
        {
            "prompt": "What is the chemical formula for sulfuric acid? What is its common industrial use?",
            "expected_keywords": ["h2so4", "acid", "industrial", "battery", "fertilizer"],
        },
    ],
    "creative": [
        {
            "prompt": "Write a haiku about artificial intelligence.",
            "expected_keywords": [],
            "min_length": 20,
        },
        {
            "prompt": "Explain quantum computing to a 10-year-old using a simple analogy.",
            "expected_keywords": ["like", "imagine", "coin", "both"],
            "min_length": 50,
        },
        {
            "prompt": "Write a short motivational quote about learning to code.",
            "expected_keywords": [],
            "min_length": 15,
        },
    ],
}


@dataclass
class BenchmarkResult:
    provider: str
    model: str
    category: str
    score: float
    avg_latency_ms: float
    total_cost_usd: float
    total_tokens: int
    num_prompts: int
    details: list[dict] = field(default_factory=list)


async def run_benchmark(
    provider: str,
    model: str,
    categories: list[str] = None,
) -> BenchmarkResult:
    """Run benchmark on a single model."""
    if categories is None:
        categories = list(BENCHMARKS.keys())

    all_details = []
    total_score = 0
    total_prompts = 0
    total_latency = 0
    total_cost = 0.0
    total_tokens = 0

    for category in categories:
        prompts = BENCHMARKS.get(category, [])
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
                    min_len = item.get("min_length", 10)
                    score = 1.0 if len(resp.content) >= min_len else 0.5

                total_score += score
                total_latency += latency
                total_cost += resp.cost_usd
                total_tokens += resp.tokens_in + resp.tokens_out

                all_details.append({
                    "category": category,
                    "prompt": item["prompt"][:80],
                    "score": round(score, 2),
                    "latency_ms": round(latency, 1),
                })
                total_prompts += 1

            except Exception as e:
                logger.warning(f"Benchmark failed for {provider}/{model}: {e}")
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


async def run_comparison(
    models: list[tuple[str, str]],
    categories: list[str] = None,
) -> list[BenchmarkResult]:
    """Benchmark multiple models and return sorted results."""
    tasks = [run_benchmark(p, m, categories) for p, m in models]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid = [r for r in results if isinstance(r, BenchmarkResult)]
    return sorted(valid, key=lambda r: -r.score)


def format_comparison_table(results: list[BenchmarkResult]) -> str:
    """Format comparison as a readable table."""
    lines = [
        f"{'#':<3} {'Model':<30} {'Score':>6} {'Latency':>10} {'Cost':>10} {'Prompts':>8}",
        "-" * 72,
    ]
    for i, r in enumerate(results, 1):
        marker = "*" if i == 1 else " "
        lines.append(
            f"{marker}{i:<2} {r.model:<30} {r.score:>5.1%} {r.avg_latency_ms:>8.0f}ms ${r.total_cost_usd:>8.4f} {r.num_prompts:>6}"
        )
    return "\n".join(lines)
