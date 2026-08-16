"""
Database layer — Async SQLite with migration support.
Uses aiosqlite for non-blocking database operations.
"""

import json
import time
import uuid
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite

from hive.core.agent import AgentConfig

logger = logging.getLogger(__name__)

DB_PATH = Path("hive.db")
MIGRATIONS_PATH = Path("migrations")

# Current schema version
SCHEMA_VERSION = 4


def get_connection() -> sqlite3.Connection:
    """Get a synchronous database connection (for legacy sync code)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


async def get_async_connection() -> aiosqlite.Connection:
    """Get an async database connection."""
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db():
    """Initialize database with migrations."""
    conn = await get_async_connection()
    
    # Create migrations tracking table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        )
    """)
    
    # Check current version
    cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
    row = await cursor.fetchone()
    current_version = row[0] if row and row[0] else 0
    
    # Apply migrations
    if current_version < 1:
        await _migrate_v1(conn)
    if current_version < 2:
        await _migrate_v2(conn)
    if current_version < 3:
        await _migrate_v3(conn)
    if current_version < 4:
        await _migrate_v4(conn)
    
    await conn.close()
    logger.info(f"Database initialized at schema version {SCHEMA_VERSION}")


async def _migrate_v1(conn: aiosqlite.Connection):
    """Initial schema — core tables."""
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'ollama',
            model TEXT NOT NULL DEFAULT '',
            tools TEXT NOT NULL DEFAULT '[]',
            temperature REAL NOT NULL DEFAULT 0.7,
            max_tokens INTEGER NOT NULL DEFAULT 4096,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            mode TEXT NOT NULL DEFAULT 'work'
        );

        CREATE TABLE IF NOT EXISTS agent_files (
            agent_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            assigned_at REAL NOT NULL,
            PRIMARY KEY (agent_id, filename),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            messages TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            provider TEXT,
            model TEXT,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            latency_ms REAL DEFAULT 0.0,
            tool_calls INTEGER DEFAULT 0,
            llm_calls INTEGER DEFAULT 0,
            timestamp REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, provider)
        );
    """)
    await conn.execute(
        "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
        (1, time.time(), "Initial schema — core tables")
    )
    await conn.commit()
    logger.info("Applied migration v1: Initial schema")


async def _migrate_v2(conn: aiosqlite.Connection):
    """Add rooms and messaging tables."""
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'group',
            created_by TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS room_members (
            room_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            member_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at REAL NOT NULL,
            PRIMARY KEY (room_id, member_type, member_id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            sender_type TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );
        CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_skills (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            skill_type TEXT NOT NULL DEFAULT 'prompt',
            file_path TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );

        CREATE TABLE IF NOT EXISTS shared_files (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            uploader_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            size INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );
        CREATE INDEX IF NOT EXISTS idx_files_room ON shared_files(room_id, created_at);
    """)
    await conn.execute(
        "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
        (2, time.time(), "Add rooms and messaging")
    )
    await conn.commit()
    logger.info("Applied migration v2: Rooms and messaging")


