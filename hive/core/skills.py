"""
Agent skills — MD files and skill definitions that extend agent capabilities.
Skills are loaded as additional system prompt context or tool definitions.
"""

import json
import time
import uuid
import logging
from pathlib import Path

from hive.core.db import get_connection

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("skills")


def init_skills():
    """Create skills directory."""
    SKILLS_DIR.mkdir(exist_ok=True)


async def add_skill(agent_id: str, name: str, content: str, skill_type: str = "prompt") -> dict:
    """Add a skill to an agent.
    Types: 'prompt' (appended to system prompt), 'tool' (JSON tool definition), 'knowledge' (MD reference)
    """
    skill_id = str(uuid.uuid4())[:8]
    now = time.time()

    # Save content to file if it's a knowledge file
    if skill_type == "knowledge" and content:
        file_path = SKILLS_DIR / f"{agent_id}_{skill_id}.md"
        file_path.write_text(content, encoding="utf-8")
    else:
        file_path = ""

    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_skills (id, agent_id, name, content, skill_type, file_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (skill_id, agent_id, name, content, skill_type, str(file_path), now)
    )
    conn.commit()
    conn.close()
    return {"id": skill_id, "agent_id": agent_id, "name": name, "type": skill_type}


async def get_skills(agent_id: str) -> list[dict]:
    """Get all skills for an agent."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, skill_type, content, file_path, created_at FROM agent_skills WHERE agent_id = ? ORDER BY created_at",
        (agent_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def delete_skill(skill_id: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM agent_skills WHERE id = ?", (skill_id,)).fetchone()
    if row and row["file_path"]:
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    cursor = conn.execute("DELETE FROM agent_skills WHERE id = ?", (skill_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


async def get_agent_context(agent_id: str) -> str:
    """Build full context for an agent: system prompt + skills."""
    from hive.core.db import get_agent
    agent = await get_agent(agent_id)
    if not agent:
        return ""

    context = agent["system_prompt"]
    skills = await get_skills(agent_id)

    for skill in skills:
        if skill["skill_type"] == "prompt" and skill["content"]:
            context += f"\n\n[{skill['name']}]:\n{skill['content']}"
        elif skill["skill_type"] == "knowledge" and skill["file_path"]:
            try:
                content = Path(skill["file_path"]).read_text(encoding="utf-8")
                context += f"\n\n[Knowledge: {skill['name']}]:\n{content}"
            except Exception:
                pass

    return context


async def upload_md_file(agent_id: str, filename: str, content: str) -> dict:
    """Upload an MD file as a knowledge skill for an agent."""
    name = filename.replace(".md", "").replace(".txt", "")
    return await add_skill(agent_id, name, content, skill_type="knowledge")
