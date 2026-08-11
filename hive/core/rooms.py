"""
Rooms & messaging — DMs, group chats, AI bot invitations.
"""

import uuid
import json
import time
import logging

from hive.core.db import get_connection

logger = logging.getLogger(__name__)


async def create_room(name: str, room_type: str, created_by: str) -> dict:
    """Create a new room (dm or group)."""
    room_id = str(uuid.uuid4())[:8]
    now = time.time()
    conn = get_connection()
    conn.execute(
        "INSERT INTO rooms (id, name, type, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (room_id, name, room_type, created_by, now)
    )
    # Creator auto-joins
    conn.execute(
        "INSERT INTO room_members (room_id, member_type, member_id, role, joined_at) VALUES (?, 'user', ?, 'owner', ?)",
        (room_id, created_by, now)
    )
    conn.commit()
    conn.close()
    return {"id": room_id, "name": name, "type": room_type, "created_by": created_by, "created_at": now}


async def create_dm(user_a: str, user_b: str) -> dict:
    """Create or find a DM room between two users."""
    conn = get_connection()
    # Check if DM already exists
    row = conn.execute("""
        SELECT r.id, r.name, r.created_at FROM rooms r
        WHERE r.type = 'dm'
        AND r.id IN (
            SELECT rm.room_id FROM room_members rm WHERE rm.member_type = 'user' AND rm.member_id = ?
        )
        AND r.id IN (
            SELECT rm.room_id FROM room_members rm WHERE rm.member_type = 'user' AND rm.member_id = ?
        )
    """, (user_a, user_b)).fetchone()
    if row:
        conn.close()
        return dict(row)

    conn.close()
    room = await create_room(f"DM:{user_a}:{user_b}", "dm", user_a)
    # Add second user
    await add_member(room["id"], "user", user_b)
    return room


async def get_room(room_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


async def get_user_rooms(user_id: str) -> list[dict]:
    """List all rooms a user is a member of."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.id, r.name, r.type, r.created_by, r.created_at
        FROM rooms r
        JOIN room_members rm ON r.id = rm.room_id
        WHERE rm.member_type = 'user' AND rm.member_id = ?
        ORDER BY r.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def add_member(room_id: str, member_type: str, member_id: str, role: str = "member") -> bool:
    """Add a user or agent to a room."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT room_id FROM room_members WHERE room_id = ? AND member_type = ? AND member_id = ?",
        (room_id, member_type, member_id)
    ).fetchone()
    if existing:
        conn.close()
        return False

    conn.execute(
        "INSERT INTO room_members (room_id, member_type, member_id, role, joined_at) VALUES (?, ?, ?, ?, ?)",
        (room_id, member_type, member_id, role, time.time())
    )
    conn.commit()
    conn.close()
    return True


async def remove_member(room_id: str, member_type: str, member_id: str) -> bool:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM room_members WHERE room_id = ? AND member_type = ? AND member_id = ?",
        (room_id, member_type, member_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


async def get_room_members(room_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT member_type, member_id, role, joined_at FROM room_members WHERE room_id = ?",
        (room_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def send_message(room_id: str, sender_type: str, sender_id: str, content: str) -> dict:
    """Store a message in a room."""
    msg_id = str(uuid.uuid4())[:12]
    now = time.time()
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (id, room_id, sender_type, sender_id, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, room_id, sender_type, sender_id, content, now)
    )
    conn.commit()
    conn.close()
    return {"id": msg_id, "room_id": room_id, "sender_type": sender_type, "sender_id": sender_id, "content": content, "created_at": now}


async def get_messages(room_id: str, limit: int = 50, before: float = None) -> list[dict]:
    conn = get_connection()
    if before:
        rows = conn.execute(
            "SELECT * FROM messages WHERE room_id = ? AND created_at < ? ORDER BY created_at DESC LIMIT ?",
            (room_id, before, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE room_id = ? ORDER BY created_at DESC LIMIT ?",
            (room_id, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


async def invite_bot(room_id: str, agent_id: str) -> bool:
    """Invite an AI agent (bot) to a room."""
    return await add_member(room_id, "agent", agent_id, role="bot")


async def delete_room(room_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_members WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    conn.commit()
    conn.close()
