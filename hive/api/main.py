"""
Hive API â€” FastAPI backend for agent management, chat, and observability.
v0.2: swarm, arena, memory, scheduler, API keys, voice.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from hive.core.config import settings
from hive.core.agent import AgentConfig, run_agent, tool_registry
from hive.core.llm import get_providers, list_models
from hive.core.db import (
    init_db, create_agent, get_agent, get_all_agents,
    update_agent, delete_agent, create_conversation,
    get_conversation, save_messages, get_usage_summary, log_usage,
)
from hive.core.api_keys import validate_key
from hive.api.routes import router as v2_router, init_routes

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_routes()
    from hive.core.skills import init_skills
    from hive.core.files import init_uploads
    init_skills()
    init_uploads()
    logger.info("Hive v0.3 initialized - all systems ready")
    # Start scheduler loop in background
    from hive.core.scheduler import scheduler_loop
    task = asyncio.create_task(scheduler_loop(interval=60))
    yield
    task.cancel()


app = FastAPI(
    title="Hive",
    description="Self-hosted multi-agent AI platform â€” swarm, arena, memory, voice",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v0.2 routes (arena, memory, scheduler, keys, voice)
app.include_router(v2_router)


# Auth middleware for API key protection
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth for non-API routes and health check
    path = request.url.path
    if not path.startswith("/api/") or path in ("/api/health", "/health"):
        return await call_next(request)

    # Skip auth for read-only endpoints
    if request.method == "GET" and not path.startswith("/api/keys"):
        return await call_next(request)

    # Check API key if provided
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if api_key:
        key_info = validate_key(api_key)
        if not key_info:
            raise HTTPException(401, "Invalid API key")
        request.state.api_key = key_info

    return await call_next(request)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str
    system_prompt: str = "You are a helpful assistant."
    provider: str = "ollama"
    model: str = ""
    tools: list[str] = []
    temperature: float = 0.7
    max_tokens: int = 4096


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    conversation_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Health & info
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/providers")
def providers():
    return get_providers()


@app.get("/api/models/{provider}")
async def models(provider: str):
    return await list_models(provider)


@app.get("/api/models")
def all_models():
    """List all known models with pricing and capabilities."""
    from hive.core.config import settings
    result = []
    for model_name, info in settings.MODEL_INFO.items():
        pricing = settings.PRICING.get(model_name, (0.0, 0.0))
        result.append({
            "model": model_name,
            "context_window": info.get("context", 0),
            "vision": info.get("vision", False),
            "tools": info.get("tools", False),
            "intelligence": info.get("intelligence", 0),
            "speed_tier": info.get("speed_tier", "unknown"),
            "cost_tier": info.get("cost_tier", "unknown"),
            "cost_in_per_m": pricing[0],
            "cost_out_per_m": pricing[1],
        })
    return sorted(result, key=lambda x: -x["intelligence"])


class RouterRequest(BaseModel):
    task: str = ""
    priority: str = "balanced"  # intelligence | speed | budget | balanced
    privacy: bool = False
    context_length: int = 0
    vision: bool = False


@app.post("/api/router")
def route_model(body: RouterRequest):
    """Intelligent model selection â€” recommends the best model for your task."""
    from hive.core.model_router import select_model
    rec = select_model(
        task=body.task,
        priority=body.priority,
        privacy=body.privacy,
        context_length=body.context_length,
        vision=body.vision,
    )
    return {
        "provider": rec.provider,
        "model": rec.model,
        "reason": rec.reason,
        "intelligence": rec.intelligence,
        "speed_tier": rec.speed_tier,
        "cost_tier": rec.cost_tier,
        "estimated_cost_per_1k_tokens": rec.estimated_cost_per_1k,
    }


class CompareRequest(BaseModel):
    models: list[str]


@app.post("/api/compare")
def compare_models(body: CompareRequest):
    """Compare multiple models side-by-side."""
    from hive.core.model_router import compare_models
    return compare_models(body.models)


class AnalyzeRequest(BaseModel):
    prompt: str


@app.post("/api/analyze")
def analyze_task(body: AnalyzeRequest):
    """Analyze a prompt and recommend the best model/effort level."""
    from hive.core.adaptive import analyze_task as do_analyze
    result = do_analyze(body.prompt)
    return {
        "complexity": result.complexity,
        "category": result.category,
        "estimated_tokens": result.estimated_tokens,
        "recommended_effort": result.recommended_effort,
        "recommended_provider": result.recommended_provider,
        "recommended_model": result.recommended_model,
    }


@app.get("/api/costs")
def cost_analysis():
    """Cost optimization analysis â€” usage patterns and savings recommendations."""
    from hive.core.db import get_connection
    from hive.core.cost_optimizer import analyze_usage
    conn = get_connection()
    rows = conn.execute("SELECT * FROM usage_logs ORDER BY timestamp DESC LIMIT 1000").fetchall()
    conn.close()
    logs = [dict(r) for r in rows]
    return analyze_usage(logs)


class BenchmarkRequest(BaseModel):
    models: list[str]  # list of "provider/model" strings
    categories: list[str] = []


@app.post("/api/benchmark")
async def run_benchmark(body: BenchmarkRequest):
    """Run standardized benchmarks on multiple models."""
    from hive.core.arena import benchmark_multiple, format_benchmark_table
    model_pairs = []
    for m in body.models:
        parts = m.split("/", 1)
        if len(parts) == 2:
            model_pairs.append((parts[0], parts[1]))
        else:
            model_pairs.append(("ollama", parts[0]))
    results = await benchmark_multiple(model_pairs, body.categories or None)
    return {
        "results": [
            {
                "model": r.model,
                "provider": r.provider,
                "score": r.score,
                "avg_latency_ms": r.avg_latency_ms,
                "total_cost_usd": r.total_cost_usd,
                "total_tokens": r.total_tokens,
                "num_prompts": r.num_prompts,
            }
            for r in results
        ],
        "table": format_benchmark_table(results),
    }


@app.get("/api/tools")
def tools():
    return [
        {"name": name, "description": schema["function"]["description"]}
        for name, schema in [(t["function"]["name"], t) for t in tool_registry.get_schema()]
    ]


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------

@app.post("/api/agents")
async def create_agent_endpoint(body: AgentCreate):
    config = AgentConfig(**body.model_dump())
    result = await create_agent(config)
    return result


@app.get("/api/agents")
async def list_agents():
    return await get_all_agents()


@app.get("/api/agents/{agent_id}")
async def get_agent_endpoint(agent_id: str):
    agent = await get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.put("/api/agents/{agent_id}")
async def update_agent_endpoint(agent_id: str, body: AgentUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await update_agent(agent_id, updates)
    if not result:
        raise HTTPException(404, "Agent not found")
    return result


@app.delete("/api/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: str):
    ok = await delete_agent(agent_id)
    if not ok:
        raise HTTPException(404, "Agent not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat_endpoint(body: ChatRequest):
    agent_data = await get_agent(body.agent_id)
    if not agent_data:
        raise HTTPException(404, "Agent not found")

    import json
    config = AgentConfig(
        name=agent_data["name"],
        system_prompt=agent_data["system_prompt"],
        provider=agent_data["provider"],
        model=agent_data["model"],
        tools=json.loads(agent_data["tools"]) if isinstance(agent_data["tools"], str) else agent_data["tools"],
        temperature=agent_data["temperature"],
        max_tokens=agent_data["max_tokens"],
    )

    # Load or create conversation
    conv_id = body.conversation_id
    if conv_id:
        conv = await get_conversation(conv_id)
        if not conv:
            raise HTTPException(404, "Conversation not found")
        messages = conv["messages"]
    else:
        conv_id = await create_conversation(body.agent_id)
        messages = []

    # Run agent
    result = await run_agent(config, body.message, messages)

    # Save updated messages
    new_messages = [m.to_dict() for m in result.messages]
    await save_messages(conv_id, new_messages)

    # Log usage
    await log_usage(
        agent_id=body.agent_id,
        provider=config.provider,
        model=config.model or settings.PROVIDERS[config.provider]["model"],
        tokens_in=result.total_tokens_in,
        tokens_out=result.total_tokens_out,
        cost_usd=result.total_cost_usd,
        latency_ms=result.total_latency_ms,
        tool_calls=result.tool_executions,
        llm_calls=result.llm_calls,
    )

    return {
        "response": result.response,
        "conversation_id": conv_id,
        "stats": {
            "llm_calls": result.llm_calls,
            "tool_executions": result.tool_executions,
            "tokens_in": result.total_tokens_in,
            "tokens_out": result.total_tokens_out,
            "cost_usd": result.total_cost_usd,
            "latency_ms": result.total_latency_ms,
            "finish_reason": result.finish_reason,
        },
    }


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@app.get("/api/usage")
async def usage(agent_id: Optional[str] = None, days: int = 7):
    return await get_usage_summary(agent_id=agent_id, days=days)


# ---------------------------------------------------------------------------
# Streaming chat (SSE)
# ---------------------------------------------------------------------------

@app.post("/api/chat/stream")
async def chat_stream_endpoint(body: ChatRequest):
    """Stream agent response as Server-Sent Events."""
    from fastapi.responses import StreamingResponse
    from hive.core.streaming import stream_chat_response
    return StreamingResponse(
        stream_chat_response(body.agent_id, body.message, body.conversation_id),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Vector memory
# ---------------------------------------------------------------------------

class MemoryRequest(BaseModel):
    agent_id: str
    content: str
    metadata: Optional[dict] = None


@app.post("/api/memory/vector")
def vector_remember(body: MemoryRequest):
    """Store a memory using vector embeddings."""
    from hive.core.vector_memory import VectorMemory
    mem = VectorMemory(body.agent_id)
    memory_id = mem.remember(body.content, body.metadata)
    return {"id": memory_id, "status": "stored"}


@app.get("/api/memory/vector/{agent_id}")
def vector_recall(agent_id: str, q: str, limit: int = 5):
    """Recall memories by semantic similarity."""
    from hive.core.vector_memory import VectorMemory
    mem = VectorMemory(agent_id)
    return mem.recall(q, limit)


@app.get("/api/memory/vector/{agent_id}/all")
def vector_list(agent_id: str, limit: int = 50):
    """List all vector memories for an agent."""
    from hive.core.vector_memory import VectorMemory
    mem = VectorMemory(agent_id)
    return {"count": mem.count, "memories": mem.list_all(limit)}


@app.delete("/api/memory/vector/{agent_id}")
def vector_clear(agent_id: str):
    """Clear all vector memories for an agent."""
    from hive.core.vector_memory import VectorMemory
    mem = VectorMemory(agent_id)
    count = mem.clear()
    return {"deleted": count}


# ---------------------------------------------------------------------------
# Auth tokens
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    user_id: str
    role: str = "user"


@app.post("/api/auth/token")
def create_auth_token(body: TokenRequest):
    """Create a JWT authentication token."""
    from hive.core.auth import create_token
    token = create_token(body.user_id, body.role)
    return {"token": token, "type": "Bearer"}


@app.get("/api/auth/verify")
def verify_auth_token(token: str):
    """Verify a JWT token."""
    from hive.core.auth import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return payload


# ---------------------------------------------------------------------------
# Metrics & monitoring
# ---------------------------------------------------------------------------

@app.get("/api/metrics")
def get_metrics():
    """Get application metrics summary."""
    from hive.core.metrics import metrics
    return metrics.summary()


@app.get("/api/metrics/prometheus")
def prometheus_metrics():
    """Export metrics in Prometheus text format."""
    from fastapi.responses import PlainTextResponse
    from hive.core.metrics import metrics
    return PlainTextResponse(metrics.prometheus_format())


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------

@app.post("/api/cron/next")
def cron_next(expression: str):
    """Calculate next run time for a cron expression."""
    from hive.core.cron_parser import next_run_time, describe_cron
    try:
        next_time = next_run_time(expression)
        return {
            "expression": expression,
            "description": describe_cron(expression),
            "next_run": next_time.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# MCP Integrations
# ---------------------------------------------------------------------------

@app.get("/api/integrations")
def list_integrations():
    """List registered MCP integrations and their tools."""
    from hive.core.mcp_integrations import integrations, setup_default_integrations
    setup_default_integrations()
    return {
        name: {"path": conn.server_path, "tools": conn.tools}
        for name, conn in integrations.connections.items()
    }


@app.post("/api/integrations/discover")
async def discover_integrations():
    """Discover tools on all registered MCP servers."""
    from hive.core.mcp_integrations import integrations, setup_default_integrations
    setup_default_integrations()
    results = await integrations.discover_all()
    return results


class IntegrationCallRequest(BaseModel):
    tool: str  # "server__tool" format
    arguments: dict = {}


@app.post("/api/integrations/call")
async def call_integration(body: IntegrationCallRequest):
    """Call a tool on a registered MCP server."""
    from hive.core.mcp_integrations import integrations, setup_default_integrations
    setup_default_integrations()
    result = await integrations.execute(body.tool, body.arguments)
    return {"result": result}


# ---------------------------------------------------------------------------
# Benchmark Suite
# ---------------------------------------------------------------------------

class BenchmarkRequest(BaseModel):
    models: list[str]  # "provider/model" format
    categories: list[str] = []


@app.post("/api/benchmark/run")
async def run_benchmark_suite(body: BenchmarkRequest):
    """Run benchmark suite on multiple models."""
    from hive.core.benchmark_suite import run_comparison, format_comparison_table
    model_pairs = []
    for m in body.models:
        parts = m.split("/", 1)
        if len(parts) == 2:
            model_pairs.append((parts[0], parts[1]))
        else:
            model_pairs.append(("ollama", parts[0]))
    results = await run_comparison(model_pairs, body.categories or None)
    return {
        "results": [
            {
                "provider": r.provider,
                "model": r.model,
                "score": r.score,
                "avg_latency_ms": r.avg_latency_ms,
                "total_cost_usd": r.total_cost_usd,
                "num_prompts": r.num_prompts,
            }
            for r in results
        ],
        "table": format_comparison_table(results),
    }


@app.get("/api/benchmark/categories")
def benchmark_categories():
    """List available benchmark categories and prompt counts."""
    from hive.core.benchmark_suite import BENCHMARKS
    return {
        name: {"prompts": len(prompts), "sample": prompts[0]["prompt"][:80]}
        for name, prompts in BENCHMARKS.items()
    }


# ---------------------------------------------------------------------------
# Multi-user: Auth, Users, Rooms, WebSocket
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserKeyRequest(BaseModel):
    provider: str
    api_key: str
    model: str = ""

class CreateRoomRequest(BaseModel):
    name: str
    type: str = "group"  # 'dm' or 'group'

class InviteRequest(BaseModel):
    member_type: str  # 'user' or 'agent'
    member_id: str

class SendMessageRequest(BaseModel):
    content: str


@app.post("/api/auth/register")
async def register_endpoint(body: RegisterRequest):
    from hive.core.users import register
    from hive.core.auth import create_token
    try:
        user = await register(body.username, body.password, body.display_name)
        token = create_token(user["id"], role="user")
        return {**user, "token": token}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/login")
async def login_endpoint(body: LoginRequest):
    from hive.core.users import login
    result = await login(body.username, body.password)
    if not result:
        raise HTTPException(401, "Invalid credentials")
    return result


@app.get("/api/users/me")
async def get_current_user(user_id: str = None):
    """Get current user profile. Pass user_id as query param (from JWT)."""
    from hive.core.users import get_user
    if not user_id:
        raise HTTPException(400, "user_id required")
    user = await get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@app.get("/api/users")
async def list_users_endpoint():
    from hive.core.users import list_users
    return await list_users()


@app.get("/api/users/keys")
async def get_user_keys(user_id: str):
    from hive.core.user_keys import list_keys
    return await list_keys(user_id)


@app.post("/api/users/keys")
async def set_user_key(user_id: str, body: UserKeyRequest):
    from hive.core.user_keys import set_key
    return await set_key(user_id, body.provider, body.api_key, body.model)


@app.delete("/api/users/keys/{provider}")
async def delete_user_key(user_id: str, provider: str):
    from hive.core.user_keys import delete_key
    ok = await delete_key(user_id, provider)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"deleted": True}


# ── Rooms ──

@app.get("/api/rooms")
async def list_rooms(user_id: str):
    from hive.core.rooms import get_user_rooms
    return await get_user_rooms(user_id)


@app.post("/api/rooms")
async def create_room_endpoint(user_id: str, body: CreateRoomRequest):
    from hive.core.rooms import create_room, create_dm
    if body.type == "dm" and body.name:
        # For DM, name is the other user's ID
        return await create_dm(user_id, body.name)
    return await create_room(body.name, body.type, user_id)


@app.get("/api/rooms/{room_id}")
async def get_room_endpoint(room_id: str):
    from hive.core.rooms import get_room, get_room_members
    room = await get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    members = await get_room_members(room_id)
    return {**room, "members": members}


@app.post("/api/rooms/{room_id}/members")
async def invite_member(room_id: str, body: InviteRequest):
    from hive.core.rooms import add_member, invite_bot
    if body.member_type == "agent":
        ok = await invite_bot(room_id, body.member_id)
    else:
        ok = await add_member(room_id, body.member_type, body.member_id)
    if not ok:
        raise HTTPException(400, "Already a member or invalid")
    return {"invited": True}


@app.delete("/api/rooms/{room_id}/members/{member_type}/{member_id}")
async def remove_member_endpoint(room_id: str, member_type: str, member_id: str):
    from hive.core.rooms import remove_member
    ok = await remove_member(room_id, member_type, member_id)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"removed": True}


@app.get("/api/rooms/{room_id}/messages")
async def get_room_messages(room_id: str, limit: int = 50):
    from hive.core.rooms import get_messages
    return await get_messages(room_id, limit)


@app.post("/api/rooms/{room_id}/messages")
async def send_room_message(room_id: str, user_id: str, body: SendMessageRequest):
    from hive.core.rooms import send_message
    from hive.core.ws import broadcast
    msg = await send_message(room_id, "user", user_id, body.content)
    await broadcast(room_id, {"type": "new_message", "message": msg})
    return msg


# ── WebSocket ──

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    from hive.core.ws import register_connection, unregister_connection, handle_ws_message
    from hive.core.auth import verify_token

    await websocket.accept()

    # Auth via query param
    token = websocket.query_params.get("token", "")
    payload = verify_token(token) if token else None
    user_id = payload["sub"] if payload else "anonymous"

    register_connection(room_id, websocket)
    await websocket.send_text(json.dumps({"type": "connected", "user_id": user_id}))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                await handle_ws_message(room_id, msg, user_id)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
    except Exception:
        pass
    finally:
        unregister_connection(room_id, websocket)


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

# ── Hardware Detection ──

@app.get("/api/hardware")
def hardware_report():
    """Detect system hardware and suggest model sizes."""
    from hive.core.hardware import get_system_report
    return get_system_report()


# ── Agent Skills ──

class SkillRequest(BaseModel):
    name: str
    content: str
    skill_type: str = "prompt"  # 'prompt', 'tool', 'knowledge'


@app.get("/api/agents/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    from hive.core.skills import get_skills
    return await get_skills(agent_id)


@app.post("/api/agents/{agent_id}/skills")
async def add_agent_skill(agent_id: str, body: SkillRequest):
    from hive.core.skills import add_skill
    return await add_skill(agent_id, body.name, body.content, body.skill_type)


@app.delete("/api/agents/{agent_id}/skills/{skill_id}")
async def delete_agent_skill(agent_id: str, skill_id: str):
    from hive.core.skills import delete_skill
    ok = await delete_skill(skill_id)
    if not ok:
        raise HTTPException(404, "Skill not found")
    return {"deleted": True}


@app.post("/api/agents/{agent_id}/upload-md")
async def upload_agent_md(agent_id: str, filename: str, content: str):
    """Upload an MD file as knowledge for an agent."""
    from hive.core.skills import upload_md_file
    return await upload_md_file(agent_id, filename, content)


# ── File Sharing ──

@app.get("/api/rooms/{room_id}/files")
async def list_room_files(room_id: str, limit: int = 50):
    from hive.core.files import get_room_files
    return await get_room_files(room_id, limit)


@app.post("/api/rooms/{room_id}/files")
async def upload_room_file(room_id: str, user_id: str, filename: str, content: str):
    """Upload a file to a room. Content is base64-encoded for JSON transport."""
    import base64
    from hive.core.files import upload_file
    file_bytes = base64.b64decode(content)
    result = await upload_file(room_id, user_id, filename, file_bytes)
    # Broadcast file share event via WebSocket
    from hive.core.ws import broadcast
    await broadcast(room_id, {
        "type": "file_shared",
        "file": {
            "id": result["id"],
            "filename": filename,
            "size": result["size"],
            "uploader_id": user_id,
            "url": result["url"],
        }
    })
    return result


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: str):
    """Download a shared file."""
    from fastapi.responses import FileResponse
    from hive.core.files import get_file, get_file_path
    meta = await get_file(file_id)
    if not meta:
        raise HTTPException(404, "File not found")
    path = get_file_path(file_id)
    if not path:
        raise HTTPException(404, "File not found on disk")
    return FileResponse(path, media_type=meta["mime_type"], filename=meta["filename"])


@app.delete("/api/files/{file_id}")
async def delete_shared_file(file_id: str):
    from hive.core.files import delete_file
    ok = await delete_file(file_id)
    if not ok:
        raise HTTPException(404, "File not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# P2P: Identity, Peers, Encrypted Chat
# ---------------------------------------------------------------------------

class IdentitySetup(BaseModel):
    display_name: str = ""
    password: str = ""

class PeerConnect(BaseModel):
    invite_code: str = ""
    public_signing_key: str = ""
    public_encryption_key: str = ""
    display_name: str = ""

class EncryptedChat(BaseModel):
    recipient_did: str
    content: str


@app.get("/api/p2p/identity")
def get_identity():
    """Get current P2P identity (creates one if none exists)."""
    from hive.core.identity import load_identity, identity_exists
    if not identity_exists():
        return {"status": "no_identity", "message": "No identity configured. POST to /api/p2p/identity to create one."}
    identity = load_identity()
    if not identity:
        return {"status": "error", "message": "Failed to load identity"}
    return {"status": "ok", **identity.to_dict()}


@app.post("/api/p2p/identity")
def create_identity(body: IdentitySetup):
    """Create a new P2P identity."""
    from hive.core.identity import generate_identity, save_identity, identity_exists
    if identity_exists():
        raise HTTPException(400, "Identity already exists. Delete keystore/ to reset.")
    identity = generate_identity(body.display_name)
    save_identity(identity, body.password)
    return identity.to_dict()


@app.get("/api/p2p/peers")
def list_peers():
    """List known P2P peers."""
    from hive.core.db import get_connection
    conn = get_connection()
    rows = conn.execute("SELECT * FROM p2p_peers ORDER BY last_seen DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/p2p/peers/connect")
def connect_peer(body: PeerConnect):
    """Connect to a peer via invite code or public keys."""
    from hive.core.identity import import_peer
    from hive.core.db import get_connection
    import time, json, base64

    if body.invite_code:
        data = json.loads(base64.urlsafe_b64decode(body.invite_code))
        peer = import_peer(data["signing_key"], data["encryption_key"], data.get("name", ""))
    elif body.public_signing_key and body.public_encryption_key:
        peer = import_peer(body.public_signing_key, body.public_encryption_key, body.display_name)
    else:
        raise HTTPException(400, "Provide invite_code or public keys")

    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO p2p_peers (did, peer_id, display_name, address, public_signing_key, public_encryption_key, last_seen, is_online, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (peer["did"], peer["did"][5:21], peer.get("display_name", ""), "", peer.get("public_signing_key", body.public_signing_key), peer.get("public_encryption_key", body.public_encryption_key), time.time(), 1, time.time())
    )
    conn.commit()
    conn.close()
    return {"status": "connected", "did": peer["did"]}


@app.delete("/api/p2p/peers/{did}")
def remove_peer(did: str):
    """Remove a peer."""
    from hive.core.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM p2p_peers WHERE did = ?", (did,))
    conn.commit()
    conn.close()
    return {"deleted": True}


@app.get("/api/p2p/sessions")
def list_sessions():
    """List active encrypted sessions."""
    from hive.core.signal_protocol import SessionManager
    mgr = SessionManager()
    return mgr.list_sessions()


@app.post("/api/p2p/send")
def send_encrypted(body: EncryptedChat):
    """Send an encrypted message to a peer."""
    from hive.core.identity import load_identity
    from hive.core.signal_protocol import SessionManager
    from hive.core.db import get_connection
    from hive.core.relay import relay, RelayMessage
    import uuid, json, time

    identity = load_identity()
    if not identity:
        raise HTTPException(400, "No identity configured")

    conn = get_connection()
    peer = conn.execute("SELECT * FROM p2p_peers WHERE did = ?", (body.recipient_did,)).fetchone()
    if not peer:
        conn.close()
        raise HTTPException(404, "Peer not found")

    mgr = SessionManager()
    session = mgr.get_or_create_session(body.recipient_did, identity.encryption_key, peer["public_encryption_key"])
    encrypted = session.encrypt(body.content)

    msg_id = str(uuid.uuid4())[:12]
    conn.execute(
        "INSERT INTO encrypted_messages (id, sender_did, recipient_did, ciphertext, nonce, counter, message_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (msg_id, identity.did, body.recipient_did, encrypted["ciphertext"], encrypted["nonce"], encrypted["counter"], "text", time.time())
    )
    conn.commit()
    conn.close()

    # Store in relay for offline delivery
    relay.store(RelayMessage(
        id=msg_id, sender_did=identity.did, recipient_did=body.recipient_did,
        ciphertext=encrypted["ciphertext"], nonce=encrypted["nonce"],
        timestamp=time.time(),
    ))

    return {"status": "sent", "id": msg_id, "counter": encrypted["counter"]}


@app.get("/api/p2p/inbox")
def get_inbox(recipient_did: str = ""):
    """Get pending encrypted messages from relay."""
    from hive.core.identity import load_identity
    from hive.core.relay import relay

    if not recipient_did:
        identity = load_identity()
        if identity:
            recipient_did = identity.did

    messages = relay.fetch(recipient_did)
    return {
        "count": len(messages),
        "messages": [m.to_dict() for m in messages],
    }


@app.get("/api/p2p/invite")
def generate_invite():
    """Generate an invite code for this node."""
    from hive.core.identity import load_identity
    identity = load_identity()
    if not identity:
        raise HTTPException(400, "No identity configured")

    import json, base64
    data = json.dumps({
        "did": identity.did,
        "name": identity.display_name,
        "signing_key": identity.public_signing_key_hex,
        "encryption_key": identity.public_encryption_key_hex,
    })
    return {"invite_code": base64.urlsafe_b64encode(data.encode()).decode()}


@app.get("/api/p2p/relay/status")
def relay_status():
    """Get relay mailbox status."""
    from hive.core.relay import relay
    return {"pending": relay.all_pending()}


@app.get("/", response_class=HTMLResponse)
def ui():
    return HTML_PAGE


HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hive</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#09090b;--s1:#18181b;--s2:#1f1f23;--bd:#27272a;--t1:#fafafa;--t2:#a1a1aa;--mt:#52525b;--ac:#6366f1;--ac2:#818cf8;--gn:#22c55e;--rd:#ef4444;--bl:#3b82f6;--am:#f59e0b;--r:8px}
body{font-family:'Inter',-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--t1);height:100vh;display:flex;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
input,textarea,select,button{font-family:inherit;font-size:inherit}
input,textarea,select{padding:8px 12px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--t1);outline:none;width:100%}
input:focus,textarea:focus,select:focus{border-color:var(--ac)}
.btn{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-weight:500;transition:all .15s}
.btn-p{background:var(--ac);color:#fff}.btn-p:hover{background:var(--ac2)}
.btn-o{background:transparent;border:1px solid var(--bd);color:var(--t2)}.btn-o:hover{border-color:var(--t2)}
.btn-d{background:var(--rd);color:#fff}
.btn-s{padding:4px 10px;font-size:12px}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.tag-g{background:#052e16;color:#4ade80}.tag-r{background:#450a0a;color:#f87171}
.tag-b{background:#172554;color:#60a5fa}.tag-gr{background:#27272a;color:#a1a1aa}

/* Auth screen */
#auth{display:flex;align-items:center;justify-content:center;width:100vw;height:100vh}
#auth .card{width:380px;padding:32px;background:var(--s1);border:1px solid var(--bd);border-radius:12px}
#auth h1{font-size:24px;font-weight:700;margin-bottom:4px}
#auth .sub{color:var(--mt);font-size:12px;margin-bottom:24px}
#auth .fg{margin-bottom:12px}
#auth label{display:block;font-size:12px;color:var(--t2);margin-bottom:4px;font-weight:500}
#auth .tabs{display:flex;gap:0;margin-bottom:20px;border-bottom:1px solid var(--bd)}
#auth .tab{padding:8px 16px;cursor:pointer;color:var(--mt);font-size:13px;border-bottom:2px solid transparent}
#auth .tab.active{color:var(--ac);border-bottom-color:var(--ac)}

/* Main app */
#app{display:none;width:100vw;height:100vh}
.sidebar{width:260px;border-right:1px solid var(--bd);display:flex;flex-direction:column;background:var(--s1);flex-shrink:0}
.sb-head{padding:16px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}
.sb-head h2{font-size:15px;font-weight:700}
.sb-user{padding:8px 16px;border-bottom:1px solid var(--bd);font-size:12px;color:var(--t2)}
.sb-nav{padding:8px}
.sb-nav-item{padding:8px 12px;border-radius:6px;cursor:pointer;font-size:13px;color:var(--t2);display:flex;align-items:center;gap:8px}
.sb-nav-item:hover{background:var(--s2);color:var(--t1)}
.sb-nav-item.active{background:var(--ac);color:#fff}
.sb-rooms{flex:1;overflow-y:auto;border-top:1px solid var(--bd);padding:8px}
.sb-rooms-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--mt);padding:8px 12px 4px;font-weight:600}
.room-item{padding:8px 12px;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:2px}
.room-item:hover{background:var(--s2)}
.room-item.active{background:var(--s2);box-shadow:inset 3px 0 0 var(--ac)}
.room-name{font-weight:500}.room-meta{font-size:11px;color:var(--mt)}

/* Main content */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{padding:12px 20px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}
.topbar h3{font-size:15px;font-weight:600}
.content{flex:1;overflow-y:auto;padding:20px}

/* Chat */
.chat-msgs{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:6px}
.msg{max-width:75%;padding:8px 12px;border-radius:10px;font-size:13px;line-height:1.5}
.msg-me{align-self:flex-end;background:var(--ac);color:#fff;border-bottom-right-radius:2px}
.msg-other{align-self:flex-start;background:var(--s1);border:1px solid var(--bd);border-bottom-left-radius:2px}
.msg-bot{align-self:flex-start;background:var(--s2);border:1px solid var(--bd);border-bottom-left-radius:2px}
.msg-file{align-self:flex-start;background:var(--s2);border:1px solid var(--bl);border-radius:8px;padding:8px 12px;font-size:12px}
.msg-sender{font-size:11px;color:var(--mt);margin-bottom:2px}
.chat-bar{padding:12px 20px;border-top:1px solid var(--bd);display:flex;gap:8px;align-items:center}
.chat-bar input{flex:1}

/* Settings */
.settings-section{margin-bottom:24px}
.settings-section h4{font-size:14px;font-weight:600;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--bd)}
.key-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--s2)}

/* Modal */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}
.modal-bg.show{display:flex}
.modal{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:24px;width:480px;max-width:90vw}
.modal h3{font-size:16px;font-weight:600;margin-bottom:16px}
.fg{margin-bottom:12px}
.fg label{display:block;font-size:12px;color:var(--t2);margin-bottom:4px;font-weight:500}

/* Hardware */
.hw-card{background:var(--s2);border-radius:8px;padding:16px;margin-bottom:12px}
.hw-stat{display:flex;justify-content:space-between;padding:4px 0;font-size:13px}
.hw-stat .val{font-weight:600;color:var(--gn)}
.model-sug{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.model-chip{background:var(--s1);border:1px solid var(--bd);border-radius:6px;padding:6px 12px;font-size:12px}
</style>
</head>
<body>

<!-- AUTH SCREEN -->
<div id="auth">
<div class="card">
  <h1>Hive</h1>
  <div class="sub">Multi-agent AI platform</div>
  <div class="tabs">
    <div class="tab active" onclick="showAuthTab('login')">Login</div>
    <div class="tab" onclick="showAuthTab('register')">Register</div>
  </div>
  <div id="auth-login">
    <div class="fg"><label>Username</label><input id="loginUser" placeholder="yourname"></div>
    <div class="fg"><label>Password</label><input id="loginPass" type="password" placeholder="password"></div>
    <button class="btn btn-p" style="width:100%;margin-top:8px" onclick="doLogin()">Login</button>
    <div id="loginErr" style="color:var(--rd);font-size:12px;margin-top:8px"></div>
  </div>
  <div id="auth-register" style="display:none">
    <div class="fg"><label>Username</label><input id="regUser" placeholder="yourname"></div>
    <div class="fg"><label>Display Name</label><input id="regName" placeholder="Your Name"></div>
    <div class="fg"><label>Password</label><input id="regPass" type="password" placeholder="min 4 chars"></div>
    <button class="btn btn-p" style="width:100%;margin-top:8px" onclick="doRegister()">Create Account</button>
    <div id="regErr" style="color:var(--rd);font-size:12px;margin-top:8px"></div>
  </div>
</div>
</div>

<!-- MAIN APP -->
<div id="app">
<div class="sidebar">
  <div class="sb-head"><h2>Hive</h2><button class="btn btn-o btn-s" onclick="doLogout()">Logout</button></div>
  <div class="sb-user" id="sbUser"></div>
  <div class="sb-nav">
    <div class="sb-nav-item active" data-view="chat" onclick="switchView('chat')">Chat</div>
    <div class="sb-nav-item" data-view="agents" onclick="switchView('agents')">Agents</div>
    <div class="sb-nav-item" data-view="settings" onclick="switchView('settings')">Settings</div>
    <div class="sb-nav-item" data-view="hardware" onclick="switchView('hardware')">System</div>
  </div>
  <div class="sb-rooms" id="sbRooms">
    <div class="sb-rooms-label">Rooms</div>
    <div id="roomList"></div>
    <div style="padding:8px"><button class="btn btn-o btn-s" style="width:100%" onclick="showModal('newRoom')">+ New Room</button></div>
  </div>
</div>
<div class="main">
  <!-- Chat view -->
  <div id="view-chat" class="view" style="display:flex;flex-direction:column;flex:1">
    <div class="topbar"><h3 id="chatTitle">Select a room</h3><div id="chatActions"></div></div>
    <div class="chat-msgs" id="chatMsgs"><div style="display:flex;align-items:center;justify-content:center;flex:1;color:var(--mt)">Select or create a room to start chatting</div></div>
    <div class="chat-bar" id="chatBar" style="display:none">
      <input id="chatInput" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendMsg()">
      <button class="btn btn-o btn-s" onclick="showModal('uploadFile')" title="Upload file">File</button>
      <button class="btn btn-o btn-s" onclick="showModal('inviteBot')" title="Invite bot">Bot</button>
      <button class="btn btn-o btn-s" onclick="showModal('inviteUser')" title="Invite user">User</button>
      <button class="btn btn-p" onclick="sendMsg()">Send</button>
    </div>
  </div>
  <!-- Agents view -->
  <div id="view-agents" class="view" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>Agents</h3><button class="btn btn-p btn-s" onclick="showModal('newAgent')">+ New Agent</button></div>
    <div class="content" id="agentsList"></div>
  </div>
  <!-- Settings view -->
  <div id="view-settings" class="view" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>Settings</h3></div>
    <div class="content">
      <div class="settings-section">
        <h4>API Keys</h4>
        <p style="font-size:12px;color:var(--mt);margin-bottom:12px">Add your own API keys. Each user has their own keys — you pay for your own usage.</p>
        <div id="keysList"></div>
        <div style="margin-top:12px;display:flex;gap:8px">
          <select id="keyProvider" style="width:160px"><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="groq">Groq</option><option value="mistral">Mistral</option><option value="openrouter">OpenRouter</option><option value="xai">xAI</option><option value="deepseek">DeepSeek</option><option value="gemini">Gemini</option></select>
          <input id="keyValue" placeholder="sk-..." style="flex:1">
          <button class="btn btn-p btn-s" onclick="saveKey()">Save</button>
        </div>
      </div>
      <div class="settings-section">
        <h4>Profile</h4>
        <div id="profileInfo"></div>
      </div>
    </div>
  </div>
  <!-- Hardware view -->
  <div id="view-hardware" class="view" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>System Info</h3><button class="btn btn-o btn-s" onclick="loadHardware()">Refresh</button></div>
    <div class="content" id="hwContent"></div>
  </div>
</div>
</div>

<!-- MODALS -->
<div class="modal-bg" id="modal-newRoom"><div class="modal">
  <h3>New Room</h3>
  <div class="fg"><label>Room Name</label><input id="nrName" placeholder="General"></div>
  <div class="fg"><label>Type</label><select id="nrType"><option value="group">Group Chat</option><option value="dm">Direct Message</option></select></div>
  <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
    <button class="btn btn-o" onclick="hideModal('newRoom')">Cancel</button>
    <button class="btn btn-p" onclick="createRoom()">Create</button>
  </div>
</div></div>

<div class="modal-bg" id="modal-newAgent"><div class="modal">
  <h3>New Agent</h3>
  <div class="fg"><label>Name</label><input id="naName" placeholder="Research Assistant"></div>
  <div class="fg"><label>System Prompt</label><textarea id="naPrompt" rows="3">You are a helpful assistant.</textarea></div>
  <div class="fg"><label>Provider</label><select id="naProvider"></select></div>
  <div class="fg"><label>Model (empty = default)</label><input id="naModel" placeholder="gpt-4.1-mini"></div>
  <div class="fg"><label>Skills (MD content, optional)</label><textarea id="naSkills" rows="2" placeholder="Additional instructions or knowledge..."></textarea></div>
  <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
    <button class="btn btn-o" onclick="hideModal('newAgent')">Cancel</button>
    <button class="btn btn-p" onclick="createAgent()">Create</button>
  </div>
</div></div>

<div class="modal-bg" id="modal-inviteBot"><div class="modal">
  <h3>Invite Bot to Room</h3>
  <div class="fg"><label>Select Agent</label><select id="ibAgent"></select></div>
  <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
    <button class="btn btn-o" onclick="hideModal('inviteBot')">Cancel</button>
    <button class="btn btn-p" onclick="inviteBot()">Invite</button>
  </div>
</div></div>

<div class="modal-bg" id="modal-inviteUser"><div class="modal">
  <h3>Invite User to Room</h3>
  <div class="fg"><label>Select User</label><select id="iuUser"></select></div>
  <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
    <button class="btn btn-o" onclick="hideModal('inviteUser')">Cancel</button>
    <button class="btn btn-p" onclick="inviteUser()">Invite</button>
  </div>
</div></div>

<div class="modal-bg" id="modal-uploadFile"><div class="modal">
  <h3>Upload File</h3>
  <div class="fg"><label>File</label><input type="file" id="ufFile"></div>
  <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end">
    <button class="btn btn-o" onclick="hideModal('uploadFile')">Cancel</button>
    <button class="btn btn-p" onclick="uploadFile()">Upload</button>
  </div>
</div></div>

<script>
let token=null,userId=null,username=null,curRoom=null,ws=null;
const $=id=>document.getElementById(id);
const api=(url,opts={})=>fetch(url,{...opts,headers:{'Content-Type':'application/json',...opts.headers}}).then(r=>r.json());

// Auth
function showAuthTab(t){document.querySelectorAll('#auth .tab').forEach((el,i)=>el.classList.toggle('active',i===(t==='login'?0:1)));$('auth-login').style.display=t==='login'?'block':'none';$('auth-register').style.display=t==='register'?'block':'none';}
async function doRegister(){const u=$('regUser').value,p=$('regPass').value,n=$('regName').value;if(!u||!p){$('regErr').textContent='Fill all fields';return;}const r=await api('/api/auth/register',{method:'POST',body:JSON.stringify({username:u,password:p,display_name:n})});if(r.token){token=r.token;userId=r.id;username=r.username;enterApp();}else{$('regErr').textContent=r.detail||'Error';}}
async function doLogin(){const u=$('loginUser').value,p=$('loginPass').value;if(!u||!p){$('loginErr').textContent='Fill all fields';return;}const r=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u,password:p})});if(r.token){token=r.token;userId=r.id;username=r.username;enterApp();}else{$('loginErr').textContent=r.detail||'Invalid credentials';}}
function doLogout(){token=null;userId=null;username=null;if(ws)ws.close();$('app').style.display='none';$('auth').style.display='flex';}
function enterApp(){$('auth').style.display='none';$('app').style.display='flex';$('sbUser').textContent=username;loadRooms();loadProviders();loadHardware();}

// Views
function switchView(v){document.querySelectorAll('.view').forEach(el=>el.style.display='none');$('view-'+v).style.display='flex';document.querySelectorAll('.sb-nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===v));if(v==='agents')loadAgents();if(v==='settings')loadKeys();if(v==='hardware')loadHardware();}

// Rooms
async function loadRooms(){const rooms=await api('/api/rooms?user_id='+userId);$('roomList').innerHTML=rooms.map(r=>`<div class="room-item ${curRoom===r.id?'active':''}" onclick="openRoom('${r.id}','${r.name}','${r.type}')"><div class="room-name">${r.name||r.id}</div><div class="room-meta">${r.type}</div></div>`).join('')||'<div style="padding:8px 12px;font-size:12px;color:var(--mt)">No rooms yet</div>';}
async function openRoom(id,name,type){curRoom=id;$('chatTitle').textContent=name;loadRooms();$('chatBar').style.display='flex';connectWS(id);const msgs=await api('/api/rooms/'+id+'/messages');$('chatMsgs').innerHTML=msgs.map(m=>renderMsg(m)).join('')||'<div style="display:flex;align-items:center;justify-content:center;flex:1;color:var(--mt)">No messages yet</div>';$('chatMsgs').scrollTop=$('chatMsgs').scrollHeight;}
function renderMsg(m){const cls=m.sender_type==='agent'?'msg-bot':(m.sender_id===userId?'msg-me':'msg-other');const sender=m.sender_type==='agent'?'bot':'user';return `<div class="msg ${cls}"><div class="msg-sender">${sender}: ${m.sender_id}</div>${esc(m.content)}</div>`;}

// WebSocket
function connectWS(roomId){if(ws)ws.close();ws=new WebSocket('ws://'+location.host+'/ws/'+roomId+'?token='+token);ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.type==='new_message'){$('chatMsgs').innerHTML+=renderMsg(d.message);$('chatMsgs').scrollTop=$('chatMsgs').scrollHeight;}if(d.type==='file_shared'){$('chatMsgs').innerHTML+=`<div class="msg-file">File: <a href="${d.file.url}" style="color:var(--bl)">${d.file.filename}</a> (${d.file.size} bytes)</div>`;$('chatMsgs').scrollTop=$('chatMsgs').scrollHeight;}};}
async function sendMsg(){const inp=$('chatInput');const c=inp.value.trim();if(!c||!curRoom)return;inp.value='';await api('/api/rooms/'+curRoom+'/messages?user_id='+userId,{method:'POST',body:JSON.stringify({content:c})});}

// Agents
async function loadAgents(){const agents=await api('/api/agents');$('agentsList').innerHTML=agents.map(a=>`<div class="hw-card"><div style="display:flex;justify-content:space-between"><strong>${a.name}</strong><span class="tag tag-gr">${a.provider}</span></div><div style="font-size:12px;color:var(--mt);margin-top:4px">${a.system_prompt.substring(0,100)}...</div><div style="margin-top:8px;display:flex;gap:8px"><button class="btn btn-o btn-s" onclick="showAgentSkills('${a.id}')">Skills</button><button class="btn btn-d btn-s" onclick="deleteAgent('${a.id}')">Delete</button></div></div>`).join('')||'<div style="color:var(--mt)">No agents yet. Create one!</div>';}
async function createAgent(){const n=$('naName').value,p=$('naPrompt').value,pr=$('naProvider').value,m=$('naModel').value,sk=$('naSkills').value;if(!n)return;const r=await api('/api/agents',{method:'POST',body:JSON.stringify({name:n,system_prompt:p,provider:pr,model:m})});if(sk&&r.id){await api('/api/agents/'+r.id+'/skills',{method:'POST',body:JSON.stringify({name:'custom',content:sk,skill_type:'prompt'})});}hideModal('newAgent');loadAgents();}
async function deleteAgent(id){await fetch('/api/agents/'+id,{method:'DELETE'});loadAgents();}
async function showAgentSkills(id){const skills=await api('/api/agents/'+id+'/skills');alert('Skills: '+(skills.length?skills.map(s=>s.name+' ('+s.skill_type+')').join(', '):'none'));}

// Keys
async function loadKeys(){const keys=await api('/api/users/keys?user_id='+userId);$('keysList').innerHTML=keys.map(k=>`<div class="key-row"><span>${k.provider} ${k.model?'('+k.model+')':''}</span><button class="btn btn-d btn-s" onclick="deleteKey('${k.provider}')">Remove</button></div>`).join('')||'<div style="color:var(--mt);font-size:13px">No API keys configured. Add one below.</div>';$('profileInfo').innerHTML=`<div style="font-size:13px">Username: <strong>${username}</strong></div><div style="font-size:13px;color:var(--mt)">ID: ${userId}</div>`;}
async function saveKey(){const p=$('keyProvider').value,k=$('keyValue').value;if(!k)return;await api('/api/users/keys?user_id='+userId,{method:'POST',body:JSON.stringify({provider:p,api_key:k})});$('keyValue').value='';loadKeys();}
async function deleteKey(p){await fetch('/api/users/keys/'+p+'?user_id='+userId,{method:'DELETE'});loadKeys();}

// Hardware
async function loadHardware(){const r=await api('/api/hardware');const h=r.hardware;$('hwContent').innerHTML=`<div class="hw-card"><h4 style="margin-bottom:8px">Hardware</h4><div class="hw-stat"><span>OS</span><span class="val">${h.os}</span></div><div class="hw-stat"><span>CPU Cores</span><span class="val">${h.cpu_cores}</span></div><div class="hw-stat"><span>RAM</span><span class="val">${h.ram_gb} GB</span></div><div class="hw-stat"><span>GPU</span><span class="val">${h.gpu}</span></div><div class="hw-stat"><span>VRAM</span><span class="val">${h.gpu_vram_gb} GB</span></div></div><div class="hw-card"><h4 style="margin-bottom:8px">Recommendation</h4><p style="font-size:13px;color:var(--t2)">${r.recommendation}</p><div class="model-sug">${r.suggested_models.map(m=>`<div class="model-chip">${m.size} ${m.quant||''} ${m.fits?'<span class="tag tag-g">fits</span>':'<span class="tag tag-r">wont fit</span>'}</div>`).join('')}</div></div>`;}

// Room/Agent creation helpers
async function createRoom(){const n=$('nrName').value,t=$('nrType').value;if(!n)return;await api('/api/rooms?user_id='+userId,{method:'POST',body:JSON.stringify({name:n,type:t})});hideModal('newRoom');loadRooms();}
async function loadProviders(){const p=await api('/api/providers');const opts=p.map(x=>`<option value="${x.name}">${x.name}${x.configured?'':' (no key)'}</option>`).join('');$('naProvider').innerHTML=opts;}
async function inviteBot(){const a=$('ibAgent').value;if(!a||!curRoom)return;await api('/api/rooms/'+curRoom+'/members',{method:'POST',body:JSON.stringify({member_type:'agent',member_id:a})});hideModal('inviteBot');openRoom(curRoom,$('chatTitle').textContent,'group');}
async function inviteUser(){const u=$('iuUser').value;if(!u||!curRoom)return;await api('/api/rooms/'+curRoom+'/members',{method:'POST',body:JSON.stringify({member_type:'user',member_id:u})});hideModal('inviteUser');openRoom(curRoom,$('chatTitle').textContent,'group');}
async function uploadFile(){const f=$('ufFile').files[0];if(!f||!curRoom)return;const reader=new FileReader();reader.onload=async()=>{const b64=reader.result.split(',')[1];await api('/api/rooms/'+curRoom+'/files?user_id='+userId+'&filename='+f.name,{method:'POST',body:JSON.stringify({content:b64})});hideModal('uploadFile');};reader.readAsDataURL(f);}

// Modals
function showModal(id){$('modal-'+id).classList.add('show');if(id==='inviteBot'){api('/api/agents').then(a=>$('ibAgent').innerHTML=a.map(x=>`<option value="${x.id}">${x.name}</option>`).join(''));}if(id==='inviteUser'){api('/api/users').then(u=>$('iuUser').innerHTML=u.filter(x=>x.id!==userId).map(x=>`<option value="${x.id}">${x.display_name||x.username}</option>`).join('')||'<option value="">No other users</option>');}}
function hideModal(id){$('modal-'+id).classList.remove('show');}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

// Check saved session
if(localStorage.getItem('hive_token')){token=localStorage.getItem('hive_token');userId=localStorage.getItem('hive_user');username=localStorage.getItem('hive_name');enterApp();}
// Save session on login
const origEnter=enterApp;enterApp=function(){localStorage.setItem('hive_token',token);localStorage.setItem('hive_user',userId);localStorage.setItem('hive_name',username);origEnter();};
</script>
</body>
</html>
"""
