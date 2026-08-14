"""
User management — registration, authentication, profiles.
"""

import uuid
import time
import hashlib
import logging

import bcrypt

from hive.core.db import get_connection

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def register(username: str, password: str, display_name: str = None) -> dict:
    """Register a new user. Returns user dict or raises ValueError."""
    username = username.strip().lower()
    if not username or len(username) < 2:
        raise ValueError("Username must be at least 2 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise ValueError("Username already taken")

    user_id = str(uuid.uuid4())[:8]
    now = time.time()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, _hash_password(password), display_name or username, now)
    )
    conn.commit()
    conn.close()
    logger.info(f"User registered: {username} ({user_id})")
    return {"id": user_id, "username": username, "display_name": display_name or username, "created_at": now}


async def login(username: str, password: str) -> dict | None:
    """Authenticate user. Returns user dict with token, or None."""
    from hive.core.auth import create_token

    username = username.strip().lower()
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if not row or not _check_password(password, row["password_hash"]):
        return None

    user = dict(row)
    token = create_token(user["id"], role="user")
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "token": token,
    }


async def get_user(user_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT id, username, display_name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


async def get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT id, username, display_name, created_at FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None


async def list_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, username, display_name, created_at FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def update_profile(user_id: str, display_name: str = None) -> dict | None:
    conn = get_connection()
    if display_name is not None:
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
        conn.commit()
    conn.close()
    return await get_user(user_id)
