# 🐝 Hive — Self-hosted Multi-Agent AI Platform

> **v0.2** — Swarm orchestration · Model Arena · Long-term memory · Scheduler · API keys · Voice I/O · 8 LLM providers · MCP integration

Create, manage, and chat with AI agents powered by **any LLM provider** — all running on your own machine. Agents can delegate to each other, compare models side-by-side, remember across sessions, and run on schedule.

## What is Hive?

Hive is a self-hosted platform for orchestrating AI agents. Each agent has its own personality (system prompt), model, and tools. You can create agents, chat with them, and monitor costs — all from a clean web UI.

**Key insight:** Instead of being locked into one AI provider, Hive lets you switch between 8+ providers with a single config change. Use Ollama for free local inference, OpenAI for quality, Groq for speed, or OpenRouter for access to 100+ models.

## Features

### Core
| Feature | Description |
|---|---|
| **Multi-provider LLM layer** | 8 providers via 2 adapters (OpenAI-compat + Anthropic native) |
| **Agent management** | Create, edit, delete agents with custom prompts, models, and tools |
| **Tool calling** | Built-in tools + extensible `@register_tool` decorator |
| **Cost tracking** | Per-request cost estimation, token counting, latency monitoring |
| **Conversation memory** | Persistent conversations in SQLite |
| **Web UI** | Dark-themed dashboard with agent list, chat, and live stats |
| **Docker Compose** | One command: `docker compose up` |

### Advanced (v0.2)
| Feature | Description |
|---|---|
| **🐝 Swarm orchestration** | Agent-to-agent delegation via `call_agent` tool |
| **⚔️ Model Arena** | Compare N models on same prompt — latency, cost, response side-by-side |
| **🧠 Long-term memory** | Persistent keyword-based memory per agent with importance weighting |
| **⏰ Scheduled automations** | Cron-based agent tasks with background scheduler loop |
| **🔌 API keys + auth** | Create/revoke API keys, SHA-256 hashed, auth middleware |
| **🎙️ Voice I/O** | Whisper STT + OpenAI TTS integration |
| **🔗 MCP integration** | Connect to any MCP server (mcp-agent-tools, mcp-rag-bridge) |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Web UI (dark dashboard)                  │
│         agents · chat · arena · memory · stats               │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼───────────────────────────────────┐
│                    FastAPI backend (hive)                     │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Agent loop  │  │ Model layer  │  │ Swarm              │  │
│  │ (tool call, │  │ 8 providers  │  │ (call_agent,       │  │
│  │  multi-turn)│  │ 2 adapters   │  │  list_hive_agents) │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Arena       │  │ Memory       │  │ Scheduler          │  │
│  │ (parallel   │  │ (per-agent   │  │ (cron tasks,       │  │
│  │  comparison)│  │  recall)     │  │  background loop)  │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Voice I/O   │  │ API keys     │  │ MCP client         │  │
│  │ (Whisper +  │  │ (SHA-256,    │  │ (connect to any    │  │
│  │  TTS)       │  │  auth)       │  │  MCP server)       │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ SQLite (agents, conversations, usage, memory, keys)  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Clone
git clone https://github.com/zyay/hive.git
cd hive

# 2. Set up
python -m venv venv && venv\Scripts\activate   # Windows
# source venv/bin/activate                      # macOS/Linux
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

| Provider | Type | Config | Cost |
|---|---|---|---|
| **Ollama** | 🏠 Local, free | `OLLAMA_HOST` | $0 |
| **LM Studio** | 🏠 Local | OpenAI-compat endpoint | $0 |
| **OpenAI** | ☁️ Cloud | `OPENAI_API_KEY` | $0.15-10/M tokens |
| **Anthropic** | ☁️ Cloud | `ANTHROPIC_API_KEY` | $0.80-15/M tokens |
| **Groq** | ☁️ Fast inference | `GROQ_API_KEY` | $0.59-0.79/M tokens |
| **Mistral** | ☁️ Cloud | `MISTRAL_API_KEY` | $0.10-0.30/M tokens |
| **OpenRouter** | ☁️ 100+ models | `OPENROUTER_API_KEY` | varies |
| **Gemini** | ☁️ Google | `GEMINI_API_KEY` | free tier |

