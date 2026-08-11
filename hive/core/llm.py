"""
Multi-provider LLM layer — unified interface for 8+ providers.
Adapter pattern: OpenAI-compatible + Anthropic native.
Includes cost tracking and latency measurement.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from hive.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0
    cost_usd: float = 0.0
    tool_calls: list = field(default_factory=list)
    finish_reason: str = ""


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD based on model pricing."""
    pricing = settings.PRICING.get(model, (0.0, 0.0))
    return (tokens_in * pricing[0] + tokens_out * pricing[1]) / 1_000_000


async def chat_openai_compat(
    provider: str,
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Call an OpenAI-compatible API (OpenAI, Groq, Mistral, OpenRouter, Gemini, Ollama, LM Studio)."""
    cfg = settings.PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    # OpenRouter extra headers
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/zyay/hive"
        headers["X-Title"] = "Hive Agent Platform"

    payload = {
        "model": model or cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools

    start = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    latency = (time.time() - start) * 1000

    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage", {})

    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)

    return LLMResponse(
        content=message.get("content", "") or "",
        model=payload["model"],
        provider=provider,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=round(latency, 1),
        cost_usd=round(estimate_cost(payload["model"], tokens_in, tokens_out), 6),
        tool_calls=message.get("tool_calls", []),
        finish_reason=choice.get("finish_reason", ""),
    )


async def chat_anthropic(
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Call Anthropic Claude API (native format, not OpenAI-compatible)."""
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    # Convert OpenAI-style messages to Anthropic format
    system_msg = ""
    conv_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            conv_messages.append(m)

    payload = {
        "model": model or settings.ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": conv_messages,
    }
    if system_msg:
        payload["system"] = system_msg
    if tools:
        # Convert OpenAI tool format to Anthropic tool format
        payload["tools"] = [
            {"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]}
            for t in tools
        ]

    start = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    latency = (time.time() - start) * 1000

    # Extract content
    content_parts = []
    tool_calls = []
    for block in data.get("content", []):
        if block["type"] == "text":
            content_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append({
                "id": block["id"],
                "type": "function",
                "function": {
                    "name": block["name"],
                    "arguments": str(block.get("input", {})),
                }
            })

    usage = data.get("usage", {})
    tokens_in = usage.get("input_tokens", 0)
    tokens_out = usage.get("output_tokens", 0)

    return LLMResponse(
        content="\n".join(content_parts),
        model=payload["model"],
        provider="anthropic",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=round(latency, 1),
        cost_usd=round(estimate_cost(payload["model"], tokens_in, tokens_out), 6),
        tool_calls=tool_calls,
        finish_reason=data.get("stop_reason", ""),
    )


async def chat(
    provider: str = None,
    model: str = None,
    messages: list[dict] = None,
    tools: list[dict] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
) -> LLMResponse:
    """
    Unified chat interface — routes to the correct provider adapter.

    Usage:
        resp = await chat(provider="ollama", model="llama3.3", messages=[...])
        resp = await chat(provider="openai", model="gpt-4.1-mini", messages=[...])
        resp = await chat(provider="anthropic", model="claude-sonnet-4-20250514", messages=[...])
        resp = await chat(provider="deepseek", model="deepseek-chat", messages=[...])
        resp = await chat(provider="xai", model="grok-3-mini", messages=[...])
    """
    provider = provider or settings.DEFAULT_PROVIDER
    if messages is None:
        raise ValueError("messages required")

    cfg = settings.PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(settings.PROVIDERS.keys())}")

    if cfg["type"] == "anthropic":
        return await chat_anthropic(
            model=model, messages=messages, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
        )
    else:
        return await chat_openai_compat(
            provider=provider, model=model, messages=messages, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
        )


async def chat_stream(
    provider: str = None,
    model: str = None,
    messages: list[dict] = None,
    tools: list[dict] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
):
    """
    Streaming chat — yields content chunks as they arrive.
    Only works with OpenAI-compatible providers.
    """
    provider = provider or settings.DEFAULT_PROVIDER
    cfg = settings.PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    if cfg["type"] == "anthropic":
        raise ValueError("Streaming not yet supported for Anthropic. Use chat() instead.")

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    payload = {
        "model": model or cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


async def list_models(provider: str = None) -> list[dict]:
    """List available models for a provider."""
    provider = provider or settings.DEFAULT_PROVIDER
    cfg = settings.PROVIDERS.get(provider)
    if not cfg:
        return []

    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
                resp.raise_for_status()
                return [{"id": m["name"], "provider": provider} for m in resp.json().get("models", [])]
        except Exception:
            return [{"id": settings.OLLAMA_MODEL, "provider": provider}]

    # For OpenAI-compatible, just return the default model
    return [{"id": cfg["model"], "provider": provider}]


def get_providers() -> list[dict]:
    """List all configured providers with their status."""
    result = []
    for name, cfg in settings.PROVIDERS.items():
        has_key = bool(cfg["api_key"]) or name == "ollama"
        result.append({
            "name": name,
            "type": cfg["type"],
            "model": cfg["model"],
            "configured": has_key,
        })
    return result
