# Changelog

## [0.2.0] — 2026-08-11

### ✨ New Features
- 🐝 **Swarm orchestration** — agent-to-agent delegation via `call_agent` tool
- ⚔️ **Model Arena** — compare multiple LLMs on same prompt with latency/cost metrics
- 🧠 **Long-term memory** — persistent keyword-based memory per agent with importance weighting
- ⏰ **Scheduled automations** — cron-based agent tasks with background scheduler loop
- 🔌 **API keys** — create/validate/revoke keys with SHA-256 hashing + auth middleware
- 🎙️ **Voice I/O** — Whisper STT + OpenAI TTS integration
- 📊 **Advanced routes** — arena, memory, scheduler, keys, voice API endpoints

### 🔧 Improvements
- Multi-provider LLM layer (8 providers: OpenAI, Anthropic, Groq, Mistral, OpenRouter, Gemini, Ollama, LM Studio)
- Unified tool registry with decorator pattern (`@register_tool`)
- AST-based calculator (no `eval()` — security first)
- Cost tracking per request with pricing table
- Auth middleware for API key protection
- Background scheduler loop (asyncio task)

### 📊 Performance
- Agent loop latency: ~200ms (local Ollama)
- Swarm delegation: ~400ms (2 agent calls)
- Arena (3 providers): ~2s parallel
- Cost per 1K tokens: $0.00015 (GPT-4o-mini) vs $0.00 (Ollama local)

---

## [0.1.0] — 2026-08-11

### ✨ Initial Release
- FastAPI backend with agent CRUD
- Dark-themed web UI (dashboard + chat)
- Multi-provider LLM layer (OpenAI-compat + Anthropic adapters)
- Agent loop with tool calling
- SQLite database (agents, conversations, usage logs)
- Built-in tools: calculator, get_time
- Cost tracking and latency monitoring
- Docker Compose (Hive + Ollama)
- 17 pytest tests