async def _migrate_v3(conn: aiosqlite.Connection):
    """Add P2P and E2EE tables."""
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS p2p_peers (
            did TEXT PRIMARY KEY,
            peer_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            public_signing_key TEXT NOT NULL DEFAULT '',
            public_encryption_key TEXT NOT NULL DEFAULT '',
            last_seen REAL NOT NULL DEFAULT 0,
            is_online INTEGER NOT NULL DEFAULT 0,
            added_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS p2p_sessions (
            peer_did TEXT PRIMARY KEY,
            root_key TEXT NOT NULL,
            sending_chain_key TEXT NOT NULL,
            receiving_chain_key TEXT NOT NULL,
            sending_counter INTEGER NOT NULL DEFAULT 0,
            receiving_counter INTEGER NOT NULL DEFAULT 0,
            their_public_key TEXT NOT NULL DEFAULT '',
            established_at REAL NOT NULL,
            FOREIGN KEY (peer_did) REFERENCES p2p_peers(did)
        );

        CREATE TABLE IF NOT EXISTS encrypted_messages (
            id TEXT PRIMARY KEY,
            room_id TEXT,
            sender_did TEXT NOT NULL,
            recipient_did TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            nonce TEXT NOT NULL,
            counter INTEGER NOT NULL DEFAULT 0,
            message_type TEXT NOT NULL DEFAULT 'text',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enc_messages_room ON encrypted_messages(room_id);

        CREATE TABLE IF NOT EXISTS agent_peers (
            did TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'ollama',
            model TEXT NOT NULL DEFAULT '',
            use_local INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL
        );
    """)
    await conn.execute(
        "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
        (3, time.time(), "Add P2P and E2EE tables")
    )
    await conn.commit()
    logger.info("Applied migration v3: P2P and E2EE")


async def _migrate_v4(conn: aiosqlite.Connection):
    """Add description column to agents."""
    cursor = await conn.execute("PRAGMA table_info(agents)")
    columns = [row[1] for row in await cursor.fetchall()]
    if "description" not in columns:
        await conn.execute("ALTER TABLE agents ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    await conn.execute(
        "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
        (4, time.time(), "Add agent descriptions")
    )
    await conn.commit()
    logger.info("Applied migration v4: Agent descriptions")


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------

async def create_agent(config: AgentConfig) -> dict:
    """Create a new agent."""
    agent_id = str(uuid.uuid4())[:8]
    now = time.time()
    conn = await get_async_connection()
    try:
        await conn.execute(
            "INSERT INTO agents (id, name, system_prompt, description, provider, model, tools, temperature, max_tokens, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, config.name, config.system_prompt, config.description, config.provider, config.model,
             json.dumps(config.tools), config.temperature, config.max_tokens, now, now)
        )
        await conn.commit()
        return {"id": agent_id, **_agent_to_dict(config), "created_at": now}
    finally:
        await conn.close()


async def get_agent(agent_id: str) -> Optional[dict]:
    """Get an agent by ID."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        await conn.close()


async def get_all_agents() -> list[dict]:
    """Get all agents."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute("SELECT * FROM agents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def update_agent(agent_id: str, updates: dict) -> Optional[dict]:
    """Update an agent."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        existing = await cursor.fetchone()
        if not existing:
            return None

        fields = []
        values = []
        for key, val in updates.items():
            if key in ("tools",) and isinstance(val, list):
                val = json.dumps(val)
            fields.append(f"{key} = ?")
            values.append(val)
        fields.append("updated_at = ?")
        values.append(time.time())
        values.append(agent_id)

        await conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ?", values)
        await conn.commit()
        return await get_agent(agent_id)
    finally:
        await conn.close()


async def delete_agent(agent_id: str) -> bool:
    """Delete an agent and its conversations."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await conn.execute("DELETE FROM conversations WHERE agent_id = ?", (agent_id,))
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


def _agent_to_dict(config: AgentConfig) -> dict:
    """Convert AgentConfig to dict."""
    return {
        "name": config.name,
        "system_prompt": config.system_prompt,
        "description": config.description,
        "provider": config.provider,
        "model": config.model,
        "tools": config.tools,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

async def create_conversation(agent_id: str) -> str:
    """Create a new conversation."""
    conv_id = str(uuid.uuid4())[:8]
    now = time.time()
    conn = await get_async_connection()
    try:
        await conn.execute(
            "INSERT INTO conversations (id, agent_id, messages, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, agent_id, "[]", now, now)
        )
        await conn.commit()
        return conv_id
    finally:
        await conn.close()


async def get_conversation(conv_id: str) -> Optional[dict]:
    """Get a conversation by ID."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["messages"] = json.loads(d["messages"])
        return d
    finally:
        await conn.close()


async def save_messages(conv_id: str, messages: list[dict]):
    """Save messages to a conversation."""
    conn = await get_async_connection()
    try:
        await conn.execute(
            "UPDATE conversations SET messages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(messages), time.time(), conv_id)
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_agent_conversations(agent_id: str) -> list[dict]:
    """Get all conversations for an agent."""
    conn = await get_async_connection()
    try:
        cursor = await conn.execute(
            "SELECT id, created_at, updated_at FROM conversations WHERE agent_id = ? ORDER BY updated_at DESC",
            (agent_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

async def log_usage(agent_id: str, provider: str, model: str, tokens_in: int, tokens_out: int,
                    cost_usd: float, latency_ms: float, tool_calls: int, llm_calls: int):
    """Log usage metrics."""
    conn = await get_async_connection()
    try:
        await conn.execute(
            "INSERT INTO usage_logs (agent_id, provider, model, tokens_in, tokens_out, cost_usd, latency_ms, tool_calls, llm_calls, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, provider, model, tokens_in, tokens_out, cost_usd, latency_ms, tool_calls, llm_calls, time.time())
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_usage_summary(agent_id: str = None, days: int = 7) -> dict:
    """Get usage summary for a time period."""
    conn = await get_async_connection()
    try:
        since = time.time() - (days * 86400)
        where = "WHERE timestamp > ?"
        params = [since]
        if agent_id:
            where += " AND agent_id = ?"
            params.append(agent_id)

        cursor = await conn.execute(f"""
            SELECT
                COUNT(*) as total_requests,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(cost_usd) as total_cost,
                AVG(latency_ms) as avg_latency,
                SUM(tool_calls) as total_tool_calls,
                SUM(llm_calls) as total_llm_calls
            FROM usage_logs {where}
        """, params)
        row = await cursor.fetchone()

        return {
            "period_days": days,
            "total_requests": row[0] or 0,
            "total_tokens_in": row[1] or 0,
            "total_tokens_out": row[2] or 0,
            "total_cost_usd": round(row[3] or 0, 6),
            "avg_latency_ms": round(row[4] or 0, 1),
            "total_tool_calls": row[5] or 0,
            "total_llm_calls": row[6] or 0,
        }
    finally:
        await conn.close()
