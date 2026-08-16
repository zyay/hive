"""
WebSocket handler — real-time messaging per room.
Supports: new messages, typing indicators, bot invitations, join/leave events.
"""

import json
import time
import asyncio
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

# Active WebSocket connections per room
_connections: Dict[str, Set] = {}


def register_connection(room_id: str, ws):
    if room_id not in _connections:
        _connections[room_id] = set()
    _connections[room_id].add(ws)
    logger.debug(f"WS connected to room {room_id} ({len(_connections[room_id])} connections)")


def unregister_connection(room_id: str, ws):
    if room_id in _connections:
        _connections[room_id].discard(ws)
        if not _connections[room_id]:
            del _connections[room_id]


async def broadcast(room_id: str, event: dict, exclude=None):
    """Broadcast an event to all connections in a room."""
    if room_id not in _connections:
        return
    data = json.dumps(event)
    dead = []
    for ws in _connections[room_id]:
        if ws is exclude:
            continue
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections[room_id].discard(ws)


def _slugify(name: str) -> str:
    """Lowercase and strip everything except letters and digits."""
    return "".join(c for c in name.lower() if c.isalnum())


async def resolve_mentioned_agents(room_id: str, content: str) -> list[str]:
    """Return agent member IDs that should respond to this message.

    An agent responds when it is @mentioned by id, by name (exact or
    slug-normalized, e.g. "@Research Agent" or "@researchagent"), via the
    generic "@bot"/"@agent"/"@all" handle, or automatically in DM rooms.
    """
    from hive.core.rooms import get_room_members
    from hive.core.db import get_all_agents

    members = await get_room_members(room_id)
    bots = [m["member_id"] for m in members if m["member_type"] == "agent"]
    if not bots:
        return []

    room = await _get_room(room_id)
    if room and room.get("type") == "dm":
        return bots

    text = content.lower()
    if "@bot" in text or "@agent" in text or "@all" in text:
        return bots

    agents_by_id = {a["id"]: a for a in await get_all_agents()}
    mentioned = []
    for bot_id in bots:
        agent = agents_by_id.get(bot_id)
        name = (agent or {}).get("name", "")
        targets = [f"@{bot_id.lower()}"]
        if name:
            targets.append(f"@{name.lower()}")
            slug = _slugify(name)
            if slug:
                targets.append(f"@{slug}")
        if any(t in text for t in targets):
            mentioned.append(bot_id)
    return mentioned


async def trigger_agent_responses(room_id: str, content: str):
    """Fire background responses for every mentioned agent in a room.

    Used by both the WebSocket and REST message paths so agents reply
    regardless of how the message was submitted.
    """
    for agent_id in await resolve_mentioned_agents(room_id, content):
        asyncio.create_task(_generate_bot_response(room_id, agent_id, content))


async def handle_ws_message(room_id: str, data: dict, user_id: str):
    """Process an incoming WebSocket message."""
    from hive.core.rooms import send_message

    msg_type = data.get("type", "message")

    if msg_type == "message":
        content = data.get("content", "").strip()
        if not content:
            return

        # Store user message
        msg = await send_message(room_id, "user", user_id, content)
        event = {
            "type": "new_message",
            "message": {
                "id": msg["id"],
                "sender_type": "user",
                "sender_id": user_id,
                "content": content,
                "created_at": msg["created_at"],
            }
        }
        await broadcast(room_id, event)

        # Mentioned agents respond
        await trigger_agent_responses(room_id, content)

    elif msg_type == "typing":
        await broadcast(room_id, {
            "type": "typing",
            "user_id": user_id,
        }, exclude=None)

    elif msg_type == "invite_bot":
        agent_id = data.get("agent_id")
        if agent_id:
            from hive.core.rooms import invite_bot
            await invite_bot(room_id, agent_id)
            await broadcast(room_id, {
                "type": "bot_invited",
                "agent_id": agent_id,
                "invited_by": user_id,
            })


async def _get_room(room_id: str):
    from hive.core.rooms import get_room
    return await get_room(room_id)


async def _generate_bot_response(room_id: str, agent_id: str, user_message: str):
    """Generate and broadcast a bot response."""
    from hive.core.db import get_agent
    from hive.core.rooms import send_message, get_messages
    from hive.core.agent import run_agent, AgentConfig

    agent_data = await get_agent(agent_id)
    if not agent_data:
        return

    # Broadcast typing indicator
    await broadcast(room_id, {
        "type": "typing",
        "user_id": agent_id,
        "is_bot": True,
    })

    # Build conversation history from room messages
    history = await get_messages(room_id, limit=20)
    messages = [{"role": "system", "content": agent_data["system_prompt"]}]
    for msg in history:
        role = "assistant" if msg["sender_type"] == "agent" and msg["sender_id"] == agent_id else "user"
        messages.append({"role": role, "content": msg["content"]})

    config = AgentConfig(
        name=agent_data["name"],
        system_prompt=agent_data["system_prompt"],
        provider=agent_data["provider"],
        model=agent_data.get("model", ""),
        temperature=agent_data.get("temperature", 0.7),
        max_tokens=agent_data.get("max_tokens", 4096),
    )

    try:
        result = await run_agent(config, user_message, messages[:-1])  # exclude last user msg (already in history)
        if result.response:
            msg = await send_message(room_id, "agent", agent_id, result.response)
            await broadcast(room_id, {
                "type": "new_message",
                "message": {
                    "id": msg["id"],
                    "sender_type": "agent",
                    "sender_id": agent_id,
                    "content": result.response,
                    "created_at": msg["created_at"],
                }
            })
    except Exception as e:
        logger.error(f"Bot response failed for {agent_id} in {room_id}: {e}")
        await broadcast(room_id, {
            "type": "error",
            "message": f"Bot error: {e}",
            "agent_id": agent_id,
        })
