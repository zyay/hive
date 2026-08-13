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


# Global P2P network instance
p2p_network = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global p2p_network
    init_db()
    init_routes()
    from hive.core.skills import init_skills
    from hive.core.files import init_uploads
    init_skills()
    init_uploads()

    # Auto-create identity if none exists
    from hive.core.identity import identity_exists, generate_identity, save_identity, load_identity
    if not identity_exists():
        identity = generate_identity("Hive User")
        save_identity(identity)
        logger.info(f"Auto-created identity: {identity.did}")
    identity = load_identity()

    # Auto-start P2P network
    from hive.core.p2p_network import P2PNetwork
    p2p_network = P2PNetwork(identity, port=4242)
    p2p_network.start()
    logger.info(f"P2P network started on port 4242, DID: {identity.did}")

    logger.info("Hive v0.3 initialized - all systems ready")
    # Start scheduler loop in background
    from hive.core.scheduler import scheduler_loop
    task = asyncio.create_task(scheduler_loop(interval=60))
    yield
    task.cancel()
    if p2p_network:
        p2p_network.stop()


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


# ---------------------------------------------------------------------------
# Danger Zone — destructive actions
# ---------------------------------------------------------------------------

@app.delete("/api/danger/user")
def delete_user(user_id: str):
    """Permanently delete user account and all associated data."""
    from hive.core.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE sender_id = ?", (user_id,))
    conn.execute("DELETE FROM room_members WHERE member_id = ?", (user_id,))
    conn.execute("DELETE FROM user_api_keys WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "message": "User account and all data permanently deleted"}


@app.delete("/api/danger/agents")
def delete_all_agents():
    """Delete all agents."""
    from hive.core.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM agent_skills")
    conn.execute("DELETE FROM agents")
    conn.execute("DELETE FROM agent_peers")
    conn.commit()
    conn.close()
    return {"deleted": True, "message": "All agents deleted"}


@app.delete("/api/danger/rooms")
def delete_all_rooms():
    """Delete all rooms and messages."""
    from hive.core.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM encrypted_messages")
    conn.execute("DELETE FROM room_members")
    conn.execute("DELETE FROM rooms")
    conn.commit()
    conn.close()
    return {"deleted": True, "message": "All rooms and messages deleted"}


@app.delete("/api/danger/keys")
def delete_all_keys(user_id: str):
    """Delete all API keys for a user."""
    from hive.core.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM user_api_keys WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "message": "All API keys deleted"}


@app.delete("/api/danger/identity")
def delete_identity():
    """Delete P2P identity (keystore)."""
    import shutil
    from hive.core.identity import KEYSTORE_DIR
    if KEYSTORE_DIR.exists():
        shutil.rmtree(KEYSTORE_DIR)
    return {"deleted": True, "message": "P2P identity deleted. Restart to generate new identity."}


@app.delete("/api/danger/sessions")
def delete_all_sessions():
    """Delete all Signal Protocol sessions."""
    import os
    if os.path.exists("sessions.json"):
        os.remove("sessions.json")
    return {"deleted": True, "message": "All encrypted sessions deleted"}


@app.delete("/api/danger/relay")
def clear_relay():
    """Clear all relay mailboxes."""
    import shutil
    from hive.core.relay import RELAY_DIR
    if RELAY_DIR.exists():
        shutil.rmtree(RELAY_DIR)
        RELAY_DIR.mkdir(exist_ok=True)
    return {"deleted": True, "message": "All relay mailboxes cleared"}


@app.delete("/api/danger/everything")
def delete_everything():
    """Nuclear option — delete everything: DB, keystore, sessions, relay, uploads."""
    import shutil, os
    from hive.core.db import get_connection
    from hive.core.identity import KEYSTORE_DIR
    from hive.core.relay import RELAY_DIR

    # Clear DB
    conn = get_connection()
    for table in ["messages", "encrypted_messages", "room_members", "rooms",
                  "user_api_keys", "agent_skills", "agents", "agent_peers",
                  "p2p_sessions", "p2p_peers", "shared_files", "users"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

    # Delete files
    for path in [KEYSTORE_DIR, RELAY_DIR, Path("sessions.json"), Path("hive.db"), Path("uploads")]:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
        except Exception:
            pass

    return {"deleted": True, "message": "EVERYTHING deleted. Full reset. Restart required."}


# ---------------------------------------------------------------------------
# Network & P2P status
# ---------------------------------------------------------------------------

@app.get("/api/network/status")
def network_status():
    """Get P2P network status, identity, and connected peers."""
    from hive.core.identity import load_identity
    identity = load_identity()
    if not p2p_network:
        return {"status": "stopped", "identity": None, "peers": []}
    peers = p2p_network.get_online_peers()
    return {
        "status": "running",
        "port": p2p_network.port,
        "identity": identity.to_dict() if identity else None,
        "peers": [p.to_dict() for p in peers],
        "total_peers": len(p2p_network.peers),
        "invite_code": p2p_network.generate_invite_code(),
    }


@app.post("/api/network/connect")
def connect_peer(invite_code: str):
    """Connect to a peer via invite code."""
    if not p2p_network:
        raise HTTPException(503, "P2P network not running")
    peer = p2p_network.connect_from_invite(invite_code)
    if not peer:
        raise HTTPException(400, "Failed to connect — invalid invite code")
    return peer.to_dict()


@app.get("/api/network/peers")
def list_network_peers():
    """List all known P2P peers."""
    if not p2p_network:
        return []
    return [p.to_dict() for p in p2p_network.peers.values()]


@app.get("/api/messages/search")
def search_messages(room_id: str, q: str, limit: int = 20):
    """Search messages in a room."""
    from hive.core.db import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE room_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
        (room_id, f"%{q}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #ffffff; --bg-subtle: #f9fafb; --bg-muted: #f3f4f6;
  --border: #e5e7eb; --border-subtle: #f3f4f6;
  --text: #111827; --text-secondary: #6b7280; --text-muted: #9ca3af;
  --accent: #6366f1; --accent-light: #eef2ff; --accent-dark: #4f46e5;
  --success: #10b981; --error: #ef4444; --warning: #f59e0b;
  --radius: 8px; --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05);
  --transition: 150ms cubic-bezier(0.4, 0, 0.2, 1);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); height: 100vh; display: flex; font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; }
