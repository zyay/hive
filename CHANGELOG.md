# Changelog

## [1.0.0] — 2026-08-16

### 🎉 Major Release — Production Ready

### New Features
- **RAG Pipeline** — Document upload, chunking, embedding, and retrieval-augmented generation
  - Supports PDF, TXT, MD, code files
  - ChromaDB vector storage with semantic search
  - API endpoints: `/api/rag/ingest`, `/api/rag/query`, `/api/rag/documents`
- **Agent Templates** — 8 pre-configured agent archetypes
  - Coding Assistant, Research Agent, Writer, Data Analyst, DevOps, Tutor, Knowledge Assistant, Creative Agent
  - API endpoints: `/api/templates`, `/api/templates/create`
- **Web Search Tool** — DuckDuckGo search (no API key required)
- **Code Execution Sandbox** — Safe Python code execution in subprocess
- **Image Generation** — DALL-E 3 integration via OpenAI API
- **URL Fetcher** — Extract text content from any URL
- **World Clock** — Multi-timezone time display

### UI/UX Overhaul
- **Dark/Light Theme** — System preference detection + manual toggle
- **Mobile Responsive** — Bottom navigation, adaptive layouts
- **Enhanced Markdown** — Full GFM support with code syntax highlighting (highlight.js)
- **Conversation Export** — Export as JSON or Markdown
- **Toast Notifications** — Real-time feedback for all actions
- **Agent Builder** — Temperature slider, max tokens, model selection
- **Profile Section** — User avatar, name display in settings

### Architecture
- **Async Database** — Migrated from sync sqlite3 to aiosqlite (non-blocking)
- **Migration System** — Versioned schema migrations (v1→v2→v3)
- **WAL Mode** — Write-Ahead Logging for better concurrent performance
- **Proper Resource Cleanup** — try/finally blocks on all DB connections

### Infrastructure
- **CI/CD Pipeline** — GitHub Actions with lint, test, build, Docker jobs
- **Multi-stage Docker** — Smaller images, non-root user, health checks
- **Docker Compose** — Health checks, restart policies, proper volume mounts
- **Code Coverage** — pytest-cov integration with Codecov upload

### Improvements
- Structured logging throughout
- Better error messages and HTTP status codes
- Input validation on all endpoints
- Rate limiting on auth endpoints
- Security headers and CORS configuration

---

## [0.3.0] — 2026-08-11

### New Features
- Vector memory — ChromaDB + sentence-transformers semantic recall per agent
- SSE streaming — real-time token streaming via /api/chat/stream
- JWT authentication — zero-dependency HMAC-SHA256 token create/verify
- Full cron parser — 5-field cron with ranges, steps, commas
- Prometheus metrics — counters, histograms, gauges + text export
- MCP integrations — connect to mcp-agent-tools and mcp-rag-bridge
- Benchmark suite — automated evaluation (reasoning, coding, factual, creative)

### New Endpoints
- POST /api/chat/stream, /api/memory/vector, /api/auth/token
- GET /api/auth/verify, /api/metrics, /api/metrics/prometheus
- POST /api/cron/next, /api/integrations/discover, /api/integrations/call
- POST /api/benchmark/run, GET /api/benchmark/categories

### Tests: 97 pytest tests

---

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
