"""
Hive configuration — loads from environment variables.
"""

import os


class Settings:
    # Server
    HOST: str = os.getenv("HIVE_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("HIVE_PORT", "8000"))

    # Default provider
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "ollama")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # OpenAI-compatible providers (OpenAI, Groq, Mistral, OpenRouter, Gemini, LM Studio)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    MISTRAL_BASE_URL: str = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")

    # Anthropic (non-OpenAI-compatible)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///hive.db")

    # Provider registry: maps provider name → (base_url, api_key_env, default_model)
    PROVIDERS: dict = {
        "ollama": {"base_url": OLLAMA_HOST + "/v1", "api_key": "", "model": OLLAMA_MODEL, "type": "openai_compat"},
        "openai": {"base_url": OPENAI_BASE_URL, "api_key": OPENAI_API_KEY, "model": OPENAI_MODEL, "type": "openai_compat"},
        "groq": {"base_url": GROQ_BASE_URL, "api_key": GROQ_API_KEY, "model": GROQ_MODEL, "type": "openai_compat"},
        "mistral": {"base_url": MISTRAL_BASE_URL, "api_key": MISTRAL_API_KEY, "model": MISTRAL_MODEL, "type": "openai_compat"},
        "openrouter": {"base_url": OPENROUTER_BASE_URL, "api_key": OPENROUTER_API_KEY, "model": OPENROUTER_MODEL, "type": "openai_compat"},
        "gemini": {"base_url": GEMINI_BASE_URL, "api_key": GEMINI_API_KEY, "model": GEMINI_MODEL, "type": "openai_compat"},
        "anthropic": {"base_url": "https://api.anthropic.com", "api_key": ANTHROPIC_API_KEY, "model": ANTHROPIC_MODEL, "type": "anthropic"},
    }

    # Cost per 1M tokens (input, output) in USD
    PRICING: dict = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "llama-3.3-70b-versatile": (0.59, 0.79),
        "llama3.2": (0.0, 0.0),
        "llama-3.2-3b-instruct": (0.0, 0.0),
        "mistral-small-latest": (0.10, 0.30),
        "gemini-2.0-flash-exp": (0.0, 0.0),
    }


settings = Settings()