input, textarea, select, button { font-family: inherit; font-size: inherit; }
input, textarea, select { padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg); color: var(--text); outline: none; width: 100%; transition: border-color var(--transition); }
input:focus, textarea:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }
button { cursor: pointer; }
.btn { padding: 8px 16px; border: none; border-radius: var(--radius); font-weight: 500; transition: all var(--transition); display: inline-flex; align-items: center; gap: 6px; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-dark); }
.btn-secondary { background: var(--bg); border: 1px solid var(--border); color: var(--text-secondary); }
.btn-secondary:hover { background: var(--bg-subtle); color: var(--text); }
.btn-danger { background: var(--error); color: #fff; }
.btn-danger:hover { background: #dc2626; }
.btn-ghost { background: transparent; color: var(--text-secondary); padding: 6px 10px; }
.btn-ghost:hover { background: var(--bg-muted); color: var(--text); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 100px; font-size: 11px; font-weight: 600; }
.badge-success { background: #d1fae5; color: #065f46; }
.badge-error { background: #fee2e2; color: #991b1b; }
.badge-info { background: var(--accent-light); color: var(--accent-dark); }
.badge-neutral { background: var(--bg-muted); color: var(--text-secondary); }

/* Auth */
#auth { display: flex; align-items: center; justify-content: center; width: 100vw; height: 100vh; background: var(--bg-subtle); }
.auth-card { width: 400px; padding: 40px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); }
.auth-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.auth-logo svg { color: var(--accent); }
.auth-logo h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
.auth-sub { color: var(--text-muted); font-size: 13px; margin-bottom: 28px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px; }
.auth-tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid var(--border); }
.auth-tab { padding: 10px 20px; cursor: pointer; color: var(--text-muted); font-size: 13px; font-weight: 500; border-bottom: 2px solid transparent; transition: all var(--transition); }
.auth-tab:hover { color: var(--text-secondary); }
.auth-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.auth-error { color: var(--error); font-size: 12px; margin-top: 10px; }

/* App layout */
#app { display: none; width: 100vw; height: 100vh; }
.sidebar { width: 260px; border-right: 1px solid var(--border); display: flex; flex-direction: column; background: var(--bg); }
.sidebar-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.sidebar-header h2 { font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 8px; letter-spacing: -0.01em; }
.user-info { padding: 12px 20px; border-bottom: 1px solid var(--border); font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 10px; }
.user-avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--accent-light); color: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.nav { padding: 8px; }
.nav-item { padding: 8px 12px; border-radius: var(--radius); cursor: pointer; font-size: 13px; color: var(--text-secondary); margin-bottom: 2px; display: flex; align-items: center; gap: 10px; transition: all var(--transition); font-weight: 500; }
.nav-item:hover { background: var(--bg-subtle); color: var(--text); }
.nav-item.active { background: var(--accent-light); color: var(--accent-dark); }
.nav-item svg { opacity: 0.7; }
.nav-item.active svg { opacity: 1; }
.rooms-section { flex: 1; overflow-y: auto; border-top: 1px solid var(--border); padding: 8px; }
.rooms-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); padding: 8px 12px 6px; font-weight: 600; }
.room-item { padding: 10px 12px; border-radius: var(--radius); cursor: pointer; font-size: 13px; margin-bottom: 2px; position: relative; transition: all var(--transition); }
.room-item:hover { background: var(--bg-subtle); }
.room-item.active { background: var(--accent-light); }
.room-item .room-name { font-weight: 500; color: var(--text); }
.room-item .room-type { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.room-item .unread-badge { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: var(--accent); color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 100px; font-weight: 600; }

/* Main content */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: var(--bg); }
.topbar { padding: 14px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.topbar h3 { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }
.content { flex: 1; overflow-y: auto; padding: 24px; }

/* Chat */
.messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 4px; }
.message { max-width: 70%; padding: 10px 14px; border-radius: 16px; font-size: 13px; line-height: 1.5; position: relative; }
.message-sent { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
.message-received { align-self: flex-start; background: var(--bg-muted); color: var(--text); border-bottom-left-radius: 4px; }
.message .sender { font-size: 11px; font-weight: 600; margin-bottom: 3px; opacity: 0.7; }
.message .time { font-size: 10px; opacity: 0.5; margin-top: 4px; }
.typing-indicator { align-self: flex-start; color: var(--text-muted); font-size: 12px; font-style: italic; padding: 6px 14px; }
.chat-input-bar { padding: 16px 24px; border-top: 1px solid var(--border); display: flex; gap: 8px; align-items: center; background: var(--bg); }
.chat-input-bar input { flex: 1; border-radius: 100px; padding: 10px 18px; background: var(--bg-subtle); border: 1px solid var(--border); }
.search-bar { padding: 10px 24px; border-bottom: 1px solid var(--border); display: none; background: var(--bg-subtle); }
.search-bar input { background: var(--bg); font-size: 13px; border-radius: 100px; }
.conn-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.conn-dot.online { background: var(--success); }
.conn-dot.offline { background: var(--text-muted); }

/* Cards */
.card { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; margin-bottom: 16px; transition: box-shadow var(--transition); }
.card:hover { box-shadow: var(--shadow-sm); }
.card h4 { font-size: 14px; font-weight: 600; margin-bottom: 12px; letter-spacing: -0.01em; }
.stat-row { display: flex; justify-content: space-between; padding: 8px 0; font-size: 13px; border-bottom: 1px solid var(--border-subtle); }
.stat-row:last-child { border: none; }
.stat-row .value { font-weight: 600; color: var(--accent); }
.peer-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.peer-row:last-child { border: none; }

/* Modal */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.3); backdrop-filter: blur(4px); z-index: 100; align-items: center; justify-content: center; }
.modal-overlay.show { display: flex; }
.modal { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px; width: 440px; max-width: 90vw; box-shadow: var(--shadow-lg); }
.modal h3 { font-size: 17px; font-weight: 600; margin-bottom: 20px; letter-spacing: -0.01em; }

