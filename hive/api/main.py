"""
Hive API — FastAPI backend for agent management, chat, and observability.
v0.2: swarm, arena, memory, scheduler, API keys, voice.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
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
    logger.info("Hive v0.2 initialized — all systems ready")
    # Start scheduler loop in background
    from hive.core.scheduler import scheduler_loop
    task = asyncio.create_task(scheduler_loop(interval=60))
    yield
    task.cancel()


app = FastAPI(
    title="Hive",
    description="Self-hosted multi-agent AI platform — swarm, arena, memory, voice",
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
    """Intelligent model selection — recommends the best model for your task."""
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
    """Cost optimization analysis — usage patterns and savings recommendations."""
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
# Web UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def ui():
    return HTML_PAGE


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐝 Hive</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{--bg:#0a0a0a;--surface:#141414;--border:#222;--text:#e0e0e0;--muted:#666;--accent:#f59e0b;--green:#10b981;--red:#ef4444;--blue:#3b82f6}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;overflow:hidden}
  /* Sidebar */
  .sidebar{width:260px;border-right:1px solid var(--border);display:flex;flex-direction:column;background:var(--surface);flex-shrink:0}
  .sidebar-header{padding:1rem;border-bottom:1px solid var(--border)}
  .sidebar-header h1{font-size:1.2rem}
  .sidebar-header h1 span{color:var(--accent)}
  .nav-tabs{display:flex;flex-direction:column;padding:0.5rem;gap:2px}
  .nav-tab{padding:0.6rem 0.75rem;border-radius:6px;cursor:pointer;font-size:0.85rem;color:var(--muted);transition:all .15s;display:flex;align-items:center;gap:0.5rem}
  .nav-tab:hover{background:#1a1a1a;color:var(--text)}
  .nav-tab.active{background:#1a1a1a;color:var(--accent);font-weight:600}
  .agent-list{flex:1;overflow-y:auto;padding:0.5rem}
  .agent-item{padding:0.6rem;border-radius:6px;cursor:pointer;margin-bottom:2px;transition:background .15s}
  .agent-item:hover{background:#1a1a1a}
  .agent-item.active{background:#1a1a1a;border-left:3px solid var(--accent)}
  .agent-item .name{font-weight:600;font-size:0.85rem}
  .agent-item .meta{font-size:0.7rem;color:var(--muted);margin-top:2px}
  /* Main */
  .main{flex:1;display:flex;flex-direction:column;overflow:hidden}
  .topbar{padding:0.75rem 1rem;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:1rem}
  .topbar h2{font-size:1rem;white-space:nowrap}
  .content{flex:1;overflow-y:auto;padding:1rem}
  /* Buttons & inputs */
  .btn{padding:0.4rem 0.8rem;border:none;border-radius:6px;cursor:pointer;font-size:0.8rem;font-weight:600;transition:all .15s}
  .btn-primary{background:var(--accent);color:#000}
  .btn-primary:hover{background:#d97706}
  .btn-sm{padding:0.25rem 0.5rem;font-size:0.7rem}
  .btn-danger{background:var(--red);color:#fff}
  .btn-ghost{background:transparent;border:1px solid var(--border);color:var(--text)}
  .btn-ghost:hover{border-color:var(--accent)}
  input,textarea,select{padding:0.5rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:0.85rem;outline:none;width:100%}
  input:focus,textarea:focus,select:focus{border-color:var(--accent)}
  textarea{resize:vertical;min-height:60px}
  /* Chat */
  .chat-messages{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:0.5rem}
  .msg{max-width:80%;padding:0.6rem 0.8rem;border-radius:10px;font-size:0.85rem;line-height:1.5}
  .msg-user{align-self:flex-end;background:#1e3a5f;border-bottom-right-radius:3px}
  .msg-assistant{align-self:flex-start;background:var(--surface);border:1px solid var(--border);border-bottom-left-radius:3px}
  .msg-system{align-self:center;color:var(--muted);font-size:0.75rem;font-style:italic}
  .chat-input{padding:0.75rem;border-top:1px solid var(--border);display:flex;gap:0.5rem}
  .stats-bar{display:flex;gap:0.75rem;padding:0.4rem 0.75rem;border-top:1px solid var(--border);font-size:0.7rem;color:var(--muted);flex-wrap:wrap}
  .stat .val{color:var(--green);font-weight:600}
  /* Cards */
  .card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;margin-bottom:0.75rem}
  .card h3{font-size:0.9rem;margin-bottom:0.5rem}
  .grid{display:grid;gap:0.75rem}
  .grid-2{grid-template-columns:1fr 1fr}
  .grid-3{grid-template-columns:1fr 1fr 1fr}
  .grid-4{grid-template-columns:1fr 1fr 1fr 1fr}
  /* Tables */
  table{width:100%;border-collapse:collapse;font-size:0.8rem}
  th{text-align:left;padding:0.5rem;border-bottom:1px solid var(--border);color:var(--muted);font-weight:600;font-size:0.7rem;text-transform:uppercase}
  td{padding:0.5rem;border-bottom:1px solid #1a1a1a}
  tr:hover td{background:#1a1a1a}
  /* Badges */
  .badge{display:inline-block;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600}
  .badge-green{background:#064e3b;color:#10b981}
  .badge-blue{background:#1e3a5f;color:#60a5fa}
  .badge-amber{background:#451a03;color:#f59e0b}
  .badge-red{background:#450a0a;color:#ef4444}
  .badge-gray{background:#1f1f1f;color:#888}
  /* Model card */
  .model-row{display:flex;align-items:center;gap:0.75rem;padding:0.6rem;border-bottom:1px solid #1a1a1a}
  .model-row:hover{background:#1a1a1a}
  .model-rank{width:24px;text-align:center;font-weight:700;color:var(--accent);font-size:0.9rem}
  .model-info{flex:1}
  .model-name{font-weight:600;font-size:0.85rem}
  .model-meta{font-size:0.7rem;color:var(--muted)}
  .model-stats{display:flex;gap:0.75rem;font-size:0.7rem}
  .model-stats span{color:var(--muted)}
  .model-stats .val{color:var(--text);font-weight:600}
  /* Router */
  .router-result{background:#1a1a0a;border:1px solid #333;border-radius:8px;padding:1rem;margin-top:0.75rem}
  .router-result .rec{font-size:1.1rem;font-weight:700;color:var(--accent)}
  .router-result .reason{font-size:0.8rem;color:var(--muted);margin-top:0.25rem}
  /* Empty */
  .empty{display:flex;align-items:center;justify-content:center;flex:1;color:var(--muted);font-size:0.9rem;flex-direction:column;gap:0.5rem}
  /* Form */
  .form-group{margin-bottom:0.75rem}
  .form-group label{display:block;font-size:0.75rem;color:var(--muted);margin-bottom:0.25rem;font-weight:600}
  .form-row{display:flex;gap:0.5rem}
  .form-row>*{flex:1}
  /* Scrollbar */
  ::-webkit-scrollbar{width:6px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
  ::-webkit-scrollbar-thumb:hover{background:#555}
  /* Page sections */
  .page{display:none}
  .page.active{display:flex;flex-direction:column;flex:1;overflow:hidden}
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header">
    <h1>🐝 <span>Hive</span></h1>
    <p style="font-size:0.65rem;color:var(--muted);margin-top:2px">Multi-agent AI platform · v0.2</p>
  </div>
  <div class="nav-tabs">
    <div class="nav-tab active" onclick="showPage('chat')">💬 Chat</div>
    <div class="nav-tab" onclick="showPage('models')">🧠 Models</div>
    <div class="nav-tab" onclick="showPage('router')">🎯 Model Router</div>
    <div class="nav-tab" onclick="showPage('arena')">⚔️ Arena</div>
    <div class="nav-tab" onclick="showPage('costs')">💰 Costs</div>
    <div class="nav-tab" onclick="showPage('keys')">🔑 API Keys</div>
    <div class="nav-tab" onclick="showPage('settings')">⚙️ Settings</div>
  </div>
  <div style="padding:0.5rem;border-top:1px solid var(--border)">
    <button class="btn btn-primary" style="width:100%" onclick="toggleNewAgent()">+ New Agent</button>
  </div>
  <div class="agent-list" id="agentList"></div>
</div>
<div class="main">

<!-- ═══════════ CHAT PAGE ═══════════ -->
<div class="page active" id="page-chat">
  <div class="topbar">
    <h2 id="chatTitle">Select an agent</h2>
    <div id="chatActions"></div>
  </div>
  <div class="chat-messages" id="messages">
    <div class="empty">🐝 Select or create an agent to start chatting</div>
  </div>
  <div class="stats-bar" id="statsBar" style="display:none">
    <div class="stat">LLM: <span class="val" id="statCalls">0</span></div>
    <div class="stat">Tools: <span class="val" id="statTools">0</span></div>
    <div class="stat">Tokens: <span class="val" id="statTokens">0</span></div>
    <div class="stat">Cost: <span class="val" id="statCost">$0</span></div>
    <div class="stat">Latency: <span class="val" id="statLatency">0ms</span></div>
  </div>
  <div class="chat-input" id="chatInput" style="display:none">
    <input id="userMsg" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendMessage()">
    <button class="btn btn-primary" onclick="sendMessage()">Send</button>
  </div>
</div>

<!-- ═══════════ MODELS PAGE ═══════════ -->
<div class="page" id="page-models">
  <div class="topbar"><h2>🧠 Model Intelligence Rankings</h2><span style="font-size:0.7rem;color:var(--muted)">Artificial Analysis Aug 2026</span></div>
  <div class="content" id="modelsList"></div>
</div>

<!-- ═══════════ ROUTER PAGE ═══════════ -->
<div class="page" id="page-router">
  <div class="topbar"><h2>🎯 Intelligent Model Router</h2></div>
  <div class="content">
    <div class="card">
      <h3>Analyze a task</h3>
      <div class="form-group"><label>What do you need help with?</label><textarea id="routerPrompt" placeholder="e.g., Write a Python function to sort a list, or analyze this complex architecture problem..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>Priority</label><select id="routerPriority"><option value="balanced">Balanced</option><option value="intelligence">Maximum Intelligence</option><option value="speed">Speed</option><option value="budget">Budget</option></select></div>
        <div class="form-group"><label>Requirements</label><div style="display:flex;gap:0.5rem;margin-top:0.25rem"><label style="font-size:0.8rem;display:flex;align-items:center;gap:4px"><input type="checkbox" id="routerVision" style="width:auto"> Vision</label><label style="font-size:0.8rem;display:flex;align-items:center;gap:4px"><input type="checkbox" id="routerPrivacy" style="width:auto"> Privacy</label></div></div>
      </div>
      <button class="btn btn-primary" onclick="analyzePrompt()">Analyze & Recommend</button>
      <div id="routerResult"></div>
    </div>
  </div>
</div>

<!-- ═══════════ ARENA PAGE ═══════════ -->
<div class="page" id="page-arena">
  <div class="topbar"><h2>⚔️ Model Arena</h2></div>
  <div class="content">
    <div class="card">
      <h3>Compare models on the same prompt</h3>
      <div class="form-group"><label>Prompt</label><textarea id="arenaPrompt" placeholder="Enter a prompt to test across models..."></textarea></div>
      <div class="form-group"><label>Providers (comma-separated, or leave empty for all configured)</label><input id="arenaProviders" placeholder="e.g., ollama,openai,anthropic"></div>
      <button class="btn btn-primary" onclick="runArena()">Run Arena</button>
      <div id="arenaResult" style="margin-top:0.75rem"></div>
    </div>
  </div>
</div>

<!-- ═══════════ COSTS PAGE ═══════════ -->
<div class="page" id="page-costs">
  <div class="topbar"><h2>💰 Cost Optimization</h2><button class="btn btn-ghost btn-sm" onclick="loadCosts()">Refresh</button></div>
  <div class="content" id="costsContent"></div>
</div>

<!-- ═══════════ KEYS PAGE ═══════════ -->
<div class="page" id="page-keys">
  <div class="topbar"><h2>🔑 API Keys</h2></div>
  <div class="content">
    <div class="card">
      <h3>Create API Key</h3>
      <div class="form-row">
        <div class="form-group"><label>Name</label><input id="keyName" placeholder="my-app"></div>
        <div class="form-group"><label>Agent (optional)</label><input id="keyAgent" placeholder="agent ID"></div>
      </div>
      <button class="btn btn-primary" onclick="createKey()">Create Key</button>
      <div id="keyResult" style="margin-top:0.5rem"></div>
    </div>
    <div class="card"><h3>Existing Keys</h3><div id="keysList"></div></div>
  </div>
</div>

<!-- ═══════════ SETTINGS PAGE ═══════════ -->
<div class="page" id="page-settings">
  <div class="topbar"><h2>⚙️ Settings</h2></div>
  <div class="content">
    <div class="card">
      <h3>Create New Agent</h3>
      <div class="form-group"><label>Name</label><input id="sAgentName" placeholder="Research Assistant"></div>
      <div class="form-group"><label>System Prompt</label><textarea id="sAgentPrompt" rows="3">You are a helpful assistant.</textarea></div>
      <div class="form-row">
        <div class="form-group"><label>Provider</label><select id="sAgentProvider"></select></div>
        <div class="form-group"><label>Model (empty = default)</label><input id="sAgentModel" placeholder="llama3.3"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Temperature</label><input id="sAgentTemp" type="number" value="0.7" min="0" max="2" step="0.1"></div>
        <div class="form-group"><label>Max Tokens</label><input id="sAgentMaxTok" type="number" value="4096" min="100" max="128000"></div>
      </div>
      <button class="btn btn-primary" onclick="createAgentFull()">Create Agent</button>
    </div>
    <div class="card">
      <h3>Provider Status</h3>
      <div id="providerStatus"></div>
    </div>
  </div>
</div>

<!-- ═══════════ NEW AGENT MODAL ═══════════ -->
<div id="newAgentModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:100;display:none;align-items:center;justify-content:center">
  <div class="card" style="width:400px;max-width:90vw">
    <h3>New Agent</h3>
    <div class="form-group"><label>Name</label><input id="nAgentName" placeholder="My Agent"></div>
    <div class="form-group"><label>System Prompt</label><textarea id="nAgentPrompt">You are a helpful assistant.</textarea></div>
    <div class="form-group"><label>Provider</label><select id="nAgentProvider"></select></div>
    <div class="form-group"><label>Model (empty = default)</label><input id="nAgentModel"></div>
    <div style="display:flex;gap:0.5rem;margin-top:0.75rem">
      <button class="btn btn-primary" onclick="createAgentModal()">Create</button>
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

</div><!-- /main -->
<script>
let currentAgent=null,conversationId=null;
const $=id=>document.getElementById(id);

// ── Navigation ──
function showPage(name){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  $('page-'+name).classList.add('active');
  document.querySelectorAll('.nav-tab')[['chat','models','router','arena','costs','keys','settings'].indexOf(name)].classList.add('active');
  if(name==='models')loadModels();
  if(name==='costs')loadCosts();
  if(name==='keys')loadKeys();
  if(name==='settings')loadProviders();
}

// ── Agents ──
async function loadAgents(){
  const r=await fetch('/api/agents');const agents=await r.json();
  $('agentList').innerHTML=agents.map(a=>`<div class="agent-item ${currentAgent?.id===a.id?'active':''}" onclick="selectAgent('${a.id}')"><div class="name">${a.name}</div><div class="meta">${a.provider} · ${a.model||'default'}</div></div>`).join('');
  // Populate provider selects
  const pr=await fetch('/api/providers');const providers=await pr.json();
  const opts=providers.map(p=>`<option value="${p.name}">${p.name}${p.configured?'':'  (no key)'}</option>`).join('');
  ['nAgentProvider','sAgentProvider'].forEach(id=>{const el=$(id);if(el)el.innerHTML=opts;});
}
async function selectAgent(id){
  const r=await fetch('/api/agents/'+id);currentAgent=await r.json();conversationId=null;
  $('chatTitle').textContent=currentAgent.name;$('messages').innerHTML='';$('chatInput').style.display='flex';$('statsBar').style.display='flex';
  $('chatActions').innerHTML=`<button class="btn btn-danger btn-sm" onclick="deleteAgent('${id}')">Delete</button>`;
  showPage('chat');loadAgents();
}
async function deleteAgent(id){if(!confirm('Delete?'))return;await fetch('/api/agents/'+id,{method:'DELETE'});currentAgent=null;$('chatTitle').textContent='Select an agent';$('messages').innerHTML='<div class="empty">🐝 Select an agent</div>';$('chatInput').style.display='none';$('statsBar').style.display='none';$('chatActions').innerHTML='';loadAgents();}
function toggleNewAgent(){$('newAgentModal').style.display='flex';loadAgents();}
function closeModal(){$('newAgentModal').style.display='none';}
async function createAgentModal(){
  const body={name:$('nAgentName').value,system_prompt:$('nAgentPrompt').value,provider:$('nAgentProvider').value,model:$('nAgentModel').value};
  if(!body.name)return;await fetch('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});closeModal();$('nAgentName').value='';loadAgents();
}
async function createAgentFull(){
  const body={name:$('sAgentName').value,system_prompt:$('sAgentPrompt').value,provider:$('sAgentProvider').value,model:$('sAgentModel').value,temperature:parseFloat($('sAgentTemp').value),max_tokens:parseInt($('sAgentMaxTok').value)};
  if(!body.name)return;await fetch('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('sAgentName').value='';loadAgents();alert('Agent created!');
}

// ── Chat ──
async function sendMessage(){
  const input=$('userMsg');const msg=input.value.trim();if(!msg||!currentAgent)return;input.value='';
  const msgs=$('messages');msgs.innerHTML+=`<div class="msg msg-user">${esc(msg)}</div><div class="msg msg-system">Thinking...</div>`;msgs.scrollTop=msgs.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:currentAgent.id,message:msg,conversation_id:conversationId})});
    const data=await r.json();conversationId=data.conversation_id;
    msgs.querySelector('.msg-system:last-child')?.remove();
    msgs.innerHTML+=`<div class="msg msg-assistant">${esc(data.response).replace(/\\n/g,'<br>')}</div>`;
    const s=data.stats;$('statCalls').textContent=s.llm_calls;$('statTools').textContent=s.tool_executions;$('statTokens').textContent=s.tokens_in+s.tokens_out;$('statCost').textContent='$'+s.cost_usd.toFixed(4);$('statLatency').textContent=s.latency_ms+'ms';
  }catch(e){msgs.querySelector('.msg-system:last-child')?.remove();msgs.innerHTML+=`<div class="msg msg-system" style="color:var(--red)">Error: ${e.message}</div>`;}
  msgs.scrollTop=msgs.scrollHeight;
}

// ── Models ──
async function loadModels(){
  const r=await fetch('/api/models');const models=await r.json();
  $('modelsList').innerHTML=`<table><thead><tr><th>#</th><th>Model</th><th>Intelligence</th><th>Context</th><th>Speed</th><th>Cost (in/out per 1M)</th><th>Capabilities</th></tr></thead><tbody>${
    models.map((m,i)=>`<tr><td style="color:var(--accent);font-weight:700">${i+1}</td><td style="font-weight:600">${m.model}</td><td><span class="badge ${m.intelligence>=60?'badge-green':m.intelligence>=50?'badge-blue':m.intelligence>=40?'badge-amber':'badge-gray'}">${m.intelligence}/100</span></td><td>${formatCtx(m.context_window)}</td><td><span class="badge ${m.speed_tier==='ultra'?'badge-green':m.speed_tier==='fast'?'badge-blue':'badge-gray'}">${m.speed_tier}</span></td><td>$${m.cost_in_per_m} / $${m.cost_out_per_m}</td><td>${m.vision?'👁 ':''}${m.tools?'🔧 ':''}</td></tr>`).join('')
  }</tbody></table>`;
}
function formatCtx(n){if(n>=1e6)return(n/1e6).toFixed(n%1e6===0?0:1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return n;}

// ── Router ──
async function analyzePrompt(){
  const body={prompt:$('routerPrompt').value,priority:$('routerPriority').value,vision:$('routerVision').checked,privacy:$('routerPrivacy').checked};
  if(!body.prompt)return;
  const r=await fetch('/api/router',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  $('routerResult').innerHTML=`<div class="router-result"><div class="rec">${d.provider} / ${d.model}</div><div class="reason">${d.reason}</div><div style="display:flex;gap:1rem;margin-top:0.5rem;font-size:0.75rem"><span>Intelligence: <b style="color:var(--green)">${d.intelligence}/100</b></span><span>Speed: <b>${d.speed_tier}</b></span><span>Cost: <b>${d.cost_tier}</b></span><span>~$${d.estimated_cost_per_1k_tokens}/1K tokens</span></div></div>`;
}

// ── Arena ──
async function runArena(){
  const prompt=$('arenaPrompt').value;if(!prompt)return;
  const provStr=$('arenaProviders').value;const providers=provStr?provStr.split(',').map(s=>s.trim()):[];
  $('arenaResult').innerHTML='<div class="msg msg-system">Running arena... this may take a moment</div>';
  try{
    const r=await fetch('/api/arena',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,providers})});
    const d=await r.json();
    $('arenaResult').innerHTML=`<table><thead><tr><th>#</th><th>Provider</th><th>Model</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>${
      d.results.map((r,i)=>`<tr><td>${i===0?'🏆':'  '}${i+1}</td><td>${r.provider}</td><td style="font-weight:600">${r.model}</td><td>${r.latency_ms}ms</td><td>${r.tokens_in+r.tokens_out}</td><td>$${r.cost_usd.toFixed(4)}</td></tr>`).join('')
    }</tbody></table><div style="margin-top:0.75rem"><h3 style="font-size:0.85rem;margin-bottom:0.5rem">Responses</h3>${
      d.results.map(r=>`<div class="card"><div style="font-size:0.75rem;color:var(--muted);margin-bottom:0.25rem">${r.provider} / ${r.model} · ${r.latency_ms}ms</div><div style="font-size:0.8rem">${esc(r.response).substring(0,300).replace(/\\n/g,'<br>')}${r.response.length>300?'...':''}</div></div>`).join('')
    }</div>`;
  }catch(e){$('arenaResult').innerHTML=`<div class="msg msg-system" style="color:var(--red)">Error: ${e.message}</div>`;}
}

// ── Costs ──
async function loadCosts(){
  const r=await fetch('/api/costs');const d=await r.json();
  if(d.total_requests===0){$('costsContent').innerHTML='<div class="empty">No usage data yet. Chat with an agent to generate data.</div>';return;}
  $('costsContent').innerHTML=`<div class="grid grid-4" style="margin-bottom:1rem"><div class="card" style="text-align:center"><div style="font-size:1.5rem;font-weight:700;color:var(--green)">$${d.total_cost.toFixed(4)}</div><div style="font-size:0.7rem;color:var(--muted)">Total Cost</div></div><div class="card" style="text-align:center"><div style="font-size:1.5rem;font-weight:700;color:var(--accent)">${d.total_requests}</div><div style="font-size:0.7rem;color:var(--muted)">Requests</div></div><div class="card" style="text-align:center"><div style="font-size:1.5rem;font-weight:700;color:var(--blue)">$${d.potential_savings.toFixed(4)}</div><div style="font-size:0.7rem;color:var(--muted)">Potential Savings</div></div><div class="card" style="text-align:center"><div style="font-size:1.5rem;font-weight:700;color:var(--red)">${d.savings_pct}%</div><div style="font-size:0.7rem;color:var(--muted)">Optimization</div></div></div>${
    Object.entries(d.by_model).map(([m,v])=>`<div class="card"><div style="display:flex;justify-content:space-between"><strong>${m}</strong><span style="color:var(--green)">$${v.cost.toFixed(4)}</span></div><div style="font-size:0.75rem;color:var(--muted);margin-top:4px">${v.requests} requests · avg $${v.avg_cost_per_request.toFixed(4)}/req · avg ${v.avg_latency_ms}ms</div></div>`).join('')
  }${d.recommendations.length?`<h3 style="margin:1rem 0 0.5rem;font-size:0.9rem">💡 Recommendations</h3>${d.recommendations.map(r=>`<div class="card" style="border-left:3px solid var(--accent)"><div style="font-weight:600;font-size:0.85rem">${r.type==='model_downgrade'?'Switch to cheaper model':r.type==='enable_caching'?'Enable caching':'Speed optimization'}</div><div style="font-size:0.8rem;color:var(--muted);margin-top:4px">${r.reason}</div><div style="font-size:0.75rem;color:var(--green);margin-top:4px">Save $${r.potential_savings.toFixed(4)}</div></div>`).join('')}`:''}`;
}

// ── API Keys ──
async function loadKeys(){
  const r=await fetch('/api/keys');const keys=await r.json();
  $('keysList').innerHTML=keys.length?`<table><thead><tr><th>Name</th><th>Requests</th><th>Last Used</th><th>Status</th><th></th></tr></thead><tbody>${keys.map(k=>`<tr><td>${k.name}</td><td>${k.request_count}</td><td>${k.last_used?new Date(k.last_used*1000).toLocaleString():'never'}</td><td><span class="badge ${k.enabled?'badge-green':'badge-red'}">${k.enabled?'active':'revoked'}</span></td><td><button class="btn btn-danger btn-sm" onclick="revokeKey('${k.name}')">Revoke</button></td></tr>`).join('')}</tbody></table>`:'<p style="color:var(--muted);font-size:0.85rem">No API keys yet.</p>';
}
async function createKey(){
  const name=$('keyName').value;if(!name)return;
  const r=await fetch('/api/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,agent_id:$('keyAgent').value||null})});
  const d=await r.json();$('keyResult').innerHTML=`<div class="card" style="border:1px solid var(--green)"><strong>Key created:</strong><code style="display:block;margin-top:0.5rem;padding:0.5rem;background:var(--bg);border-radius:4px;word-break:break-all;font-size:0.8rem">${d.key}</code><p style="font-size:0.7rem;color:var(--red);margin-top:0.25rem">⚠️ Save this key — it won't be shown again.</p></div>`;$('keyName').value='';loadKeys();
}
async function revokeKey(name){if(!confirm('Revoke '+name+'?'))return;await fetch('/api/keys/'+name,{method:'DELETE'});loadKeys();}

// ── Providers ──
async function loadProviders(){
  const r=await fetch('/api/providers');const providers=await r.json();
  $('providerStatus').innerHTML=providers.map(p=>`<div style="display:flex;justify-content:space-between;padding:0.4rem 0;border-bottom:1px solid #1a1a1a"><span style="font-weight:600;font-size:0.85rem">${p.name}</span><span class="badge ${p.configured?'badge-green':'badge-gray'}">${p.configured?'configured':'no key'}</span></div>`).join('');
}

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
loadAgents();
</script>
</body>
</html>
"""
