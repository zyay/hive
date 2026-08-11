"""
Model Arena — compare multiple LLMs on the same prompt side-by-side.
Returns responses, latency, and cost for each model.
"""

import asyncio
import logging
from dataclasses import dataclass

from hive.core.llm import chat, LLMResponse
from hive.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ArenaResult:
    provider: str
    model: str
    response: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    finish_reason: str


async def run_arena(
    prompt: str,
    providers: list[str] = None,
    system_prompt: str = "You are a helpful assistant.",
) -> list[ArenaResult]:
    """
    Run the same prompt on multiple providers simultaneously.
    Returns results sorted by latency (fastest first).
    """
    if not providers:
        providers = [
            name for name, cfg in settings.PROVIDERS.items()
            if cfg["api_key"] or name == "ollama"
        ]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    async def run_one(provider: str) -> ArenaResult:
        try:
            cfg = settings.PROVIDERS[provider]
            resp = await chat(
                provider=provider,
                model=cfg["model"],
                messages=messages,
            )
            return ArenaResult(
                provider=provider,
                model=resp.model,
                response=resp.content,
                latency_ms=resp.latency_ms,
                tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                cost_usd=resp.cost_usd,
                finish_reason=resp.finish_reason,
            )
        except Exception as e:
            logger.warning(f"Arena: {provider} failed: {e}")
            return ArenaResult(
                provider=provider,
                model=cfg["model"],
                response=f"Error: {e}",
                latency_ms=0,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0,
                finish_reason="error",
            )

    tasks = [run_one(p) for p in providers]
    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda r: r.latency_ms)


def format_arena_table(results: list[ArenaResult]) -> str:
    """Format arena results as a comparison table."""
    lines = [
        f"{'Provider':<15} {'Model':<25} {'Latency':>10} {'Tokens':>10} {'Cost':>10}",
        "─" * 75,
    ]
    for r in results:
        status = "🏆" if r == results[0] else "  "
        lines.append(
            f"{status} {r.provider:<13} {r.model:<25} {r.latency_ms:>8.0f}ms {r.tokens_in + r.tokens_out:>8} ${r.cost_usd:>8.4f}"
        )
    return "\n".join(lines)