/* Tutorial */
#tut { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); backdrop-filter: blur(8px); z-index: 300; align-items: center; justify-content: center; }
#tut .tut-box { background: var(--bg); border: 1px solid var(--border); border-radius: 16px; padding: 40px; width: 520px; max-width: 92vw; box-shadow: var(--shadow-lg); text-align: center; }
#tut .tut-icon { color: var(--accent); margin-bottom: 16px; }
#tut h2 { font-size: 20px; font-weight: 700; margin-bottom: 10px; letter-spacing: -0.02em; }
#tut p { font-size: 14px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 20px; }
#tut .tut-info { background: var(--bg-subtle); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; font-size: 13px; color: var(--text-secondary); line-height: 1.8; text-align: left; }
#tut .tut-dots { display: flex; gap: 6px; justify-content: center; margin-top: 24px; }
#tut .tut-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); transition: background var(--transition); }
#tut .tut-dot.active { background: var(--accent); }

/* Danger zone */
.danger-item { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 8px; transition: all var(--transition); }
.danger-item:hover { border-color: var(--error); }
.danger-item.critical { border-color: var(--error); background: #fef2f2; }
.danger-item .danger-title { font-size: 13px; font-weight: 500; }
.danger-item .danger-desc { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* Empty state */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; color: var(--text-muted); gap: 8px; }
.empty-state svg { opacity: 0.3; }
</style>
</head>
<body>

<!-- AUTH -->
<div id="auth">
<div class="auth-card">
  <div class="auth-logo">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    <h1>Hive</h1>
  </div>
  <div class="auth-sub">Decentralized, end-to-end encrypted AI messenger</div>
  <div class="auth-tabs">
    <div class="auth-tab active" onclick="authTab(0)">Sign in</div>
    <div class="auth-tab" onclick="authTab(1)">Create account</div>
  </div>
  <div id="aLogin">
    <div class="form-group"><label>Username</label><input id="lU" placeholder="Enter username"></div>
    <div class="form-group"><label>Password</label><input id="lP" type="password" placeholder="Enter password"></div>
    <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:4px" onclick="doLogin()">Sign in</button>
    <div id="lErr" class="auth-error"></div>
  </div>
  <div id="aReg" style="display:none">
    <div class="form-group"><label>Username</label><input id="rU" placeholder="Choose username"></div>
    <div class="form-group"><label>Display name</label><input id="rN" placeholder="Your name"></div>
    <div class="form-group"><label>Password</label><input id="rP" type="password" placeholder="Min 4 characters"></div>
    <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:4px" onclick="doReg()">Create account</button>
    <div id="rErr" class="auth-error"></div>
  </div>
</div>
</div>

<!-- APP -->
<div id="app">
<div class="sidebar">
  <div class="sidebar-header">
    <h2><span id="connDot" class="conn-dot offline"></span>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    Hive</h2>
    <button class="btn btn-ghost btn-sm" onclick="logout()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
    </button>
  </div>
  <div class="user-info">
    <div class="user-avatar" id="userAvatar"></div>
    <span id="sbU"></span>
  </div>
  <div class="nav">
    <div class="nav-item active" data-v="chat" onclick="view('chat')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> Chat</div>
    <div class="nav-item" data-v="agents" onclick="view('agents')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg> Agents</div>
    <div class="nav-item" data-v="network" onclick="view('network')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10"/></svg> Network</div>
    <div class="nav-item" data-v="settings" onclick="view('settings')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Settings</div>
    <div class="nav-item" data-v="system" onclick="view('system')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> System</div>
  </div>
  <div class="rooms-section">
    <div class="rooms-label">Rooms</div>
    <div id="rList"></div>
    <div style="padding:8px"><button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center" onclick="modal('mRoom')">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> New room</button></div>
  </div>
</div>

<div class="main">
  <!-- Chat -->
  <div id="vChat" style="display:flex;flex-direction:column;flex:1">
    <div class="topbar">
      <h3 id="cTitle">Select a room</h3>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="toggleSearch()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Search</button>
      </div>
    </div>
    <div class="search-bar" id="searchBar"><input id="searchIn" placeholder="Search messages..." oninput="doSearch()"></div>
    <div class="messages" id="cMsgs">
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span>Create or select a room to start chatting</span>
      </div>
    </div>
    <div id="typingArea"></div>
    <div class="chat-input-bar" id="cBar" style="display:none">
      <button class="btn btn-ghost btn-sm" onclick="modal('mFile')" title="Upload file">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg></button>
      <input id="cIn" placeholder="Type a message..." onkeydown="if(event.key==='Enter')send()" oninput="sendTyping()">
      <button class="btn btn-ghost btn-sm" onclick="modal('mBot')" title="Invite bot">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/></svg></button>
      <button class="btn btn-ghost btn-sm" onclick="modal('mUser')" title="Invite user">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg></button>
      <button class="btn btn-primary btn-sm" onclick="send()">Send</button>
    </div>
  </div>
  <!-- Agents -->
  <div id="vAgents" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>Agents</h3><button class="btn btn-primary btn-sm" onclick="modal('mAgent')">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> New agent</button></div>
    <div class="content" id="aList"></div>
  </div>
  <!-- Network -->
  <div id="vNetwork" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>Network</h3><button class="btn btn-secondary btn-sm" onclick="loadNet()">Refresh</button></div>
    <div class="content" id="netC"></div>
  </div>
  <!-- Settings -->
  <div id="vSettings" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>Settings</h3></div>
    <div class="content">
      <div style="margin-bottom:32px">
        <h4 style="font-size:15px;font-weight:600;margin-bottom:4px">API Keys</h4>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">Your keys, your usage. Stored encrypted locally.</p>
        <div id="kList"></div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <select id="kProv" style="width:160px"><option>openai</option><option>anthropic</option><option>groq</option><option>mistral</option><option>openrouter</option><option>xai</option><option>deepseek</option><option>gemini</option></select>
          <input id="kVal" placeholder="sk-..." style="flex:1">
          <button class="btn btn-primary btn-sm" onclick="saveKey()">Save key</button>
        </div>
      </div>
      <div style="margin-bottom:32px">
        <h4 style="font-size:15px;font-weight:600;margin-bottom:4px">Profile</h4>
        <div id="pInfo" style="font-size:13px;color:var(--text-secondary)"></div>
      </div>
      <div>
        <h4 style="font-size:15px;font-weight:600;margin-bottom:4px;color:var(--error)">Danger Zone</h4>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">Irreversible actions. Proceed with caution.</p>
        <div class="danger-item"><div><div class="danger-title">Delete API Keys</div><div class="danger-desc">Remove all stored API keys</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('keys','Delete all API keys?')">Delete</button></div>
        <div class="danger-item"><div><div class="danger-title">Delete Agents</div><div class="danger-desc">Remove all AI agents and skills</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('agents','Delete ALL agents?')">Delete</button></div>
        <div class="danger-item"><div><div class="danger-title">Delete Rooms</div><div class="danger-desc">Remove all rooms and messages</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('rooms','Delete ALL rooms?')">Delete</button></div>
        <div class="danger-item"><div><div class="danger-title">Reset Identity</div><div class="danger-desc">Delete P2P cryptographic identity</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('identity','Reset identity?')">Reset</button></div>
        <div class="danger-item critical"><div><div class="danger-title" style="color:var(--error)">Delete Everything</div><div class="danger-desc">Nuclear reset — all data, identity, keys</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('everything','DELETE EVERYTHING?')">Reset All</button></div>
        <div class="danger-item critical"><div><div class="danger-title" style="color:var(--error)">Delete Account</div><div class="danger-desc">Permanently delete your account</div></div><button class="btn btn-danger btn-sm" onclick="dangerAction('user','DELETE ACCOUNT?')">Delete</button></div>
        <div id="dangerMsg" style="margin-top:8px;font-size:12px"></div>
      </div>
    </div>
  </div>
  <!-- System -->
  <div id="vSystem" style="display:none;flex-direction:column;flex:1">
    <div class="topbar"><h3>System</h3><button class="btn btn-secondary btn-sm" onclick="loadHW()">Refresh</button></div>
    <div class="content" id="hwC"></div>
  </div>
</div>
</div>

<!-- Modals -->
<div class="modal-overlay" id="mRoom"><div class="modal">
  <h3>New Room</h3>
  <div class="form-group"><label>Name</label><input id="nrN" placeholder="General"></div>
  <div class="form-group"><label>Type</label><select id="nrT"><option value="group">Group chat</option><option value="dm">Direct message</option></select></div>
  <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
    <button class="btn btn-secondary" onclick="hideM('mRoom')">Cancel</button>
    <button class="btn btn-primary" onclick="mkRoom()">Create room</button>
  </div>
</div></div>
<div class="modal-overlay" id="mAgent"><div class="modal">
  <h3>New Agent</h3>
  <div class="form-group"><label>Name</label><input id="naN" placeholder="Research Assistant"></div>
  <div class="form-group"><label>System prompt</label><textarea id="naP" rows="3">You are a helpful assistant.</textarea></div>
  <div class="form-group"><label>Provider</label><select id="naPr"></select></div>
  <div class="form-group"><label>Model</label><input id="naM" placeholder="Leave empty for default"></div>
  <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
    <button class="btn btn-secondary" onclick="hideM('mAgent')">Cancel</button>
    <button class="btn btn-primary" onclick="mkAgent()">Create agent</button>
  </div>
</div></div>
<div class="modal-overlay" id="mBot"><div class="modal">
  <h3>Invite Bot</h3>
  <div class="form-group"><label>Agent</label><select id="ibA"></select></div>
  <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
    <button class="btn btn-secondary" onclick="hideM('mBot')">Cancel</button>
    <button class="btn btn-primary" onclick="invBot()">Invite</button>
  </div>
</div></div>
<div class="modal-overlay" id="mUser"><div class="modal">
  <h3>Invite User</h3>
  <div class="form-group"><label>User</label><select id="iuU"></select></div>
  <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
    <button class="btn btn-secondary" onclick="hideM('mUser')">Cancel</button>
    <button class="btn btn-primary" onclick="invUser()">Invite</button>
  </div>
</div></div>
<div class="modal-overlay" id="mFile"><div class="modal">
  <h3>Upload File</h3>
  <div class="form-group"><label>Choose file</label><input type="file" id="fileIn"></div>
  <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
    <button class="btn btn-secondary" onclick="hideM('mFile')">Cancel</button>
    <button class="btn btn-primary" onclick="uploadFile()">Upload</button>
  </div>
</div></div>

<!-- Tutorial -->
<div id="tut"><div class="tut-box">
  <div class="tut-icon" id="tIcon"></div>
  <h2 id="tTitle"></h2>
  <p id="tText"></p>
  <div class="tut-info" id="tInfo"></div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:24px">
    <div class="tut-dots" id="tDots"></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-secondary" onclick="skipTut()">Skip</button>
      <button class="btn btn-secondary" id="tPrev" onclick="tutBack()" style="display:none">Back</button>
      <button class="btn btn-primary" id="tNext" onclick="tutNext()">Next</button>
    </div>
  </div>
</div></div>

<script>
var T=null,U=null,N=null,room=null,ws=null,wsRetry=0,unread={},typingTimer=null;
var $=function(id){return document.getElementById(id)};
var api=function(u,o){o=o||{};o.headers=o.headers||{};o.headers['Content-Type']='application/json';return fetch(u,o).then(function(r){return r.json()})};

function authTab(i){document.querySelectorAll('.auth-tab').forEach(function(e,j){e.classList.toggle('active',j===i)});$('aLogin').style.display=i?'none':'block';$('aReg').style.display=i?'block':'none'}
function doReg(){var u=$('rU').value,p=$('rP').value,n=$('rN').value;if(!u||!p){$('rErr').textContent='Please fill all fields';return}api('/api/auth/register',{method:'POST',body:JSON.stringify({username:u,password:p,display_name:n})}).then(function(r){if(r.token){T=r.token;U=r.id;N=r.username;enter()}else{$('rErr').textContent=r.detail||'Error'}})}
function doLogin(){var u=$('lU').value,p=$('lP').value;if(!u||!p){$('lErr').textContent='Please fill all fields';return}api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u,password:p})}).then(function(r){if(r.token){T=r.token;U=r.id;N=r.username;enter()}else{$('lErr').textContent=r.detail||'Invalid credentials'}})}
function logout(){T=null;U=null;N=null;if(ws)ws.close();$('app').style.display='none';$('auth').style.display='flex'}

