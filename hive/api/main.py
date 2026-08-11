"""
Hive API â€” FastAPI backend for agent management, chat, and observability.
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
    logger.info("Hive v0.2 initialized â€” all systems ready")
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
# Web UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def ui():
    return HTML_PAGE


HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hive â€” Multi-Agent Platform</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{--bg:#09090b;--surface:#18181b;--surface2:#1f1f23;--border:#27272a;--text:#fafafa;--text2:#a1a1aa;--muted:#52525b;--accent:#6366f1;--accent2:#818cf8;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;--amber:#f59e0b;--radius:8px}
  body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;overflow:hidden;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
  .sidebar{width:240px;border-right:1px solid var(--border);display:flex;flex-direction:column;background:var(--surface);flex-shrink:0}
  .sidebar-brand{padding:20px;border-bottom:1px solid var(--border)}
  .sidebar-brand h1{font-size:16px;font-weight:700;letter-spacing:-0.02em}
  .sidebar-brand p{font-size:11px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:0.05em}
  .nav{padding:8px;display:flex;flex-direction:column;gap:1px}
  .nav-item{padding:8px 12px;border-radius:6px;cursor:pointer;font-size:13px;color:var(--text2);transition:all .15s;display:flex;align-items:center;gap:8px}
  .nav-item:hover{background:var(--surface2);color:var(--text)}
  .nav-item.active{background:var(--accent);color:#fff;font-weight:500}
  .nav-item .icon{width:16px;text-align:center;font-size:12px;opacity:.7}
  .nav-item.active .icon{opacity:1}
  .sidebar-agents{flex:1;overflow-y:auto;border-top:1px solid var(--border);padding:8px}
  .sidebar-agents-label{font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);padding:8px 12px 4px;font-weight:600}
  .agent-item{padding:8px 12px;border-radius:6px;cursor:pointer;margin-bottom:1px;transition:all .12s}
  .agent-item:hover{background:var(--surface2)}
  .agent-item.active{background:var(--surface2);box-shadow:inset 3px 0 0 var(--accent)}
  .agent-name{font-weight:500;font-size:13px}
  .agent-meta{font-size:11px;color:var(--muted);margin-top:1px}
  .sidebar-footer{padding:12px;border-top:1px solid var(--border)}
  .main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
  .topbar{padding:12px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:12px;flex-shrink:0}
  .topbar h2{font-size:15px;font-weight:600;letter-spacing:-0.01em}
  .topbar-right{display:flex;align-items:center;gap:8px}
  .content{flex:1;overflow-y:auto;padding:20px}
  .btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500;transition:all .15s;display:inline-flex;align-items:center;gap:6px}
  .btn-accent{background:var(--accent);color:#fff}
  .btn-accent:hover{background:var(--accent2)}
  .btn-outline{background:transparent;border:1px solid var(--border);color:var(--text2)}
  .btn-outline:hover{border-color:var(--text2);color:var(--text)}
  .btn-danger{background:var(--red);color:#fff}
  .btn-danger:hover{opacity:.9}
  .btn-sm{padding:4px 10px;font-size:12px}
  .btn-full{width:100%}
  input,textarea,select{padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;outline:none;width:100%;font-family:inherit;transition:border-color .15s}
  input:focus,textarea:focus,select:focus{border-color:var(--accent)}
  textarea{resize:vertical;min-height:60px}
  select{cursor:pointer}
  .chat-area{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:8px}
  .bubble{max-width:75%;padding:10px 14px;border-radius:var(--radius);font-size:13px;line-height:1.6}
  .bubble-user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:2px}
  .bubble-assistant{align-self:flex-start;background:var(--surface);border:1px solid var(--border);border-bottom-left-radius:2px}
  .bubble-system{align-self:center;color:var(--muted);font-size:12px;font-style:italic}
  .chat-bar{padding:12px 20px;border-top:1px solid var(--border);display:flex;gap:8px;flex-shrink:0}
  .metrics{display:flex;gap:16px;padding:6px 20px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);flex-shrink:0}
  .metrics .val{color:var(--green);font-weight:600;font-variant-numeric:tabular-nums}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:12px}
  .card-title{font-size:14px;font-weight:600;margin-bottom:12px;letter-spacing:-0.01em}
  .grid{display:grid;gap:12px}
  .grid-2{grid-template-columns:1fr 1fr}
  .grid-3{grid-template-columns:1fr 1fr 1fr}
  .grid-4{grid-template-columns:repeat(4,1fr)}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.04em}
  td{padding:8px 12px;border-bottom:1px solid var(--border)}
  tbody tr{transition:background .1s}
  tbody tr:hover{background:var(--surface2)}
  .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:0.02em}
  .tag-green{background:#052e16;color:#4ade80}
  .tag-blue{background:#172554;color:#60a5fa}
  .tag-amber{background:#451a03;color:#fbbf24}
  .tag-red{background:#450a0a;color:#f87171}
  .tag-gray{background:#27272a;color:#a1a1aa}
  .tag-purple{background:#2e1065;color:#a78bfa}
  .stat-card{text-align:center;padding:20px}
  .stat-value{font-size:24px;font-weight:700;letter-spacing:-0.02em;font-variant-numeric:tabular-nums}
  .stat-label{font-size:11px;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:0.04em}
  .form-label{display:block;font-size:12px;color:var(--text2);margin-bottom:4px;font-weight:500}
  .form-group{margin-bottom:12px}
  .form-row{display:flex;gap:12px}
  .form-row>*{flex:1}
  .empty{display:flex;align-items:center;justify-content:center;flex:1;color:var(--muted);font-size:13px;flex-direction:column;gap:8px}
  .router-result{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-top:12px}
  .router-model{font-size:18px;font-weight:700;color:var(--accent2);letter-spacing:-0.01em}
  .router-reason{font-size:13px;color:var(--text2);margin-top:4px}
  .router-meta{display:flex;gap:16px;margin-top:12px;font-size:12px;color:var(--muted)}
  .router-meta b{color:var(--text)}
  .page{display:none}
  .page.active{display:flex;flex-direction:column;flex:1;overflow:hidden}
  .divider{height:1px;background:var(--border);margin:8px 0}
  .provider-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)}
  .provider-name{font-weight:500;font-size:13px}
  .key-code{font-family:'JetBrains Mono',monospace;font-size:12px;padding:8px 12px;background:var(--bg);border-radius:6px;word-break:break-all;border:1px solid var(--border)}
  .rec-card{border-left:3px solid var(--accent);padding-left:12px}
  ::-webkit-scrollbar{width:5px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
  ::-webkit-scrollbar-thumb:hover{background:#555}
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-brand">
    <h1>Hive</h1>
    <p>Agent Platform v0.2</p>
  </div>
  <div class="nav" id="navTabs">
    <div class="nav-item active" data-page="chat"><span class="icon">&#9679;</span> Chat</div>
    <div class="nav-item" data-page="models"><span class="icon">&#9670;</span> Models</div>
    <div class="nav-item" data-page="router"><span class="icon">&#9654;</span> Router</div>
    <div class="nav-item" data-page="arena"><span class="icon">&#9876;</span> Arena</div>
    <div class="nav-item" data-page="costs"><span class="icon">&#9733;</span> Costs</div>
    <div class="nav-item" data-page="keys"><span class="icon">&#9711;</span> API Keys</div>
    <div class="nav-item" data-page="settings"><span class="icon">&#9881;</span> Settings</div>
  </div>
  <div class="sidebar-footer">
    <button class="btn btn-accent btn-full" onclick="openModal()">New Agent</button>
  </div>
  <div class="sidebar-agents">
    <div class="sidebar-agents-label">Agents</div>
    <div id="agentList"></div>
  </div>
</div>
<div class="main">

<div class="page active" id="page-chat">
  <div class="topbar"><h2 id="chatTitle">Select an agent</h2><div id="chatActions"></div></div>
  <div class="chat-area" id="messages"><div class="empty">Select or create an agent to begin</div></div>
  <div class="metrics" id="statsBar" style="display:none">
    <span>LLM calls: <span class="val" id="statCalls">0</span></span>
    <span>Tools: <span class="val" id="statTools">0</span></span>
    <span>Tokens: <span class="val" id="statTokens">0</span></span>
    <span>Cost: <span class="val" id="statCost">$0.00</span></span>
    <span>Latency: <span class="val" id="statLatency">0ms</span></span>
  </div>
  <div class="chat-bar" id="chatInput" style="display:none">
    <input id="userMsg" placeholder="Send a message..." onkeydown="if(event.key==='Enter')sendMessage()">
    <button class="btn btn-accent" onclick="sendMessage()">Send</button>
  </div>
</div>

<div class="page" id="page-models">
  <div class="topbar"><h2>Model Intelligence Rankings</h2><span style="font-size:11px;color:var(--muted)">Artificial Analysis, August 2026</span></div>
  <div class="content" id="modelsList"></div>
</div>

<div class="page" id="page-router">
  <div class="topbar"><h2>Model Router</h2></div>
  <div class="content">
    <div class="card">
      <div class="card-title">Analyze Task</div>
      <div class="form-group"><label class="form-label">Describe your task</label><textarea id="routerPrompt" placeholder="e.g., Write a Python function to implement binary search with error handling..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Priority</label><select id="routerPriority"><option value="balanced">Balanced</option><option value="intelligence">Maximum Intelligence</option><option value="speed">Speed</option><option value="budget">Budget</option></select></div>
        <div class="form-group"><label class="form-label">Requirements</label><div style="display:flex;gap:16px;margin-top:6px"><label style="font-size:13px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="routerVision" style="width:auto"> Vision</label><label style="font-size:13px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="routerPrivacy" style="width:auto"> Privacy</label></div></div>
      </div>
      <button class="btn btn-accent" onclick="analyzePrompt()">Analyze</button>
      <div id="routerResult"></div>
    </div>
  </div>
</div>

<div class="page" id="page-arena">
  <div class="topbar"><h2>Model Arena</h2></div>
  <div class="content">
    <div class="card">
      <div class="card-title">Compare Models</div>
      <div class="form-group"><label class="form-label">Prompt</label><textarea id="arenaPrompt" placeholder="Enter a prompt to test across multiple models..."></textarea></div>
      <div class="form-group"><label class="form-label">Providers (comma-separated, or empty for all configured)</label><input id="arenaProviders" placeholder="e.g., ollama, openai, anthropic"></div>
      <button class="btn btn-accent" onclick="runArena()">Run Benchmark</button>
      <div id="arenaResult" style="margin-top:12px"></div>
    </div>
  </div>
</div>

<div class="page" id="page-costs">
  <div class="topbar"><h2>Cost Optimization</h2><button class="btn btn-outline btn-sm" onclick="loadCosts()">Refresh</button></div>
  <div class="content" id="costsContent"></div>
</div>

<div class="page" id="page-keys">
  <div class="topbar"><h2>API Keys</h2></div>
  <div class="content">
    <div class="card">
      <div class="card-title">Create Key</div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Name</label><input id="keyName" placeholder="my-application"></div>
        <div class="form-group"><label class="form-label">Agent ID (optional)</label><input id="keyAgent" placeholder="agent-uuid"></div>
      </div>
      <button class="btn btn-accent" onclick="createKey()">Generate Key</button>
      <div id="keyResult" style="margin-top:8px"></div>
    </div>
    <div class="card"><div class="card-title">Active Keys</div><div id="keysList"></div></div>
  </div>
</div>

<div class="page" id="page-settings">
  <div class="topbar"><h2>Settings</h2></div>
  <div class="content">
    <div class="card">
      <div class="card-title">Create Agent</div>
      <div class="form-group"><label class="form-label">Name</label><input id="sAgentName" placeholder="Research Assistant"></div>
      <div class="form-group"><label class="form-label">System Prompt</label><textarea id="sAgentPrompt" rows="3">You are a helpful assistant.</textarea></div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Provider</label><select id="sAgentProvider"></select></div>
        <div class="form-group"><label class="form-label">Model (empty for default)</label><input id="sAgentModel" placeholder="llama3.3"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Temperature</label><input id="sAgentTemp" type="number" value="0.7" min="0" max="2" step="0.1"></div>
        <div class="form-group"><label class="form-label">Max Tokens</label><input id="sAgentMaxTok" type="number" value="4096" min="100" max="128000"></div>
      </div>
      <button class="btn btn-accent" onclick="createAgentFull()">Create Agent</button>
    </div>
    <div class="card"><div class="card-title">Provider Status</div><div id="providerStatus"></div></div>
  </div>
</div>

<div id="modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center">
  <div class="card" style="width:420px;max-width:90vw;margin:0">
    <div class="card-title">New Agent</div>
    <div class="form-group"><label class="form-label">Name</label><input id="nName" placeholder="My Agent"></div>
    <div class="form-group"><label class="form-label">System Prompt</label><textarea id="nPrompt">You are a helpful assistant.</textarea></div>
    <div class="form-group"><label class="form-label">Provider</label><select id="nProvider"></select></div>
    <div class="form-group"><label class="form-label">Model (empty for default)</label><input id="nModel"></div>
    <div style="display:flex;gap:8px;margin-top:16px">
      <button class="btn btn-accent" onclick="createAgentModal()">Create</button>
      <button class="btn btn-outline" onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

</div>
<script>
let cur=null,convId=null;
const $=id=>document.getElementById(id);

document.querySelectorAll('.nav-item').forEach(el=>{
  el.addEventListener('click',()=>showPage(el.dataset.page));
});

function showPage(name){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(t=>t.classList.remove('active'));
  const page=$('page-'+name);if(page)page.classList.add('active');
  const tabs=document.querySelectorAll('.nav-item');
  const idx=['chat','models','router','arena','costs','keys','settings'].indexOf(name);
  if(idx>=0&&tabs[idx])tabs[idx].classList.add('active');
  if(name==='models')loadModels();
  if(name==='costs')loadCosts();
  if(name==='keys')loadKeys();
  if(name==='settings')loadProviders();
}

async function loadAgents(){
  const r=await fetch('/api/agents');const agents=await r.json();
  $('agentList').innerHTML=agents.map(a=>`<div class="agent-item ${cur?.id===a.id?'active':''}" onclick="selectAgent('${a.id}')"><div class="agent-name">${a.name}</div><div class="agent-meta">${a.provider} / ${a.model||'default'}</div></div>`).join('')||'<div style="padding:8px 12px;font-size:12px;color:var(--muted)">No agents yet</div>';
  const pr=await fetch('/api/providers');const providers=await pr.json();
  const opts=providers.map(p=>`<option value="${p.name}">${p.name}${p.configured?'':'  (not configured)'}</option>`).join('');
  ['nProvider','sAgentProvider'].forEach(id=>{const el=$(id);if(el)el.innerHTML=opts;});
}

async function selectAgent(id){
  const r=await fetch('/api/agents/'+id);cur=await r.json();convId=null;
  $('chatTitle').textContent=cur.name;$('messages').innerHTML='';$('chatInput').style.display='flex';$('statsBar').style.display='flex';
  $('chatActions').innerHTML=`<button class="btn btn-danger btn-sm" onclick="deleteAgent('${id}')">Delete</button>`;
  showPage('chat');loadAgents();
}

async function deleteAgent(id){if(!confirm('Delete this agent?'))return;await fetch('/api/agents/'+id,{method:'DELETE'});cur=null;$('chatTitle').textContent='Select an agent';$('messages').innerHTML='<div class="empty">Select or create an agent</div>';$('chatInput').style.display='none';$('statsBar').style.display='none';$('chatActions').innerHTML='';loadAgents();}

function openModal(){$('modal').style.display='flex';loadAgents();}
function closeModal(){$('modal').style.display='none';}

async function createAgentModal(){
  const body={name:$('nName').value,system_prompt:$('nPrompt').value,provider:$('nProvider').value,model:$('nModel').value};
  if(!body.name)return;await fetch('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});closeModal();$('nName').value='';loadAgents();
}

async function createAgentFull(){
  const body={name:$('sAgentName').value,system_prompt:$('sAgentPrompt').value,provider:$('sAgentProvider').value,model:$('sAgentModel').value,temperature:parseFloat($('sAgentTemp').value),max_tokens:parseInt($('sAgentMaxTok').value)};
  if(!body.name)return;await fetch('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('sAgentName').value='';loadAgents();
}

async function sendMessage(){
  const input=$('userMsg');const msg=input.value.trim();if(!msg||!cur)return;input.value='';
  const msgs=$('messages');msgs.innerHTML+=`<div class="bubble bubble-user">${esc(msg)}</div><div class="bubble bubble-system">Processing...</div>`;msgs.scrollTop=msgs.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:cur.id,message:msg,conversation_id:convId})});
    const data=await r.json();convId=data.conversation_id;
    msgs.querySelector('.bubble-system:last-child')?.remove();
    msgs.innerHTML+=`<div class="bubble bubble-assistant">${esc(data.response).replace(/\\n/g,'<br>')}</div>`;
    const s=data.stats;$('statCalls').textContent=s.llm_calls;$('statTools').textContent=s.tool_executions;$('statTokens').textContent=s.tokens_in+s.tokens_out;$('statCost').textContent='$'+s.cost_usd.toFixed(4);$('statLatency').textContent=s.latency_ms+'ms';
  }catch(e){msgs.querySelector('.bubble-system:last-child')?.remove();msgs.innerHTML+=`<div class="bubble bubble-system" style="color:var(--red)">Error: ${e.message}</div>`;}
  msgs.scrollTop=msgs.scrollHeight;
}

async function loadModels(){
  const r=await fetch('/api/models');const models=await r.json();
  $('modelsList').innerHTML=`<table><thead><tr><th>#</th><th>Model</th><th>Intelligence</th><th>Context</th><th>Speed</th><th>Cost (in / out per 1M)</th><th>Capabilities</th></tr></thead><tbody>${
    models.map((m,i)=>`<tr><td style="color:var(--accent2);font-weight:700">${i+1}</td><td style="font-weight:600">${m.model}</td><td><span class="tag ${m.intelligence>=60?'tag-green':m.intelligence>=50?'tag-blue':m.intelligence>=40?'tag-amber':'tag-gray'}">${m.intelligence}</span></td><td>${fmtCtx(m.context_window)}</td><td><span class="tag ${m.speed_tier==='ultra'?'tag-green':m.speed_tier==='fast'?'tag-blue':'tag-gray'}">${m.speed_tier}</span></td><td style="font-variant-numeric:tabular-nums">$${m.cost_in_per_m} / $${m.cost_out_per_m}</td><td>${m.vision?'<span class="tag tag-purple" style="margin-right:4px">vision</span>':''}${m.tools?'<span class="tag tag-blue">tools</span>':''}</td></tr>`).join('')
  }</tbody></table>`;
}
function fmtCtx(n){if(n>=1e6)return(n/1e6).toFixed(n%1e6===0?0:1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return n;}

async function analyzePrompt(){
  const body={prompt:$('routerPrompt').value,priority:$('routerPriority').value,vision:$('routerVision').checked,privacy:$('routerPrivacy').checked};
  if(!body.prompt)return;
  const r=await fetch('/api/router',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  $('routerResult').innerHTML=`<div class="router-result"><div class="router-model">${d.provider} / ${d.model}</div><div class="router-reason">${d.reason}</div><div class="router-meta"><span>Intelligence: <b>${d.intelligence}/100</b></span><span>Speed: <b>${d.speed_tier}</b></span><span>Cost tier: <b>${d.cost_tier}</b></span><span>Est. $${d.estimated_cost_per_1k_tokens}/1K tokens</span></div></div>`;
}

async function runArena(){
  const prompt=$('arenaPrompt').value;if(!prompt)return;
  const provStr=$('arenaProviders').value;const providers=provStr?provStr.split(',').map(s=>s.trim()):[];
  $('arenaResult').innerHTML='<div class="bubble bubble-system">Running benchmark...</div>';
  try{
    const r=await fetch('/api/arena',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,providers})});
    const d=await r.json();
    $('arenaResult').innerHTML=`<table><thead><tr><th>#</th><th>Provider</th><th>Model</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>${
      d.results.map((r,i)=>`<tr><td style="font-weight:700;color:${i===0?'var(--green)':'var(--muted)'}">${i+1}</td><td>${r.provider}</td><td style="font-weight:600">${r.model}</td><td style="font-variant-numeric:tabular-nums">${r.latency_ms}ms</td><td style="font-variant-numeric:tabular-nums">${r.tokens_in+r.tokens_out}</td><td style="font-variant-numeric:tabular-nums">$${r.cost_usd.toFixed(4)}</td></tr>`).join('')
    }</tbody></table><div style="margin-top:16px"><div style="font-size:13px;font-weight:600;margin-bottom:8px">Responses</div>${
      d.results.map(r=>`<div class="card"><div style="font-size:11px;color:var(--muted);margin-bottom:4px">${r.provider} / ${r.model} &middot; ${r.latency_ms}ms</div><div style="font-size:13px">${esc(r.response).substring(0,300).replace(/\\n/g,'<br>')}${r.response.length>300?'...':''}</div></div>`).join('')
    }</div>`;
  }catch(e){$('arenaResult').innerHTML=`<div class="bubble bubble-system" style="color:var(--red)">Error: ${e.message}</div>`;}
}

async function loadCosts(){
  const r=await fetch('/api/costs');const d=await r.json();
  if(d.total_requests===0){$('costsContent').innerHTML='<div class="empty">No usage data yet. Chat with an agent to generate data.</div>';return;}
  $('costsContent').innerHTML=`<div class="grid grid-4" style="margin-bottom:16px"><div class="card stat-card"><div class="stat-value" style="color:var(--green)">$${d.total_cost.toFixed(4)}</div><div class="stat-label">Total Cost</div></div><div class="card stat-card"><div class="stat-value" style="color:var(--accent2)">${d.total_requests}</div><div class="stat-label">Requests</div></div><div class="card stat-card"><div class="stat-value" style="color:var(--blue)">$${d.potential_savings.toFixed(4)}</div><div class="stat-label">Potential Savings</div></div><div class="card stat-card"><div class="stat-value" style="color:var(--amber)">${d.savings_pct}%</div><div class="stat-label">Optimization</div></div></div>${
    Object.entries(d.by_model).map(([m,v])=>`<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:13px">${m}</strong><span style="color:var(--green);font-weight:600;font-size:13px">$${v.cost.toFixed(4)}</span></div><div style="font-size:12px;color:var(--muted);margin-top:4px">${v.requests} requests &middot; avg $${v.avg_cost_per_request.toFixed(4)}/req &middot; avg ${v.avg_latency_ms}ms</div></div>`).join('')
  }${d.recommendations.length?`<div style="font-size:14px;font-weight:600;margin:16px 0 8px">Recommendations</div>${d.recommendations.map(r=>`<div class="card rec-card"><div style="font-weight:600;font-size:13px">${r.type==='model_downgrade'?'Switch to cheaper model':r.type==='enable_caching'?'Enable response caching':'Speed optimization'}</div><div style="font-size:12px;color:var(--text2);margin-top:4px">${r.reason}</div><div style="font-size:12px;color:var(--green);margin-top:4px;font-weight:500">Save $${r.potential_savings.toFixed(4)}</div></div>`).join('')}`:''}`;
}

async function loadKeys(){
  const r=await fetch('/api/keys');const keys=await r.json();
  $('keysList').innerHTML=keys.length?`<table><thead><tr><th>Name</th><th>Requests</th><th>Last Used</th><th>Status</th><th></th></tr></thead><tbody>${keys.map(k=>`<tr><td style="font-weight:500">${k.name}</td><td style="font-variant-numeric:tabular-nums">${k.request_count}</td><td style="font-size:12px">${k.last_used?new Date(k.last_used*1000).toLocaleString():'never'}</td><td><span class="tag ${k.enabled?'tag-green':'tag-red'}">${k.enabled?'active':'revoked'}</span></td><td><button class="btn btn-danger btn-sm" onclick="revokeKey('${k.name}')">Revoke</button></td></tr>`).join('')}</tbody></table>`:'<div style="font-size:13px;color:var(--muted)">No API keys created yet.</div>';
}

async function createKey(){
  const name=$('keyName').value;if(!name)return;
  const r=await fetch('/api/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,agent_id:$('keyAgent').value||null})});
  const d=await r.json();$('keyResult').innerHTML=`<div class="card" style="border-color:var(--green)"><div style="font-size:12px;font-weight:600;color:var(--green);margin-bottom:8px">Key generated successfully</div><div class="key-code">${d.key}</div><div style="font-size:11px;color:var(--red);margin-top:8px">Save this key now. It will not be displayed again.</div></div>`;$('keyName').value='';loadKeys();
}

async function revokeKey(name){if(!confirm('Revoke key "'+name+'"?'))return;await fetch('/api/keys/'+name,{method:'DELETE'});loadKeys();}

async function loadProviders(){
  const r=await fetch('/api/providers');const providers=await r.json();
  $('providerStatus').innerHTML=providers.map(p=>`<div class="provider-row"><span class="provider-name">${p.name}</span><span class="tag ${p.configured?'tag-green':'tag-gray'}">${p.configured?'configured':'not configured'}</span></div>`).join('');
}

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
loadAgents();
</script>
</body>
</html>
"""
