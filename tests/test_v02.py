"""Tests for Hive v0.2 modules: memory, api_keys, scheduler, arena, swarm, mcp_client."""

import time
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------

class TestMemory:
    def setup_method(self):
        from hive.core.memory import init_memory, clear_memories, MEMORY_DB
        init_memory()
        # Clean up test data
        import sqlite3
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.execute("DELETE FROM memories WHERE agent_id = 'test-agent'")
        conn.commit()
        conn.close()

    def test_remember_and_recall(self):
        from hive.core.memory import remember, recall
        remember("test-agent", "Python is great for AI", keywords="python ai", importance=0.8)
        results = recall("test-agent", "python AI")
        assert len(results) >= 1
        assert "Python" in results[0]["content"]

    def test_recall_empty(self):
        from hive.core.memory import recall
        results = recall("nonexistent-agent", "anything")
        assert results == []

    def test_forget(self):
        from hive.core.memory import remember, recall, forget, MEMORY_DB
        remember("test-agent", "temporary fact", importance=0.5)
        results = recall("test-agent", "temporary")
        assert len(results) >= 1
        memory_id = results[0]["id"]
        ok = forget("test-agent", memory_id)
        assert ok is True

    def test_list_memories(self):
        from hive.core.memory import remember, list_memories
        remember("test-agent", "fact one")
        remember("test-agent", "fact two")
        memories = list_memories("test-agent")
        assert len(memories) >= 2

    def test_clear_memories(self):
        from hive.core.memory import remember, clear_memories, list_memories
        remember("test-agent", "to be cleared")
        count = clear_memories("test-agent")
        assert count >= 1
        assert list_memories("test-agent") == []


# ---------------------------------------------------------------------------
# API Keys tests
# ---------------------------------------------------------------------------

class TestApiKeys:
    def setup_method(self):
        from hive.core.api_keys import init_api_keys
        init_api_keys()

    def test_create_and_validate(self):
        from hive.core.api_keys import create_key, validate_key, delete_key
        raw_key = create_key("test-key-" + str(time.time()))
        assert raw_key.startswith("hive_")
        info = validate_key(raw_key)
        assert info is not None
        assert info["name"].startswith("test-key-")
        delete_key(info["name"])

    def test_invalid_key(self):
        from hive.core.api_keys import validate_key
        result = validate_key("hive_invalid_key_12345")
        assert result is None

    def test_revoke_key(self):
        from hive.core.api_keys import create_key, validate_key, revoke_key, delete_key
        name = "revoke-test-" + str(time.time())
        raw_key = create_key(name)
        assert validate_key(raw_key) is not None
        revoke_key(name)
        assert validate_key(raw_key) is None
        delete_key(name)

    def test_list_keys(self):
        from hive.core.api_keys import list_keys
        keys = list_keys()
        assert isinstance(keys, list)


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------

class TestScheduler:
    def setup_method(self):
        from hive.core.scheduler import init_scheduler
        init_scheduler()

    def test_create_and_get_task(self):
        from hive.core.scheduler import create_task, get_tasks, delete_task
        task_id = "test-task-" + str(time.time())
        result = create_task(task_id, "agent-1", "Summarize today's conversations")
        assert result["id"] == task_id
        tasks = get_tasks()
        assert any(t["id"] == task_id for t in tasks)
        delete_task(task_id)

    def test_delete_task(self):
        from hive.core.scheduler import create_task, delete_task, get_tasks
        task_id = "del-task-" + str(time.time())
        create_task(task_id, "agent-1", "test")
        ok = delete_task(task_id)
        assert ok is True
        tasks = get_tasks()
        assert not any(t["id"] == task_id for t in tasks)

    def test_delete_nonexistent(self):
        from hive.core.scheduler import delete_task
        ok = delete_task("nonexistent-task-id")
        assert ok is False


# ---------------------------------------------------------------------------
# Arena tests
# ---------------------------------------------------------------------------

class TestArena:
    def test_benchmark_result_dataclass(self):
        from hive.core.arena import BenchmarkResult
        r = BenchmarkResult(
            model="test", provider="test", category="reasoning",
            score=0.8, avg_latency_ms=200, total_cost_usd=0.01,
            total_tokens=500, num_prompts=3,
        )
        assert r.score == 0.8
        assert r.model == "test"

    def test_format_benchmark_table(self):
        from hive.core.arena import BenchmarkResult, format_benchmark_table
        results = [
            BenchmarkResult("model-a", "prov", "cat", 0.9, 100, 0.01, 500, 3),
            BenchmarkResult("model-b", "prov", "cat", 0.7, 200, 0.02, 600, 3),
        ]
        table = format_benchmark_table(results)
        assert "model-a" in table
        assert "model-b" in table
        assert "🏆" in table


# ---------------------------------------------------------------------------
# MCP Client tests
# ---------------------------------------------------------------------------

class TestMCPClient:
    def test_mcp_client_init(self):
        from hive.core.mcp_client import MCPClient
        client = MCPClient("test", "python", ["server.py"])
        assert client.name == "test"
        assert client.tools == []

    def test_mcp_registry_register(self):
        from hive.core.mcp_client import MCPRegistry
        registry = MCPRegistry()
        client = registry.register("test-server", "python", ["server.py"])
        assert "test-server" in registry.servers
        assert client.name == "test-server"

    def test_get_all_tool_schemas_empty(self):
        from hive.core.mcp_client import MCPRegistry
        registry = MCPRegistry()
        schemas = registry.get_all_tool_schemas()
        assert schemas == []


# ---------------------------------------------------------------------------
# Swarm tests
# ---------------------------------------------------------------------------

class TestSwarm:
    @pytest.mark.asyncio
    async def test_list_hive_agents_empty(self):
        """list_hive_agents should return a string even with no agents."""
        from hive.core.db import init_db
        init_db()
        from hive.core.swarm import list_hive_agents
        result = await list_hive_agents()
        assert isinstance(result, str)