function enter(){localStorage.setItem('ht',T);localStorage.setItem('hu',U);localStorage.setItem('hn',N);$('auth').style.display='none';$('app').style.display='flex';$('sbU').textContent=N;$('userAvatar').textContent=N.charAt(0).toUpperCase();loadRooms();loadProv();loadHW();loadNet();if(!localStorage.getItem('htut'))setTimeout(showTut,600)}

function view(v){document.querySelectorAll('[id^=v]').forEach(function(e){e.style.display='none'});var el=$('v'+v.charAt(0).toUpperCase()+v.slice(1));if(el)el.style.display='flex';document.querySelectorAll('.nav-item').forEach(function(e){e.classList.toggle('active',e.dataset.v===v)});if(v==='agents')loadAgents();if(v==='settings')loadKeys();if(v==='system')loadHW();if(v==='network')loadNet()}

function loadRooms(){api('/api/rooms?user_id='+U).then(function(r){$('rList').innerHTML=r.map(function(x){var b=unread[x.id]?'<span class="unread-badge">'+unread[x.id]+'</span>':'';return '<div class="room-item'+(room===x.id?' active':'')+'" onclick="openR(\''+x.id+'\',\''+(x.name||x.id)+'\')"><div class="room-name">'+(x.name||x.id)+'</div><div class="room-type">'+x.type+'</div>'+b+'</div>'}).join('')||'<div style="padding:12px;font-size:13px;color:var(--text-muted)">No rooms yet</div>'})}

