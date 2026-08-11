"""
Hive configuration — loads from environment variables.
Updated Aug 2026 with latest models from Artificial Analysis leaderboard.
"""

import os


class Settings:
    # Server
    HOST: str = os.getenv("HIVE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HIVE_PORT", "8000"))

    # Default provider
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "ollama")

    # ── Local (free) ──────────────────────────────────────────
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.3")
    LMSTUDIO_HOST: str = os.getenv("LMSTUDIO_HOST", "http://localhost:1234")
    LMSTUDIO_MODEL: str = os.getenv("LMSTUDIO_MODEL", "local-model")

    # ── Cloud providers ───────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    MISTRAL_BASE_URL: str = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_MODEL: str = os.getenv("XAI_MODEL", "grok-3-mini")
    XAI_BASE_URL: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")

    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///hive.db")

    # ── Provider registry ─────────────────────────────────────
    PROVIDERS: dict = {
        "ollama": {"base_url": OLLAMA_HOST + "/v1", "api_key": "", "model": OLLAMA_MODEL, "type": "openai_compat"},
        "lmstudio": {"base_url": LMSTUDIO_HOST + "/v1", "api_key": "", "model": LMSTUDIO_MODEL, "type": "openai_compat"},
        "openai": {"base_url": OPENAI_BASE_URL, "api_key": OPENAI_API_KEY, "model": OPENAI_MODEL, "type": "openai_compat"},
        "anthropic": {"base_url": ANTHROPIC_BASE_URL, "api_key": ANTHROPIC_API_KEY, "model": ANTHROPIC_MODEL, "type": "anthropic"},
        "gemini": {"base_url": GEMINI_BASE_URL, "api_key": GEMINI_API_KEY, "model": GEMINI_MODEL, "type": "openai_compat"},
        "groq": {"base_url": GROQ_BASE_URL, "api_key": GROQ_API_KEY, "model": GROQ_MODEL, "type": "openai_compat"},
        "mistral": {"base_url": MISTRAL_BASE_URL, "api_key": MISTRAL_API_KEY, "model": MISTRAL_MODEL, "type": "openai_compat"},
        "openrouter": {"base_url": OPENROUTER_BASE_URL, "api_key": OPENROUTER_API_KEY, "model": OPENROUTER_MODEL, "type": "openai_compat"},
        "xai": {"base_url": XAI_BASE_URL, "api_key": XAI_API_KEY, "model": XAI_MODEL, "type": "openai_compat"},
        "deepseek": {"base_url": DEEPSEEK_BASE_URL, "api_key": DEEPSEEK_API_KEY, "model": DEEPSEEK_MODEL, "type": "openai_compat"},
    }

    # ── Pricing per 1M tokens (input, output) USD — Aug 2026 ─
    PRICING: dict = {
        # Claude 5 family (Anthropic)
        "claude-opus-5-max": (15.00, 75.00),
        "claude-opus-5-xhigh": (10.00, 50.00),
        "claude-opus-5-high": (5.00, 25.00),
        "claude-fable-5": (3.00, 15.00),
        # Claude 4 family
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-opus-4-20250514": (15.00, 75.00),
        # Claude 3.5 family
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        # GPT-5.6 family (OpenAI)
        "gpt-5.6-sol-max": (10.00, 40.00),
        "gpt-5.6-luna-medium": (2.00, 8.00),
        "gpt-5.6-luna-low": (0.50, 2.00),
        # GPT-4.1 family
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        # Google Gemini
        "gemini-2.5-pro": (0.0, 0.0),
        "gemini-2.5-flash": (0.0, 0.0),
        "gemini-2.5-flash-lite": (0.0, 0.0),
        # Groq
        "llama-3.3-70b-versatile": (0.59, 0.79),
        "llama-3.1-8b-instant": (0.05, 0.08),
        # Speed champions (via OpenRouter/specialized providers)
        "celeris-1": (1.00, 3.00),
        "mercury-2": (0.80, 2.50),
        "ling-3.0-flash": (0.30, 1.00),
        # xAI
        "grok-3": (3.00, 15.00),
        "grok-3-mini": (0.30, 0.50),
        # DeepSeek
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
        # Open-weights (local/free)
        "kimi-k3-max": (0.0, 0.0),
        "llama-4-scout": (0.0, 0.0),
        "miMo-v2.5": (0.0, 0.0),
        # Mistral
        "mistral-large-latest": (2.00, 6.00),
        "mistral-small-latest": (0.10, 0.30),
        # OpenRouter
        "anthropic/claude-sonnet-4": (3.00, 15.00),
        # Local
        "llama3.3": (0.0, 0.0),
        "llama3.2": (0.0, 0.0),
        "local-model": (0.0, 0.0),
    }

    # ── Model metadata — Artificial Analysis Aug 2026 ─────────
    MODEL_INFO: dict = {
        # Claude 5 family — Intelligence Index: 63/100 (#1)
        "claude-opus-5-max": {"context": 200_000, "vision": True, "tools": True, "intelligence": 63, "speed_tier": "slow", "cost_tier": "premium"},
        "claude-opus-5-xhigh": {"context": 200_000, "vision": True, "tools": True, "intelligence": 63, "speed_tier": "slow", "cost_tier": "premium"},
        "claude-opus-5-high": {"context": 200_000, "vision": True, "tools": True, "intelligence": 61, "speed_tier": "medium", "cost_tier": "high"},
        "claude-fable-5": {"context": 200_000, "vision": True, "tools": True, "intelligence": 62, "speed_tier": "medium", "cost_tier": "medium"},
        # Claude 4 family
        "claude-sonnet-4-20250514": {"context": 200_000, "vision": True, "tools": True, "intelligence": 55, "speed_tier": "medium", "cost_tier": "medium"},
        "claude-opus-4-20250514": {"context": 200_000, "vision": True, "tools": True, "intelligence": 58, "speed_tier": "slow", "cost_tier": "premium"},
        # GPT-5.6 family
        "gpt-5.6-sol-max": {"context": 500_000, "vision": True, "tools": True, "intelligence": 61, "speed_tier": "medium", "cost_tier": "premium"},
        "gpt-5.6-luna-medium": {"context": 500_000, "vision": True, "tools": True, "intelligence": 52, "speed_tier": "fast", "cost_tier": "medium"},
        "gpt-5.6-luna-low": {"context": 500_000, "vision": True, "tools": True, "intelligence": 48, "speed_tier": "fast", "cost_tier": "budget"},
        # GPT-4.1 family
        "gpt-4.1": {"context": 1_047_576, "vision": True, "tools": True, "intelligence": 50, "speed_tier": "medium", "cost_tier": "medium"},
        "gpt-4.1-mini": {"context": 1_047_576, "vision": True, "tools": True, "intelligence": 45, "speed_tier": "fast", "cost_tier": "budget"},
        "gpt-4.1-nano": {"context": 1_047_576, "vision": True, "tools": True, "intelligence": 40, "speed_tier": "fast", "cost_tier": "budget"},
        # Google Gemini
        "gemini-2.5-pro": {"context": 2_000_000, "vision": True, "tools": True, "intelligence": 55, "speed_tier": "medium", "cost_tier": "free"},
        "gemini-2.5-flash": {"context": 1_000_000, "vision": True, "tools": True, "intelligence": 50, "speed_tier": "fast", "cost_tier": "free"},
        "gemini-2.5-flash-lite": {"context": 1_000_000, "vision": True, "tools": True, "intelligence": 42, "speed_tier": "ultra", "cost_tier": "free"},
        # Speed champions
        "celeris-1": {"context": 128_000, "vision": False, "tools": True, "intelligence": 45, "speed_tier": "ultra", "cost_tier": "medium"},
        "mercury-2": {"context": 128_000, "vision": False, "tools": True, "intelligence": 43, "speed_tier": "ultra", "cost_tier": "medium"},
        "ling-3.0-flash": {"context": 128_000, "vision": False, "tools": True, "intelligence": 40, "speed_tier": "fast", "cost_tier": "budget"},
        # xAI
        "grok-3": {"context": 131_072, "vision": False, "tools": True, "intelligence": 50, "speed_tier": "medium", "cost_tier": "medium"},
        "grok-3-mini": {"context": 131_072, "vision": False, "tools": True, "intelligence": 42, "speed_tier": "fast", "cost_tier": "budget"},
        # DeepSeek
        "deepseek-chat": {"context": 128_000, "vision": False, "tools": True, "intelligence": 48, "speed_tier": "fast", "cost_tier": "budget"},
        "deepseek-reasoner": {"context": 128_000, "vision": False, "tools": False, "intelligence": 55, "speed_tier": "slow", "cost_tier": "budget"},
        # Open-weights
        "kimi-k3-max": {"context": 128_000, "vision": False, "tools": True, "intelligence": 60, "speed_tier": "medium", "cost_tier": "free"},
        "llama-4-scout": {"context": 128_000, "vision": False, "tools": True, "intelligence": 45, "speed_tier": "fast", "cost_tier": "free"},
        "miMo-v2.5": {"context": 128_000, "vision": False, "tools": True, "intelligence": 48, "speed_tier": "fast", "cost_tier": "free"},
        # Groq
        "llama-3.3-70b-versatile": {"context": 128_000, "vision": False, "tools": True, "intelligence": 42, "speed_tier": "ultra", "cost_tier": "budget"},
        # Mistral
        "mistral-large-latest": {"context": 128_000, "vision": True, "tools": True, "intelligence": 45, "speed_tier": "medium", "cost_tier": "medium"},
        # Local
        "llama3.3": {"context": 128_000, "vision": False, "tools": True, "intelligence": 40, "speed_tier": "fast", "cost_tier": "free"},
    }


settings = Settings()
