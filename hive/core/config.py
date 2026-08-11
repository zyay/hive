"""
Hive configuration — loads from environment variables.
Updated Aug 2026 with latest models and providers.
"""

import os


class Settings:
    # Server
    HOST: str = os.getenv("HIVE_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("HIVE_PORT", "8000"))

    # Default provider
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "ollama")

    # Ollama (local, free)
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.3")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    # Google Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")

    # Groq (fastest inference)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    # Mistral
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    MISTRAL_BASE_URL: str = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    # OpenRouter (1 key → 300+ models)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # xAI (Grok)
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_MODEL: str = os.getenv("XAI_MODEL", "grok-3-mini")
    XAI_BASE_URL: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")

    # DeepSeek
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    # LM Studio (local, OpenAI-compatible)
    LMSTUDIO_HOST: str = os.getenv("LMSTUDIO_HOST", "http://localhost:1234")
    LMSTUDIO_MODEL: str = os.getenv("LMSTUDIO_MODEL", "local-model")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///hive.db")

    # Provider registry
    PROVIDERS: dict = {
        "ollama": {"base_url": OLLAMA_HOST + "/v1", "api_key": "", "model": OLLAMA_MODEL, "type": "openai_compat"},
        "openai": {"base_url": OPENAI_BASE_URL, "api_key": OPENAI_API_KEY, "model": OPENAI_MODEL, "type": "openai_compat"},
        "anthropic": {"base_url": ANTHROPIC_BASE_URL, "api_key": ANTHROPIC_API_KEY, "model": ANTHROPIC_MODEL, "type": "anthropic"},
        "gemini": {"base_url": GEMINI_BASE_URL, "api_key": GEMINI_API_KEY, "model": GEMINI_MODEL, "type": "openai_compat"},
        "groq": {"base_url": GROQ_BASE_URL, "api_key": GROQ_API_KEY, "model": GROQ_MODEL, "type": "openai_compat"},
        "mistral": {"base_url": MISTRAL_BASE_URL, "api_key": MISTRAL_API_KEY, "model": MISTRAL_MODEL, "type": "openai_compat"},
        "openrouter": {"base_url": OPENROUTER_BASE_URL, "api_key": OPENROUTER_API_KEY, "model": OPENROUTER_MODEL, "type": "openai_compat"},
        "xai": {"base_url": XAI_BASE_URL, "api_key": XAI_API_KEY, "model": XAI_MODEL, "type": "openai_compat"},
        "deepseek": {"base_url": DEEPSEEK_BASE_URL, "api_key": DEEPSEEK_API_KEY, "model": DEEPSEEK_MODEL, "type": "openai_compat"},
        "lmstudio": {"base_url": LMSTUDIO_HOST + "/v1", "api_key": "", "model": LMSTUDIO_MODEL, "type": "openai_compat"},
    }

    # Cost per 1M tokens (input, output) in USD — Aug 2026 pricing
    PRICING: dict = {
        # OpenAI
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        # Anthropic
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-opus-4-20250514": (15.00, 75.00),
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        # Google
        "gemini-2.5-flash": (0.0, 0.0),  # free tier
        "gemini-2.5-pro": (0.0, 0.0),  # free tier
        "gemini-2.0-flash-exp": (0.0, 0.0),
        # Groq
        "llama-3.3-70b-versatile": (0.59, 0.79),
        "llama-3.1-8b-instant": (0.05, 0.08),
        # Mistral
        "mistral-large-latest": (2.00, 6.00),
        "mistral-small-latest": (0.10, 0.30),
        # xAI
        "grok-3": (3.00, 15.00),
        "grok-3-mini": (0.30, 0.50),
        # DeepSeek
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
        # OpenRouter (varies, using common models)
        "anthropic/claude-3.5-sonnet": (3.00, 15.00),
        "meta-llama/llama-3.3-70b-instruct": (0.59, 0.79),
        # Local (free)
        "llama3.3": (0.0, 0.0),
        "llama3.2": (0.0, 0.0),
        "llama-3.2-3b-instruct": (0.0, 0.0),
        "local-model": (0.0, 0.0),
    }

    # Model metadata — context windows, capabilities
    MODEL_INFO: dict = {
        "gpt-4.1": {"context": 1_047_576, "vision": True, "tools": True},
        "gpt-4.1-mini": {"context": 1_047_576, "vision": True, "tools": True},
        "gpt-4.1-nano": {"context": 1_047_576, "vision": True, "tools": True},
        "claude-sonnet-4-20250514": {"context": 200_000, "vision": True, "tools": True},
        "claude-opus-4-20250514": {"context": 200_000, "vision": True, "tools": True},
        "gemini-2.5-flash": {"context": 1_000_000, "vision": True, "tools": True},
        "gemini-2.5-pro": {"context": 2_000_000, "vision": True, "tools": True},
        "grok-3": {"context": 131_072, "vision": False, "tools": True},
        "grok-3-mini": {"context": 131_072, "vision": False, "tools": True},
        "deepseek-chat": {"context": 128_000, "vision": False, "tools": True},
        "deepseek-reasoner": {"context": 128_000, "vision": False, "tools": False},
        "llama-3.3-70b-versatile": {"context": 128_000, "vision": False, "tools": True},
        "mistral-large-latest": {"context": 128_000, "vision": True, "tools": True},
        "llama3.3": {"context": 128_000, "vision": False, "tools": True},
    }


settings = Settings()