function openR(id,name){room=id;unread[id]=0;$('cTitle').textContent=name;loadRooms();$('cBar').style.display='flex';connectWS(id);api('/api/rooms/'+id+'/messages').then(function(m){$('cMsgs').innerHTML=m.map(function(x){var c=x.sender_id===U?'message-sent':'message-received';var t=new Date(x.created_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});return '<div class="message '+c+'"><div class="sender">'+(x.sender_type==='agent'?'Bot':'You')+'</div>'+esc(x.content)+'<div class="time">'+t+'</div></div>'}).join('')||'<div class="empty-state"><span>No messages yet</span></div>';$('cMsgs').scrollTop=$('cMsgs').scrollHeight})}

function connectWS(id){if(ws)ws.close();ws=new WebSocket('ws://'+location.host+'/ws/'+id+'?token='+T);ws.onopen=function(){wsRetry=0;$('connDot').className='conn-dot online'};ws.onclose=function(){$('connDot').className='conn-dot offline';if(T&&room){var d=Math.min(1000*Math.pow(2,wsRetry),30000);wsRetry++;setTimeout(function(){if(room)connectWS(room)},d)}};ws.onmessage=function(e){var d=JSON.parse(e.data);if(d.type==='new_message'){if(d.message.sender_id!==U&&room!==id){unread[id]=(unread[id]||0)+1;loadRooms();beep()}var c=d.message.sender_id===U?'message-sent':'message-received';var t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});$('cMsgs').innerHTML+='<div class="message '+c+'"><div class="sender">'+(d.message.sender_type==='agent'?'Bot':'You')+'</div>'+esc(d.message.content)+'<div class="time">'+t+'</div></div>';$('cMsgs').scrollTop=$('cMsgs').scrollHeight}else if(d.type==='typing'&&d.user_id!==U){$('typingArea').innerHTML='<div class="typing-indicator">'+(d.is_bot?'Bot':'Someone')+' is typing...</div>';clearTimeout(typingTimer);typingTimer=setTimeout(function(){$('typingArea').innerHTML=''},3000)}}}

