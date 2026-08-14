"""Tests for multi-user features: users, rooms, messages, user keys."""

import pytest
import time


class TestUsers:
    def setup_method(self):
        from hive.core.db import init_db, get_connection
        init_db()
        conn = get_connection()
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    @pytest.mark.asyncio
    async def test_register(self):
        from hive.core.users import register
        user = await register("testuser", "password123")
        assert user["username"] == "testuser"
        assert "id" in user
        assert "token" not in user  # register doesn't return token directly

    @pytest.mark.asyncio
    async def test_register_duplicate(self):
        from hive.core.users import register
        await register("duplicate", "pass1234")
        with pytest.raises(ValueError, match="already taken"):
            await register("duplicate", "pass5678")

    @pytest.mark.asyncio
    async def test_register_short_password(self):
        from hive.core.users import register
        with pytest.raises(ValueError, match="at least 8"):
            await register("user1", "short")

    @pytest.mark.asyncio
    async def test_login_success(self):
        from hive.core.users import register, login
        await register("loginuser", "mypassword")
        result = await login("loginuser", "mypassword")
        assert result is not None
        assert result["username"] == "loginuser"
        assert "token" in result

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        from hive.core.users import register, login
        await register("loginuser2", "correctpass")
        result = await login("loginuser2", "wrongpass")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user(self):
        from hive.core.users import register, get_user
        user = await register("getme", "password")
        fetched = await get_user(user["id"])
        assert fetched["username"] == "getme"

    @pytest.mark.asyncio
    async def test_list_users(self):
        from hive.core.users import register, list_users
        await register("user_a", "password")
        await register("user_b", "password")
        users = await list_users()
        assert len(users) >= 2


class TestUserKeys:
    def setup_method(self):
        from hive.core.db import init_db, get_connection
        init_db()
        conn = get_connection()
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM user_api_keys")
        conn.commit()
        conn.close()

    @pytest.mark.asyncio
    async def test_set_and_get_key(self):
        from hive.core.users import register
        from hive.core.user_keys import set_key, get_key
        user = await register("keyuser", "password")
        await set_key(user["id"], "openai", "sk-test-key", "gpt-4.1-mini")
        key, model = await get_key(user["id"], "openai")
        assert key == "sk-test-key"
        assert model == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_get_key_fallback_to_server(self):
        from hive.core.users import register
        from hive.core.user_keys import get_key
        user = await register("nokeyuser", "password")
        key, model = await get_key(user["id"], "ollama")
        # Should fall back to server config (ollama has no key but has model)
        assert isinstance(key, str)

    @pytest.mark.asyncio
    async def test_list_keys(self):
        from hive.core.users import register
        from hive.core.user_keys import set_key, list_keys
        user = await register("listkeyuser", "password")
        await set_key(user["id"], "openai", "sk-1")
        await set_key(user["id"], "anthropic", "sk-2")
        keys = await list_keys(user["id"])
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_delete_key(self):
        from hive.core.users import register
        from hive.core.user_keys import set_key, delete_key, list_keys
        user = await register("delkeyuser", "password")
        await set_key(user["id"], "openai", "sk-test")
        await delete_key(user["id"], "openai")
        keys = await list_keys(user["id"])
        assert len(keys) == 0


class TestRooms:
    def setup_method(self):
        from hive.core.db import init_db, get_connection
        init_db()
        conn = get_connection()
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM room_members")
        conn.execute("DELETE FROM rooms")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    @pytest.mark.asyncio
    async def test_create_room(self):
        from hive.core.users import register
        from hive.core.rooms import create_room
        user = await register("roomcreator", "password")
        room = await create_room("Test Room", "group", user["id"])
        assert room["name"] == "Test Room"
        assert room["type"] == "group"

    @pytest.mark.asyncio
    async def test_create_dm(self):
        from hive.core.users import register
        from hive.core.rooms import create_dm
        user_a = await register("dm_user_a", "password")
        user_b = await register("dm_user_b", "password")
        room = await create_dm(user_a["id"], user_b["id"])
        assert room["type"] == "dm"

    @pytest.mark.asyncio
    async def test_get_user_rooms(self):
        from hive.core.users import register
        from hive.core.rooms import create_room, get_user_rooms
        user = await register("roomlister", "password")
        await create_room("Room 1", "group", user["id"])
        await create_room("Room 2", "group", user["id"])
        rooms = await get_user_rooms(user["id"])
        assert len(rooms) >= 2

    @pytest.mark.asyncio
    async def test_invite_bot(self):
        from hive.core.users import register
        from hive.core.rooms import create_room, invite_bot, get_room_members
        user = await register("botinviter", "password")
        room = await create_room("Bot Room", "group", user["id"])
        await invite_bot(room["id"], "agent-123")
        members = await get_room_members(room["id"])
        bot_members = [m for m in members if m["member_type"] == "agent"]
        assert len(bot_members) == 1

    @pytest.mark.asyncio
    async def test_send_and_get_messages(self):
        from hive.core.users import register
        from hive.core.rooms import create_room, send_message, get_messages
        user = await register("msgsender", "password")
        room = await create_room("Chat Room", "group", user["id"])
        await send_message(room["id"], "user", user["id"], "Hello!")
        await send_message(room["id"], "user", user["id"], "World!")
        messages = await get_messages(room["id"])
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello!"
        assert messages[1]["content"] == "World!"
