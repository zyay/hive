"""
Hive API routes for v0.2 features: arena, memory, scheduler, API keys, voice.
"""

import io
import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from hive.core.memory import init_memory, remember, recall, list_memories, forget, clear_memories
from hive.core.scheduler import init_scheduler, create_task, get_tasks, delete_task, toggle_task
from hive.core.api_keys import init_api_keys, create_key, validate_key, list_keys, revoke_key
from hive.core.voice import transcribe, synthesize

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_routes():
    init_memory()
    init_scheduler()
    init_api_keys()


# ---------------------------------------------------------------------------
# Model Arena
# ---------------------------------------------------------------------------

class ArenaRequest(BaseModel):
    prompt: str
    providers: list[str] = []
    system_prompt: str = "You are a helpful assistant."


@router.post("/api/arena")
async def arena(body: ArenaRequest):
    """Run the same prompt on multiple models simultaneously."""
    import asyncio
    from hive.core.llm import chat
    from hive.core.config import settings

    providers = body.providers or [
        name for name, cfg in settings.PROVIDERS.items()
        if cfg["api_key"] or name == "ollama"
    ]

    messages = [
        {"role": "system", "content": body.system_prompt},
        {"role": "user", "content": body.prompt},
    ]

    async def run_one(provider: str):
        cfg = settings.PROVIDERS.get(provider, {})
        try:
            resp = await chat(provider=provider, model=cfg.get("model", ""), messages=messages)
            return {
                "provider": provider,
                "model": resp.model,
                "response": resp.content,
                "latency_ms": resp.latency_ms,
                "tokens_in": resp.tokens_in,
                "tokens_out": resp.tokens_out,
                "cost_usd": resp.cost_usd,
            }
        except Exception as e:
            return {
                "provider": provider,
                "model": cfg.get("model", "unknown"),
                "response": f"Error: {e}",
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0,
            }

    results = await asyncio.gather(*[run_one(p) for p in providers])
    results = sorted(results, key=lambda r: r["latency_ms"])
    return {"results": results}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class RememberRequest(BaseModel):
    agent_id: str
    content: str
    keywords: str = ""
    importance: float = 0.5


@router.post("/api/memory")
async def add_memory(body: RememberRequest):
    remember(body.agent_id, body.content, body.keywords, body.importance)
    return {"status": "stored"}


@router.get("/api/memory/{agent_id}")
async def get_memories(agent_id: str, limit: int = 20):
    return list_memories(agent_id, limit)


@router.get("/api/memory/{agent_id}/recall")
async def recall_memories(agent_id: str, q: str, limit: int = 5):
    return recall(agent_id, q, limit)


@router.delete("/api/memory/{agent_id}/{memory_id}")
async def delete_memory(agent_id: str, memory_id: int):
    ok = forget(agent_id, memory_id)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"deleted": True}


@router.delete("/api/memory/{agent_id}")
async def delete_all_memories(agent_id: str):
    count = clear_memories(agent_id)
    return {"deleted": count}


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    agent_id: str
    prompt: str
    cron: str = "0 * * * *"


@router.post("/api/schedule")
async def add_schedule(body: ScheduleRequest):
    import uuid
    task_id = str(uuid.uuid4())[:8]
    return create_task(task_id, body.agent_id, body.prompt, body.cron)


@router.get("/api/schedule")
async def list_schedules():
    return get_tasks()


@router.delete("/api/schedule/{task_id}")
async def remove_schedule(task_id: str):
    ok = delete_task(task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
    return {"deleted": True}


@router.put("/api/schedule/{task_id}/toggle")
async def toggle_schedule(task_id: str, enabled: bool = True):
    toggle_task(task_id, enabled)
    return {"toggled": True}


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class CreateKeyRequest(BaseModel):
    name: str
    agent_id: Optional[str] = None


@router.post("/api/keys")
async def create_api_key(body: CreateKeyRequest):
    raw_key = create_key(body.name, body.agent_id)
    return {"key": raw_key, "warning": "Save this key — it won't be shown again."}


@router.get("/api/keys")
async def get_keys():
    return list_keys()


@router.delete("/api/keys/{name}")
async def remove_key(name: str):
    ok = revoke_key(name)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"revoked": True}


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

@router.post("/api/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    text = await transcribe(audio_bytes, audio.filename or "audio.wav")
    return {"transcript": text}


@router.post("/api/voice/synthesize")
async def voice_synthesize(text: str, voice: str = "alloy"):
    audio_bytes = await synthesize(text, voice)
    return Response(content=audio_bytes, media_type="audio/mpeg")