function send(){var v=$('cIn').value.trim();if(!v||!room)return;$('cIn').value='';api('/api/rooms/'+room+'/messages?user_id='+U,{method:'POST',body:JSON.stringify({content:v})})}
function sendTyping(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'typing'}))}

function toggleSearch(){var b=$('searchBar');b.style.display=b.style.display==='none'||!b.style.display?'block':'none';if(b.style.display==='block')$('searchIn').focus();else{$('searchIn').value='';loadRoomMsgs()}}
function doSearch(){var q=$('searchIn').value.trim();if(!q){loadRoomMsgs();return}api('/api/messages/search?room_id='+room+'&q='+encodeURIComponent(q)).then(function(m){$('cMsgs').innerHTML=m.map(function(x){return '<div class="message message-received">'+esc(x.content)+'</div>'}).join('')||'<div class="empty-state"><span>No results found</span></div>'})}
function loadRoomMsgs(){if(room)api('/api/rooms/'+room+'/messages').then(function(m){$('cMsgs').innerHTML=m.map(function(x){var c=x.sender_id===U?'message-sent':'message-received';return '<div class="message '+c+'">'+esc(x.content)+'</div>'}).join('')})}

function beep(){try{var c=new(window.AudioContext||window.webkitAudioContext)();var o=c.createOscillator();var g=c.createGain();o.connect(g);g.connect(c.destination);g.gain.value=0.08;o.frequency.value=880;o.start();o.stop(c.currentTime+0.08)}catch(e){}}

