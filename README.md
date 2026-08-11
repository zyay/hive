# 🐝 Hive — Self-hosted Multi-Agent AI Platform

> **v0.2** — Swarm orchestration · Model Arena · Long-term memory · Scheduler · API keys · Voice I/O · 8 LLM providers

Create, manage, and chat with AI agents powered by **any LLM provider** — all running on your own machine.

## What is Hive?

Hive is a self-hosted platform for orchestrating AI agents. Each agent has its own personality (system prompt), model, and tools. You can create agents, chat with them, and monitor costs — all from a clean web UI.

**Key insight:** Instead of being locked into one AI provider, Hive lets you switch between 8+ providers with a single config change. Use Ollama for free local inference, OpenAI for quality, Groq for speed, or OpenRouter for access to 100+ models.

## Features

| Feature | Description |
|---|---|
| **Multi-provider LLM layer** | OpenAI, Anthropic, Groq, Mistral, OpenRouter, Gemini, Ollama — unified API |
| **Agent management** | Create, edit, delete agents with custom prompts, models, and tools |
| **Tool calling** | Built-in tools (calculator, time) + extensible tool registry |
| **Cost tracking** | Per-request cost estimation, token counting, latency monitoring |
| **Conversation memory** | Persistent conversations stored in SQLite |
| **Web UI** | Dark-themed dashboard with agent list, chat, and stats |
| **Docker Compose** | One command to run everything (Hive + Ollama) |
| **Self-hosted** | Your data, your keys, your infrastructure |

## Architecture

```
┌──────────────────┐
│   Web UI (hive)  │  dashboard: agents, chat, stats
└────────┬─────────┘
         │ HTTP
┌────────▼─────────────────────────────────┐
│          FastAPI backend (hive)          │
│  ┌──────────────┐   ┌─────────────────┐  │
│  │ Agent loop   │   │ Model layer     │  │
│  │ (tool call)  │   │ 8+ providers    │  │
│  └──────────────┘   └─────────────────┘  │
│  ┌──────────────┐   ┌─────────────────┐  │
│  │ SQLite DB    │   │ Tool registry   │  │
│  │ (agents,     │   │ (calculator,    │  │
│  │  convos,     │   │  time, custom)  │  │
│  │  usage)      │   └─────────────────┘  │
│  └──────────────┘                        │
└──────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Clone
git clone https://github.com/zyay/hive.git
cd hive

# 2. Set up
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env                            # edit with your API keys

# 3. Run
python main.py
# Open http://127.0.0.1:8000
```

### Or with Docker:

```bash
docker compose up --build
# Hive at http://localhost:8000, Ollama at http://localhost:11434
```

## Supported providers

| Provider | Type | Config |
|---|---|---|
| **Ollama** | 🏠 Local, free | `OLLAMA_HOST` |
| **OpenAI** | ☁️ Cloud | `OPENAI_API_KEY` |
| **Anthropic** | ☁️ Cloud | `ANTHROPIC_API_KEY` |
| **Groq** | ☁️ Fast inference | `GROQ_API_KEY` |
| **Mistral** | ☁️ Cloud | `MISTRAL_API_KEY` |
| **OpenRouter** | ☁️ 100+ models | `OPENROUTER_API_KEY` |
| **Gemini** | ☁️ Google | `GEMINI_API_KEY` |
| **LM Studio** | 🏠 Local | OpenAI-compatible endpoint |

All OpenAI-compatible providers share the same adapter — just change `base_url` and `api_key`.

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/api/providers` | GET | List configured providers |
| `/api/tools` | GET | List available tools |
| `/api/agents` | GET | List all agents |
| `/api/agents` | POST | Create agent |
| `/api/agents/{id}` | GET/PUT/DELETE | Agent CRUD |
| `/api/chat` | POST | Send message to agent |
| `/api/usage` | GET | Usage statistics |

### Example: create an agent and chat

```bash
# Create agent
curl -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "Researcher", "system_prompt": "You are a research assistant.", "provider": "ollama"}'

# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "abc123", "message": "What is retrieval-augmented generation?"}'
```

## Adding custom tools

```python
from hive.core.agent import register_tool

@register_tool(
    name="weather",
    description="Get current weather for a city",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
def get_weather(city: str) -> str:
    return f"Weather in {city}: 22°C, sunny"
```

## Design decisions

| Decision | Why |
|---|---|
| **Adapter pattern** | 2 adapters (OpenAI-compat + Anthropic) cover 8+ providers |
| **SQLite** | Zero-config, single-file, perfect for self-hosted |
| **Cost tracking** | Every request logged with tokens + estimated cost |
| **Tool registry** | Decorator-based — add tools with one function |
| **No external DB** | Everything runs locally, no dependencies |

## Roadmap

- [x] Multi-provider LLM layer (8 providers)
- [x] Agent management (CRUD + chat)
- [x] Tool calling with built-in tools
- [x] Cost tracking and observability
- [x] Swarm orchestration (agent-to-agent)
- [x] Model Arena (side-by-side comparison)
- [x] Long-term memory per agent
- [x] Scheduled automations (cron)
- [x] API keys + auth middleware
- [x] Voice I/O (Whisper + TTS)
- [x] MCP client integration
- [ ] Hive swarm visualization (graph view)
- [ ] RAG per agent (connect to rag-docs-assistant)
- [ ] Public marketplace for agent templates

## Performance

| Metric | Value |
|---|---|
| Agent loop latency | ~200ms (local Ollama) |
| Swarm delegation | ~400ms (2 agent calls) |
| Arena (3 providers) | ~2s parallel |
| Cost per 1K tokens | $0.00015 (GPT-4o-mini) vs $0.00 (Ollama) |
| Memory per agent | ~2KB (keyword-based) |
| DB size | ~1MB per 1000 conversations |

## Cross-repo integrations

Hive connects to your other projects via MCP:

```
hive ←→ mcp-agent-tools (19 tools: file, MySQL, web, calc, text)
hive ←→ mcp-rag-bridge (7 tools: query KB, add/update/delete docs)
hive ←→ rag-docs-assistant (RAG pipeline as a service)
```

Use `hive/core/mcp_client.py` to connect any MCP server:

```python
from hive.core.mcp_client import mcp_registry

# Register MCP servers
mcp_registry.register("agent-tools", "python", ["path/to/mcp-agent-tools/server.py"])
mcp_registry.register("rag-bridge", "python", ["path/to/mcp-rag-bridge/server.py"])

# Connect and discover tools
await mcp_registry.connect_all()
schemas = mcp_registry.get_all_tool_schemas()  # → all tools available to agents
```

## Related projects

- [rag-docs-assistant](https://github.com/zyay/rag-docs-assistant) — RAG pipeline with hybrid search, reranking, evals
- [mcp-agent-tools](https://github.com/zyay/mcp-agent-tools) — MCP server with 19 tools + sandbox
- [mcp-rag-bridge](https://github.com/zyay/mcp-rag-bridge) — MCP bridge for RAG knowledge bases

## License

MIT
