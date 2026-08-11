"""
Long-term memory — vector-based memory per agent.
Agents can remember facts across sessions using embedding similarity.
"""

import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_DB = Path("hive_memory.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(MEMORY_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_memory():
    """Create memory tables."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT NOT NULL DEFAULT '',
            importance REAL NOT NULL DEFAULT 0.5,
            access_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            last_accessed REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
    """)
    conn.commit()
    conn.close()


def remember(agent_id: str, content: str, keywords: str = "", importance: float = 0.5):
    """Store a memory for an agent."""
    now = time.time()
    conn = get_conn()
    conn.execute(
        "INSERT INTO memories (agent_id, content, keywords, importance, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, content, keywords, importance, now, now)
    )
    conn.commit()
    conn.close()
    logger.info(f"Memory stored for agent {agent_id}: {content[:50]}")


def recall(agent_id: str, query: str, limit: int = 5) -> list[dict]:
    """Recall relevant memories using keyword matching + importance weighting.

    For production, replace with embedding similarity search.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM memories WHERE agent_id = ? ORDER BY importance DESC, access_count DESC, created_at DESC LIMIT ?",
        (agent_id, limit * 3)
    ).fetchall()
    conn.close()

    if not rows:
        return []

    query_words = set(query.lower().split())
    scored = []
    for row in rows:
        row_dict = dict(row)
        content_words = set(row_dict["content"].lower().split())
        keyword_words = set(row_dict["keywords"].lower().split())
        overlap = len(query_words & (content_words | keyword_words))
        score = overlap * row_dict["importance"] + row_dict["access_count"] * 0.1
        row_dict["relevance_score"] = round(score, 3)
        scored.append(row_dict)

    scored.sort(key=lambda x: -x["relevance_score"])

    # Update access count for top results
    top_ids = [m["id"] for m in scored[:limit]]
    if top_ids:
        conn = get_conn()
        for mid in top_ids:
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (time.time(), mid)
            )
        conn.commit()
        conn.close()

    return scored[:limit]


def forget(agent_id: str, memory_id: int) -> bool:
    """Delete a specific memory."""
    conn = get_conn()
    cursor = conn.execute(
        "DELETE FROM memories WHERE id = ? AND agent_id = ?",
        (memory_id, agent_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def list_memories(agent_id: str, limit: int = 20) -> list[dict]:
    """List all memories for an agent."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM memories WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_memories(agent_id: str) -> int:
    """Delete all memories for an agent."""
    conn = get_conn()
    cursor = conn.execute("DELETE FROM memories WHERE agent_id = ?", (agent_id,))
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count