function loadAgents(){api('/api/agents').then(function(a){$('aList').innerHTML=a.map(function(x){return '<div class="card"><div style="display:flex;justify-content:space-between;align-items:start"><div><div style="font-weight:600;font-size:14px">'+x.name+'</div><div style="display:flex;gap:6px;margin-top:6px"><span class="badge badge-info">'+x.provider+'</span></div></div><button class="btn btn-danger btn-sm" onclick="delAgent(\''+x.id+'\')">Delete</button></div><div style="font-size:13px;color:var(--text-secondary);margin-top:10px;line-height:1.5">'+esc(x.system_prompt.substring(0,120))+(x.system_prompt.length>120?'...':'')+'</div></div>'}).join('')||'<div class="empty-state"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/></svg><span>No agents yet. Create one to get started.</span></div>'})}
function mkAgent(){var n=$('naN').value,p=$('naP').value,pr=$('naPr').value,m=$('naM').value;if(!n)return;api('/api/agents',{method:'POST',body:JSON.stringify({name:n,system_prompt:p,provider:pr,model:m})}).then(function(){hideM('mAgent');loadAgents()})}
function delAgent(id){fetch('/api/agents/'+id,{method:'DELETE'}).then(function(){loadAgents()})}

function loadNet(){api('/api/network/status').then(function(s){if(s.status==='stopped'){$('netC').innerHTML='<div class="card"><h4>Network Offline</h4><p style="color:var(--text-muted)">P2P network is not running.</p></div>';return}var i=s.identity||{};var peers=s.peers||[];$('netC').innerHTML='<div class="card"><h4>Your Identity</h4><div class="stat-row"><span>DID</span><span class="value" style="font-size:11px;word-break:break-all;max-width:250px;text-align:right">'+i.did+'</span></div><div class="stat-row"><span>Peer ID</span><span class="value">'+i.peer_id+'</span></div><div class="stat-row"><span>Fingerprint</span><span class="value" style="font-size:11px">'+i.fingerprint+'</span></div></div><div class="card"><h4>Connection</h4><div class="stat-row"><span>Status</span><span class="badge badge-success">'+s.status+'</span></div><div class="stat-row"><span>Port</span><span class="value">'+s.port+'</span></div><div class="stat-row"><span>Peers</span><span class="value">'+s.total_peers+'</span></div></div><div class="card"><h4>Invite Code</h4><div style="font-size:11px;word-break:break-all;color:var(--text-secondary);margin-bottom:12px;font-family:monospace;background:var(--bg-subtle);padding:10px;border-radius:var(--radius)">'+s.invite_code+'</div><button class="btn btn-secondary btn-sm" onclick="navigator.clipboard.writeText(\''+s.invite_code+'\');this.textContent=\'Copied!\';setTimeout(function(){this.textContent=\'Copy code\'},2000)">Copy code</button></div><div class="card"><h4>Connect to Peer</h4><div style="display:flex;gap:8px"><input id="connCode" placeholder="Paste invite code..." style="flex:1"><button class="btn btn-primary btn-sm" onclick="connectPeer()">Connect</button></div><div id="connMsg" style="margin-top:8px;font-size:12px"></div></div>'+(peers.length?'<div class="card"><h4>Connected Peers</h4>'+peers.map(function(p){return '<div class="peer-row"><div><div style="font-weight:500">'+(p.display_name||p.peer_id)+'</div><div style="font-size:11px;color:var(--text-muted)">'+p.address+'</div></div><span class="badge badge-success">online</span></div>'}).join('')+'</div>':'')})}
function connectPeer(){var c=$('connCode').value.trim();if(!c)return;api('/api/network/connect?invite_code='+encodeURIComponent(c),{method:'POST'}).then(function(r){$('connMsg').innerHTML='<span style="color:var(--success)">Connected to '+(r.display_name||r.peer_id)+'</span>';loadNet()}).catch(function(){$('connMsg').innerHTML='<span style="color:var(--error)">Connection failed</span>'})}

function loadKeys(){api('/api/users/keys?user_id='+U).then(function(k){$('kList').innerHTML=k.map(function(x){return '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-subtle)"><div style="font-size:13px"><span style="font-weight:500">'+x.provider+'</span>'+(x.model?' <span style="color:var(--text-muted)">('+x.model+')</span>':'')+'</div><button class="btn btn-danger btn-sm" onclick="delKey(\''+x.provider+'\')">Remove</button></div>'}).join('')||'<div style="color:var(--text-muted);font-size:13px;padding:8px 0">No API keys configured</div>';$('pInfo').innerHTML='<div style="margin-bottom:4px"><span style="color:var(--text-muted)">User:</span> <strong>'+N+'</strong></div><div style="font-size:12px;color:var(--text-muted)">ID: '+U+'</div>'})}
function saveKey(){var p=$('kProv').value,k=$('kVal').value;if(!k)return;api('/api/users/keys?user_id='+U,{method:'POST',body:JSON.stringify({provider:p,api_key:k})}).then(function(){$('kVal').value='';loadKeys()})}
function delKey(p){fetch('/api/users/keys/'+p+'?user_id='+U,{method:'DELETE'}).then(function(){loadKeys()})}

function dangerAction(action,msg){if(!confirm(msg))return;var url='/api/danger/'+action;if(action==='keys'||action==='user')url+='?user_id='+U;fetch(url,{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){$('dangerMsg').innerHTML='<span style="color:var(--success)">'+d.message+'</span>';if(action==='user')setTimeout(function(){logout()},1500);if(action==='everything')setTimeout(function(){location.reload()},2000);loadKeys();loadAgents();loadRooms()}).catch(function(){$('dangerMsg').innerHTML='<span style="color:var(--error)">Error</span>'})}

