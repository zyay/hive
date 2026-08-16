"""
Streaming responses — SSE (Server-Sent Events) for real-time chat.
"""

import json
import asyncio
import logging
from typing import AsyncGenerator

from hive.core.config import settings
from hive.core.llm import chat_stream
from hive.core.agent import AgentConfig, tool_registry
from hive.core.db import get_agent, create_conversation, save_messages, log_usage

logger = logging.getLogger(__name__)


async def stream_chat_response(
    agent_id: str,
    message: str,
    conversation_id: str = None,
) -> AsyncGenerator[str, None]:
    """
    Stream agent response as SSE events.

    Yields JSON strings in format:
        {"type": "token", "content": "..."}
        {"type": "tool_call", "name": "...", "args": "..."}
        {"type": "tool_result", "name": "...", "result": "..."}
        {"type": "done", "stats": {...}}
        {"type": "error", "message": "..."}
    """
    agent_data = await get_agent(agent_id)
    if not agent_data:
        yield _sse({"type": "error", "message": "Agent not found"})
        return

    config = AgentConfig(
        name=agent_data["name"],
        system_prompt=agent_data["system_prompt"],
        provider=agent_data["provider"],
        model=agent_data["model"],
        temperature=agent_data["temperature"],
        max_tokens=agent_data["max_tokens"],
    )

    # Build conversation
    messages = [{"role": "system", "content": config.system_prompt}]
    if conversation_id:
        from hive.core.db import get_conversation
        conv = await get_conversation(conversation_id)
        if conv:
            messages.extend(conv["messages"])
    messages.append({"role": "user", "content": message})

    # Stream LLM response
    import time
    start = time.time()
    full_response = ""
    tokens_in = 0
    tokens_out = 0

    try:
        async for token in chat_stream(
            provider=config.provider,
            model=config.model,
            messages=messages,
        ):
            full_response += token
            tokens_out += 1
            yield _sse({"type": "token", "content": token})

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield _sse({"type": "error", "message": str(e)})
        return

    latency = (time.time() - start) * 1000

    # Save conversation
    conv_id = conversation_id or await create_conversation(agent_id)
    new_messages = messages + [{"role": "assistant", "content": full_response}]
    await save_messages(conv_id, new_messages)

    # Log usage
    await log_usage(
        agent_id=agent_id,
        provider=config.provider,
        model=config.model or (settings.PROVIDERS.get(config.provider) or {}).get("model", ""),
        tokens_in=tokens_out * 4,  # rough estimate
        tokens_out=tokens_out,
        cost_usd=0,
        latency_ms=latency,
        tool_calls=0,
        llm_calls=1,
    )

    yield _sse({
        "type": "done",
        "conversation_id": conv_id,
        "stats": {
            "llm_calls": 1,
            "tool_executions": 0,
            "tokens_out": tokens_out,
            "latency_ms": round(latency, 1),
        },
    })


def _sse(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"
