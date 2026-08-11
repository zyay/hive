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
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0a0a0a; --surface: #141414; --border: #222; --text: #e0e0e0; --muted: #888; --accent: #f59e0b; --green: #10b981; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); height: 100vh; display: flex; }
  .sidebar { width: 280px; border-right: 1px solid var(--border); display: flex; flex-direction: column; background: var(--surface); }
  .sidebar-header { padding: 1rem; border-bottom: 1px solid var(--border); }
  .sidebar-header h1 { font-size: 1.3rem; }
  .sidebar-header h1 span { color: var(--accent); }
  .agent-list { flex: 1; overflow-y: auto; padding: 0.5rem; }
  .agent-item { padding: 0.75rem; border-radius: 8px; cursor: pointer; margin-bottom: 0.25rem; transition: background 0.15s; }
  .agent-item:hover { background: #1a1a1a; }
  .agent-item.active { background: #1a1a1a; border: 1px solid var(--accent); }
  .agent-item .name { font-weight: 600; font-size: 0.9rem; }
  .agent-item .meta { font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }
  .btn { padding: 0.5rem 1rem; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: all 0.15s; }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-primary:hover { background: #d97706; }
  .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.75rem; }
  .btn-danger { background: #dc2626; color: #fff; }
  .main { flex: 1; display: flex; flex-direction: column; }
  .chat-header { padding: 1rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .chat-header h2 { font-size: 1.1rem; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .msg { max-width: 80%; padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.9rem; line-height: 1.5; }
  .msg-user { align-self: flex-end; background: #1e3a5f; border-bottom-right-radius: 4px; }
  .msg-assistant { align-self: flex-start; background: var(--surface); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .msg-tool { align-self: flex-start; background: #1a1a0a; border: 1px solid #333; font-size: 0.8rem; font-family: monospace; }
  .msg-system { align-self: center; color: var(--muted); font-size: 0.8rem; font-style: italic; }
  .chat-input { padding: 1rem; border-top: 1px solid var(--border); display: flex; gap: 0.5rem; }
  .chat-input input { flex: 1; padding: 0.75rem; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); font-size: 0.9rem; outline: none; }
  .chat-input input:focus { border-color: var(--accent); }
  .stats-bar { display: flex; gap: 1rem; padding: 0.5rem 1rem; border-top: 1px solid var(--border); font-size: 0.75rem; color: var(--muted); }
  .stat { display: flex; gap: 0.3rem; }
  .stat .val { color: var(--green); font-weight: 600; }
  .empty { display: flex; align-items: center; justify-content: center; flex: 1; color: var(--muted); font-size: 1.1rem; }
  .new-agent-form { padding: 1rem; display: none; flex-direction: column; gap: 0.5rem; border-bottom: 1px solid var(--border); }
  .new-agent-form.show { display: flex; }
  .new-agent-form input, .new-agent-form textarea, .new-agent-form select { padding: 0.5rem; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); font-size: 0.85rem; }
  .new-agent-form textarea { min-height: 60px; resize: vertical; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header">
    <h1>🐝 <span>Hive</span></h1>
    <p style="font-size:0.75rem;color:var(--muted);margin-top:0.25rem;">Multi-agent AI platform</p>
  </div>
  <div style="padding:0.5rem;">
    <button class="btn btn-primary" style="width:100%;" onclick="toggleNewAgent()">+ New Agent</button>
  </div>
  <div class="new-agent-form" id="newAgentForm">
    <input id="newName" placeholder="Agent name">
    <textarea id="newPrompt" placeholder="System prompt...">You are a helpful assistant.</textarea>
    <select id="newProvider">
      <option value="ollama">Ollama (local)</option>
      <option value="openai">OpenAI</option>
      <option value="anthropic">Anthropic</option>
      <option value="groq">Groq</option>
      <option value="mistral">Mistral</option>
      <option value="openrouter">OpenRouter</option>
      <option value="gemini">Gemini</option>
    </select>
    <input id="newModel" placeholder="Model (leave empty for default)">
    <button class="btn btn-primary" onclick="createAgent()">Create</button>
  </div>
  <div class="agent-list" id="agentList"></div>
</div>
<div class="main">
  <div class="chat-header">
    <h2 id="chatTitle">Select an agent</h2>
    <div id="chatActions"></div>
  </div>
  <div class="chat-messages" id="messages">
    <div class="empty">🐝 Select or create an agent to start chatting</div>
  </div>
  <div class="stats-bar" id="statsBar" style="display:none;">
    <div class="stat">LLM calls: <span class="val" id="statCalls">0</span></div>
    <div class="stat">Tools: <span class="val" id="statTools">0</span></div>
    <div class="stat">Tokens: <span class="val" id="statTokens">0</span></div>
    <div class="stat">Cost: <span class="val" id="statCost">$0</span></div>
    <div class="stat">Latency: <span class="val" id="statLatency">0ms</span></div>
  </div>
  <div class="chat-input" id="chatInput" style="display:none;">
    <input id="userMsg" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendMessage()">
    <button class="btn btn-primary" onclick="sendMessage()">Send</button>
  </div>
</div>
<script>
let currentAgent = null;
let conversationId = null;

async function loadAgents() {
  const r = await fetch('/api/agents');
  const agents = await r.json();
  const list = document.getElementById('agentList');
  list.innerHTML = agents.map(a => `
    <div class="agent-item ${currentAgent?.id === a.id ? 'active' : ''}" onclick="selectAgent('${a.id}')">
      <div class="name">${a.name}</div>
      <div class="meta">${a.provider} · ${a.model || 'default'}</div>
    </div>
  `).join('');
}

async function selectAgent(id) {
  const r = await fetch('/api/agents/' + id);
  currentAgent = await r.json();
  conversationId = null;
  document.getElementById('chatTitle').textContent = currentAgent.name;
  document.getElementById('messages').innerHTML = '';
  document.getElementById('chatInput').style.display = 'flex';
  document.getElementById('statsBar').style.display = 'flex';
  document.getElementById('chatActions').innerHTML = `<button class="btn btn-danger btn-sm" onclick="deleteAgent('${id}')">Delete</button>`;
  loadAgents();
}

async function createAgent() {
  const body = {
    name: document.getElementById('newName').value,
    system_prompt: document.getElementById('newPrompt').value,
    provider: document.getElementById('newProvider').value,
    model: document.getElementById('newModel').value,
  };
  if (!body.name) return;
  await fetch('/api/agents', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  document.getElementById('newAgentForm').classList.remove('show');
  document.getElementById('newName').value = '';
  loadAgents();
}

async function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  await fetch('/api/agents/' + id, { method: 'DELETE' });
  currentAgent = null;
  document.getElementById('chatTitle').textContent = 'Select an agent';
  document.getElementById('messages').innerHTML = '<div class="empty">🐝 Select or create an agent</div>';
  document.getElementById('chatInput').style.display = 'none';
  document.getElementById('statsBar').style.display = 'none';
  document.getElementById('chatActions').innerHTML = '';
  loadAgents();
}

function toggleNewAgent() {
  document.getElementById('newAgentForm').classList.toggle('show');
}

async function sendMessage() {
  const input = document.getElementById('userMsg');
  const msg = input.value.trim();
  if (!msg || !currentAgent) return;
  input.value = '';

  const msgs = document.getElementById('messages');
  msgs.innerHTML += `<div class="msg msg-user">${escHtml(msg)}</div>`;
  msgs.innerHTML += `<div class="msg msg-system">Thinking...</div>`;
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ agent_id: currentAgent.id, message: msg, conversation_id: conversationId })
    });
    const data = await r.json();
    conversationId = data.conversation_id;

    // Remove "Thinking..."
    const thinking = msgs.querySelector('.msg-system:last-child');
    if (thinking) thinking.remove();

    msgs.innerHTML += `<div class="msg msg-assistant">${escHtml(data.response).replace(/\\n/g,'<br>')}</div>`;

    // Update stats
    const s = data.stats;
    document.getElementById('statCalls').textContent = s.llm_calls;
    document.getElementById('statTools').textContent = s.tool_executions;
    document.getElementById('statTokens').textContent = s.tokens_in + s.tokens_out;
    document.getElementById('statCost').textContent = '$' + s.cost_usd.toFixed(4);
    document.getElementById('statLatency').textContent = s.latency_ms + 'ms';
  } catch(e) {
    const thinking = msgs.querySelector('.msg-system:last-child');
    if (thinking) thinking.remove();
    msgs.innerHTML += `<div class="msg msg-system" style="color:#dc2626;">Error: ${e.message}</div>`;
  }
  msgs.scrollTop = msgs.scrollHeight;
}

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
loadAgents();
</script>
</body>
</html>
"""
