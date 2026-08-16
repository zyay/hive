"""
Tests for v1.0 features — RAG pipeline, templates, extra tools.
"""

import pytest
import asyncio
from pathlib import Path


# ---------------------------------------------------------------------------
# RAG Pipeline Tests
# ---------------------------------------------------------------------------

class TestRAGPipeline:
    """Test the RAG document ingestion and retrieval pipeline."""

    def test_chunk_text(self):
        from hive.core.rag import chunk_text
        text = "The quick brown fox jumps over the lazy dog. " * 20
        chunks = chunk_text(text, chunk_size=10, overlap=2)
        assert len(chunks) > 1
        assert all(len(c.split()) <= 10 for c in chunks)

    def test_chunk_empty_text(self):
        from hive.core.rag import chunk_text
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_extract_text_python(self, tmp_path):
        from hive.core.rag import extract_text
        f = tmp_path / "test.py"
        f.write_text("print('hello world')")
        text = extract_text(str(f))
        assert "hello world" in text

    def test_extract_text_markdown(self, tmp_path):
        from hive.core.rag import extract_text
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome content here.")
        text = extract_text(str(f))
        assert "Title" in text
        assert "content" in text

    def test_file_hash(self, tmp_path):
        from hive.core.rag import file_hash
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h1 = file_hash(str(f))
        assert len(h1) == 16
        
        f.write_text("world")
        h2 = file_hash(str(f))
        assert h1 != h2

    def test_document_dataclass(self):
        from hive.core.rag import Document
        doc = Document(
            id="abc123",
            filename="test.txt",
            content="Hello world",
            chunks=["Hello", "world"],
        )
        assert doc.id == "abc123"
        assert len(doc.chunks) == 2


# ---------------------------------------------------------------------------
# Agent Templates Tests
# ---------------------------------------------------------------------------

class TestTemplates:
    """Test agent template system."""

    def test_list_templates(self):
        from hive.core.templates import list_templates
        templates = list_templates()
        assert len(templates) >= 8
        names = [t["id"] for t in templates]
        assert "coding_assistant" in names
        assert "researcher" in names
        assert "writer" in names

    def test_get_template(self):
        from hive.core.templates import get_template
        t = get_template("coding_assistant")
        assert t is not None
        assert t["name"] == "Code Assistant"
        assert "calculator" in t["tools"]
        assert t["temperature"] == 0.3

    def test_get_unknown_template(self):
        from hive.core.templates import get_template
        assert get_template("nonexistent") is None

    @pytest.mark.asyncio
    async def test_create_from_template(self):
        from hive.core.templates import create_from_template
        from hive.core.db import init_db, delete_agent
        await init_db()
        
        result = await create_from_template("coding_assistant", "Test Coder")
        assert result["name"] == "Test Coder"
        assert "id" in result
        
        await delete_agent(result["id"])

    @pytest.mark.asyncio
    async def test_create_from_invalid_template(self):
        from hive.core.templates import create_from_template
        with pytest.raises(ValueError, match="Unknown template"):
            await create_from_template("nonexistent_template")


# ---------------------------------------------------------------------------
# Extra Tools Tests
# ---------------------------------------------------------------------------

class TestExtraTools:
    """Test web search, code execution, and other extra tools."""

    @pytest.mark.asyncio
    async def test_execute_code_simple(self):
        from hive.core.tools_extra import execute_code
        result = await execute_code("print(2 + 3)")
        assert "5" in result
        assert "Return code: 0" in result

    @pytest.mark.asyncio
    async def test_execute_code_error(self):
        from hive.core.tools_extra import execute_code
        result = await execute_code("raise ValueError('test')")
        assert "ValueError" in result or "stderr" in result

    @pytest.mark.asyncio
    async def test_execute_code_timeout(self):
        from hive.core.tools_extra import execute_code
        result = await execute_code("import time; time.sleep(60)", timeout=2)
        assert "timed out" in result.lower() or "Error" in result

    def test_world_clock(self):
        from hive.core.tools_extra import world_clock
        result = world_clock("UTC")
        assert "UTC" in result

    def test_world_clock_default(self):
        from hive.core.tools_extra import world_clock
        result = world_clock()
        assert "World Clock" in result


# ---------------------------------------------------------------------------
# Async DB Migration Tests
# ---------------------------------------------------------------------------

class TestDBMigrations:
    """Test database migration system."""

    @pytest.mark.asyncio
    async def test_init_db(self):
        from hive.core.db import init_db, get_async_connection
        await init_db()
        
        conn = await get_async_connection()
        try:
            cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
            row = await cursor.fetchone()
            assert row[0] == 3
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_agent_crud(self):
        from hive.core.db import init_db, create_agent, get_agent, get_all_agents, delete_agent
        from hive.core.agent import AgentConfig
        
        await init_db()
        
        config = AgentConfig(name="Test Agent", system_prompt="Test prompt")
        result = await create_agent(config)
        assert "id" in result
        
        agent = await get_agent(result["id"])
        assert agent["name"] == "Test Agent"
        
        agents = await get_all_agents()
        assert len(agents) >= 1
        
        deleted = await delete_agent(result["id"])
        assert deleted is True