function loadHW(){api('/api/hardware').then(function(r){var h=r.hardware;$('hwC').innerHTML='<div class="card"><h4>Hardware</h4><div class="stat-row"><span>Operating System</span><span class="value">'+h.os+'</span></div><div class="stat-row"><span>CPU Cores</span><span class="value">'+h.cpu_cores+'</span></div><div class="stat-row"><span>RAM</span><span class="value">'+h.ram_gb+' GB</span></div><div class="stat-row"><span>GPU</span><span class="value">'+h.gpu+'</span></div><div class="stat-row"><span>VRAM</span><span class="value">'+h.gpu_vram_gb+' GB</span></div></div><div class="card"><h4>Model Recommendation</h4><p style="font-size:13px;color:var(--text-secondary);line-height:1.6">'+r.recommendation+'</p><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:12px">'+r.suggested_models.map(function(m){return '<span class="badge badge-neutral">'+m.size+(m.quant?' '+m.quant:'')+'</span>'}).join('')+'</div></div>'})}

function loadProv(){api('/api/providers').then(function(p){$('naPr').innerHTML=p.map(function(x){return '<option value="'+x.name+'">'+x.name+'</option>'}).join('')})}
function mkRoom(){var n=$('nrN').value,t=$('nrT').value;if(!n)return;api('/api/rooms?user_id='+U,{method:'POST',body:JSON.stringify({name:n,type:t})}).then(function(){hideM('mRoom');loadRooms()})}
function invBot(){var a=$('ibA').value;if(!a||!room)return;api('/api/rooms/'+room+'/members',{method:'POST',body:JSON.stringify({member_type:'agent',member_id:a})}).then(function(){hideM('mBot')})}
function invUser(){var u=$('iuU').value;if(!u||!room)return;api('/api/rooms/'+room+'/members',{method:'POST',body:JSON.stringify({member_type:'user',member_id:u})}).then(function(){hideM('mUser')})}
function uploadFile(){var f=$('fileIn').files[0];if(!f||!room)return;var r=new FileReader();r.onload=function(){var b64=r.result.split(',')[1];api('/api/rooms/'+room+'/files?user_id='+U+'&filename='+f.name,{method:'POST',body:JSON.stringify({content:b64})}).then(function(){hideM('mFile');$('cMsgs').innerHTML+='<div class="message message-received"><div class="sender">File</div>'+f.name+' ('+Math.round(f.size/1024)+' KB)</div>';$('cMsgs').scrollTop=$('cMsgs').scrollHeight})};r.readAsDataURL(f)}

function modal(id){$(id).classList.add('show');if(id==='mBot')api('/api/agents').then(function(a){$('ibA').innerHTML=a.map(function(x){return '<option value="'+x.id+'">'+x.name+'</option>'}).join('')});if(id==='mUser')api('/api/users').then(function(u){$('iuU').innerHTML=u.filter(function(x){return x.id!==U}).map(function(x){return '<option value="'+x.id+'">'+(x.display_name||x.username)+'</option>'}).join('')||'<option>No users</option>'})}
function hideM(id){$(id).classList.remove('show')}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

if(localStorage.getItem('ht')){T=localStorage.getItem('ht');U=localStorage.getItem('hu');N=localStorage.getItem('hn');enter()}

var STEPS=[
{i:'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',t:'Welcome to Hive',p:'A decentralized, end-to-end encrypted AI messenger. Your data stays on your device.',x:'<strong>What makes Hive different:</strong><br>End-to-end encryption with Signal Protocol<br>Peer-to-peer networking — no central server<br>AI agents run locally on your machine<br>You own your data, your keys, your identity'},
{i:'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10"/></svg>',t:'Network',p:'Connect with peers over your local network or via Tailscale. Share your invite code to get started.',x:'<strong>How to connect:</strong><br>1. Go to the Network tab<br>2. Copy your invite code<br>3. Share it with someone on your network<br>4. They paste it to connect directly'},
{i:'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',t:'You are ready',p:'Add an API key, create an agent, create a room, and start chatting.',x:'<strong>Quick start:</strong><br>1. Settings — add your API key (try Groq, it is free)<br>2. Agents — create your first AI agent<br>3. Chat — create a room and invite the bot<br>4. Start chatting!'}
];
var ti=0;
function showTut(){ti=0;renderT();$('tut').style.display='flex'}
function skipTut(){localStorage.setItem('htut','1');$('tut').style.display='none'}
function tutNext(){if(ti>=STEPS.length-1){skipTut();return}ti++;renderT()}
function tutBack(){if(ti>0){ti--;renderT()}}
function renderT(){var s=STEPS[ti];$('tIcon').innerHTML=s.i;$('tTitle').textContent=s.t;$('tText').textContent=s.p;$('tInfo').innerHTML=s.x;$('tDots').innerHTML=STEPS.map(function(_,i){return '<div class="tut-dot'+(i===ti?' active':'')+'"></div>'}).join('');$('tPrev').style.display=ti>0?'inline-flex':'none';$('tNext').textContent=ti>=STEPS.length-1?'Get started':'Next'}
</script>
</body>
</html>

"""