All OpenAI-compatible providers share the same adapter — just change `base_url` and `api_key`.

## API reference

### Core endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/api/providers` | GET | List configured providers |
| `/api/tools` | GET | List available tools |
| `/api/agents` | GET/POST | List / create agents |
| `/api/agents/{id}` | GET/PUT/DELETE | Agent CRUD |
| `/api/chat` | POST | Send message to agent |
| `/api/usage` | GET | Usage statistics |

### v0.2 endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/arena` | POST | Compare models side-by-side |
| `/api/memory/{agent_id}` | GET/POST/DELETE | Agent memory CRUD |
| `/api/memory/{agent_id}/recall` | GET | Semantic recall |
| `/api/schedule` | GET/POST | List / create scheduled tasks |
| `/api/schedule/{id}` | DELETE | Remove scheduled task |
| `/api/keys` | GET/POST | List / create API keys |
| `/api/voice/transcribe` | POST | Speech-to-text |
| `/api/voice/synthesize` | POST | Text-to-speech |

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

# Model Arena — compare 3 providers
curl -X POST http://localhost:8000/api/arena \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain quantum computing in 3 sentences", "providers": ["ollama", "openai", "groq"]}'
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

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest --cov=hive --cov-report=html
```

**Test coverage:** 17 tests covering config, agent loop, LLM layer, tool registry, cost estimation, providers.

## Performance

| Metric | Value |
|---|---|
| Agent loop latency | ~200ms (local Ollama) |
| Swarm delegation | ~400ms (2 agent calls) |
| Arena (3 providers) | ~2s parallel |
| Cost per 1K tokens | $0.00015 (GPT-4o-mini) vs $0.00 (Ollama) |
| Memory per agent | ~2KB (keyword-based) |
| DB size | ~1MB per 1000 conversations |
| Startup time | <1s |

## Cross-repo integrations

Hive connects to your other projects via MCP:

```
hive ←→ mcp-agent-tools (19 tools: file, MySQL, web, calc, text)
hive ←→ mcp-rag-bridge (7 tools: query KB, add/update/delete docs)
hive ←→ rag-docs-assistant (RAG pipeline as a service)
```

```python
from hive.core.mcp_client import mcp_registry

# Register MCP servers
mcp_registry.register("agent-tools", "python", ["path/to/mcp-agent-tools/server.py"])
mcp_registry.register("rag-bridge", "python", ["path/to/mcp-rag-bridge/server.py"])

# Connect and discover tools
await mcp_registry.connect_all()
schemas = mcp_registry.get_all_tool_schemas()  # → all tools available to agents
```

## Design decisions

| Decision | Why |
|---|---|
| **Adapter pattern** | 2 adapters (OpenAI-compat + Anthropic) cover 8+ providers |
| **SQLite** | Zero-config, single-file, perfect for self-hosted |
| **Cost tracking** | Every request logged with tokens + estimated cost |
| **Tool registry** | Decorator-based — add tools with one function |
| **AST calculator** | No `eval()` — security-first math evaluation |
| **Keyword memory** | Simple, fast, no embedding model needed for recall |
| **Background scheduler** | asyncio task — no external cron daemon needed |
| **SHA-256 API keys** | Raw keys shown once, only hashes stored |

## Roadmap (v0.3)

- [ ] Hive swarm visualization (graph view of agent calls)
- [ ] RAG per agent (native ChromaDB integration)
- [ ] Advanced evals framework (automated agent quality scoring)
- [ ] Multi-user support with auth
- [ ] Public marketplace for agent templates
- [ ] Streaming responses (SSE)

## Related projects

- [rag-docs-assistant](https://github.com/zyay/rag-docs-assistant) — RAG pipeline with hybrid search, reranking, evals, 27 tests
- [mcp-agent-tools](https://github.com/zyay/mcp-agent-tools) — MCP server with 19 tools, sandbox, rate limiting, security audit
- [mcp-rag-bridge](https://github.com/zyay/mcp-rag-bridge) — MCP bridge for RAG knowledge bases, 7 tools

## License

MIT
