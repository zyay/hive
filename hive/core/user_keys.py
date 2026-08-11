"""
Per-user API key management.
Each user can configure their own provider API keys.
Falls back to server-level keys if user has no key configured.
"""

import uuid
import time
import logging

from hive.core.db import get_connection
from hive.core.config import settings

logger = logging.getLogger(__name__)


async def set_key(user_id: str, provider: str, api_key: str, model: str = "") -> dict:
    """Store or update a user's API key for a provider."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM user_api_keys WHERE user_id = ? AND provider = ?",
        (user_id, provider)
    ).fetchone()

    now = time.time()
    if existing:
        conn.execute(
            "UPDATE user_api_keys SET api_key = ?, model = ?, updated_at = ? WHERE user_id = ? AND provider = ?",
            (api_key, model, now, user_id, provider)
        )
    else:
        key_id = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO user_api_keys (id, user_id, provider, api_key, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key_id, user_id, provider, api_key, model, now, now)
        )
    conn.commit()
    conn.close()
    return {"user_id": user_id, "provider": provider, "model": model}


async def get_key(user_id: str, provider: str) -> tuple[str, str]:
    """Get user's API key for a provider. Returns (api_key, model).
    Falls back to server-level config if user has no key."""
    conn = get_connection()
    row = conn.execute(
        "SELECT api_key, model FROM user_api_keys WHERE user_id = ? AND provider = ?",
        (user_id, provider)
    ).fetchone()
    conn.close()

    if row and row["api_key"]:
        return row["api_key"], row["model"] or ""

    # Fallback to server config
    cfg = settings.PROVIDERS.get(provider, {})
    return cfg.get("api_key", ""), cfg.get("model", "")


async def list_keys(user_id: str) -> list[dict]:
    """List all API keys configured by a user."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT provider, model, created_at FROM user_api_keys WHERE user_id = ? ORDER BY provider",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def delete_key(user_id: str, provider: str) -> bool:
    """Remove a user's API key for a provider."""
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?",
        (user_id, provider)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
