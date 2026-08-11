"""Tests for hardware detection, agent skills, and file sharing."""

import pytest
import base64


class TestHardware:
    def test_detect_hardware(self):
        from hive.core.hardware import detect_hardware
        hw = detect_hardware()
        assert "ram_gb" in hw
        assert "cpu_cores" in hw
        assert hw["cpu_cores"] >= 1
        assert hw["ram_gb"] > 0

    def test_suggest_models(self):
        from hive.core.hardware import suggest_models
        hw = {"ram_gb": 16, "gpu_vram_gb": 8, "cpu_cores": 8}
        suggestions = suggest_models(hw)
        assert len(suggestions) >= 1
        assert all("size" in s for s in suggestions)

    def test_suggest_models_no_gpu(self):
        from hive.core.hardware import suggest_models
        hw = {"ram_gb": 32, "gpu_vram_gb": 0, "cpu_cores": 8}
        suggestions = suggest_models(hw)
        assert len(suggestions) >= 1

    def test_get_system_report(self):
        from hive.core.hardware import get_system_report
        report = get_system_report()
        assert "hardware" in report
        assert "suggested_models" in report
        assert "recommendation" in report
        assert len(report["recommendation"]) > 10


class TestSkills:
    def setup_method(self):
        from hive.core.db import init_db, get_connection
        from hive.core.skills import init_skills
        init_db()
        init_skills()
        conn = get_connection()
        conn.execute("DELETE FROM agent_skills")
        conn.execute("DELETE FROM agents")
        conn.commit()
        conn.close()

    @pytest.mark.asyncio
    async def test_add_and_get_skill(self):
        from hive.core.users import register
        from hive.core.skills import add_skill, get_skills
        # Create an agent first
        from hive.core.agent import AgentConfig
        from hive.core.db import create_agent
        config = AgentConfig(name="test", system_prompt="test")
        agent = await create_agent(config)

        skill = await add_skill(agent["id"], "code-helper", "Always write clean code", "prompt")
        assert skill["name"] == "code-helper"

        skills = await get_skills(agent["id"])
        assert len(skills) == 1
        assert skills[0]["content"] == "Always write clean code"

    @pytest.mark.asyncio
    async def test_delete_skill(self):
        from hive.core.skills import add_skill, delete_skill, get_skills
        from hive.core.agent import AgentConfig
        from hive.core.db import create_agent
        config = AgentConfig(name="test2", system_prompt="test")
        agent = await create_agent(config)

        skill = await add_skill(agent["id"], "temp", "temp content")
        await delete_skill(skill["id"])
        skills = await get_skills(agent["id"])
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_upload_md(self):
        from hive.core.skills import upload_md_file, get_skills
        from hive.core.agent import AgentConfig
        from hive.core.db import create_agent
        config = AgentConfig(name="test3", system_prompt="test")
        agent = await create_agent(config)

        result = await upload_md_file(agent["id"], "guide.md", "# Guide\nThis is a guide.")
        assert result["type"] == "knowledge"

        skills = await get_skills(agent["id"])
        assert len(skills) == 1


class TestFileSharing:
    def setup_method(self):
        from hive.core.db import init_db, get_connection
        from hive.core.files import init_uploads
        init_db()
        init_uploads()
        conn = get_connection()
        conn.execute("DELETE FROM shared_files")
        conn.execute("DELETE FROM rooms")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    @pytest.mark.asyncio
    async def test_upload_and_list_files(self):
        from hive.core.users import register
        from hive.core.rooms import create_room
        from hive.core.files import upload_file, get_room_files

        user = await register("fileuser", "password")
        room = await create_room("File Room", "group", user["id"])

        content = b"Hello, this is a test file!"
        result = await upload_file(room["id"], user["id"], "test.txt", content)
        assert result["filename"] == "test.txt"
        assert result["size"] == len(content)

        files = await get_room_files(room["id"])
        assert len(files) == 1

    @pytest.mark.asyncio
    async def test_delete_file(self):
        from hive.core.users import register
        from hive.core.rooms import create_room
        from hive.core.files import upload_file, delete_file, get_room_files

        user = await register("fileuser2", "password")
        room = await create_room("File Room 2", "group", user["id"])

        result = await upload_file(room["id"], user["id"], "del.txt", b"delete me")
        await delete_file(result["id"])

        files = await get_room_files(room["id"])
        assert len(files) == 0
