"""
API key management — authenticate external requests to the Hive API.
"""

import secrets
import time
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

API_KEYS_DB = Path("hive_apikeys.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(API_KEYS_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_api_keys():
    """Create API keys table."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            agent_id TEXT,
            created_at REAL NOT NULL,
            last_used REAL,
            request_count INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


def create_key(name: str, agent_id: str = None) -> str:
    """Create a new API key. Returns the raw key (shown only once)."""
    raw_key = f"hive_{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(raw_key)
    now = time.time()

    conn = get_conn()
    conn.execute(
        "INSERT INTO api_keys (key_hash, name, agent_id, created_at) VALUES (?, ?, ?, ?)",
        (key_hash, name, agent_id, now)
    )
    conn.commit()
    conn.close()

    logger.info(f"API key created: {name}")
    return raw_key


def validate_key(raw_key: str) -> dict | None:
    """Validate an API key. Returns key info if valid, None if invalid."""
    key_hash = _hash_key(raw_key)
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND enabled = 1",
        (key_hash,)
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE api_keys SET last_used = ?, request_count = request_count + 1 WHERE key_hash = ?",
            (time.time(), key_hash)
        )
        conn.commit()
        conn.close()
        return dict(row)

    conn.close()
    return None


def list_keys() -> list[dict]:
    """List all API keys (without the actual key values)."""
    conn = get_conn()
    rows = conn.execute("SELECT name, agent_id, created_at, last_used, request_count, enabled FROM api_keys ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_key(name: str) -> bool:
    """Revoke (disable) an API key by name."""
    conn = get_conn()
    cursor = conn.execute("UPDATE api_keys SET enabled = 0 WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_key(name: str) -> bool:
    """Permanently delete an API key."""
    conn = get_conn()
    cursor = conn.execute("DELETE FROM api_keys WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def _hash_key(raw_key: str) -> str:
    """Hash an API key for storage (SHA-256)."""
    import hashlib
    return hashlib.sha256(raw_key.encode()).hexdigest()
