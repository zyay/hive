# 🐝 Hive — Self-hosted Multi-Agent AI Platform

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

- [ ] MCP client integration (connect to mcp-agent-tools)
- [ ] RAG per agent (connect to rag-docs-assistant)
- [ ] Hive swarm (`call_agent` tool for agent-to-agent delegation)
- [ ] Model Arena (compare N models on same prompt)
- [ ] Voice I/O (Whisper STT + TTS)
- [ ] Public API with API keys
- [ ] Scheduled automations (cron agents)

## Related projects

- [rag-docs-assistant](https://github.com/zyay/rag-docs-assistant) — RAG pipeline with hybrid search
- [mcp-agent-tools](https://github.com/zyay/mcp-agent-tools) — MCP server with 19 tools
- [mcp-rag-bridge](https://github.com/zyay/mcp-rag-bridge) — MCP bridge for RAG

## License

MIT
