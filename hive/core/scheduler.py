"""
Scheduled automations — cron-based agent tasks.
Run agents on a schedule: morning summaries, monitoring, reports.
"""

import json
import time
import sqlite3
import logging
import asyncio
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEDULER_DB = Path("hive_scheduler.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SCHEDULER_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_scheduler():
    """Create scheduler tables."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            cron_expression TEXT NOT NULL DEFAULT '0 * * * *',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run REAL,
            next_run REAL,
            run_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def create_task(task_id: str, agent_id: str, prompt: str, cron_expression: str = "0 * * * *") -> dict:
    """Create a scheduled task."""
    now = time.time()
    conn = get_conn()
    conn.execute(
        "INSERT INTO scheduled_tasks (id, agent_id, prompt, cron_expression, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, agent_id, prompt, cron_expression, now)
    )
    conn.commit()
    conn.close()
    return {"id": task_id, "agent_id": agent_id, "prompt": prompt, "cron": cron_expression}


def get_tasks() -> list[dict]:
    """List all scheduled tasks."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_task(task_id: str) -> bool:
    """Delete a scheduled task."""
    conn = get_conn()
    cursor = conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def toggle_task(task_id: str, enabled: bool) -> bool:
    """Enable or disable a scheduled task."""
    conn = get_conn()
    conn.execute("UPDATE scheduled_tasks SET enabled = ? WHERE id = ?", (1 if enabled else 0, task_id))
    conn.commit()
    conn.close()
    return True


async def run_due_tasks():
    """Check and run any tasks that are due. Called periodically by the scheduler loop."""
    from hive.core.db import get_agent
    from hive.core.agent import AgentConfig, run_agent

    tasks = get_tasks()
    now = time.time()

    for task in tasks:
        if not task["enabled"]:
            continue

        # Simple interval check (for MVP — full cron parsing in v0.3)
        # Default: run every hour
        interval = 3600  # 1 hour
        if task["last_run"] and (now - task["last_run"]) < interval:
            continue

        logger.info(f"Scheduler: running task {task['id']} (agent: {task['agent_id']})")

        agent_data = await get_agent(task["agent_id"])
        if not agent_data:
            logger.warning(f"Scheduler: agent {task['agent_id']} not found, skipping")
            continue

        config = AgentConfig(
            name=agent_data["name"],
            system_prompt=agent_data["system_prompt"],
            provider=agent_data["provider"],
            model=agent_data["model"],
        )

        try:
            result = await run_agent(config, task["prompt"])
            conn = get_conn()
            conn.execute(
                "UPDATE scheduled_tasks SET last_run = ?, run_count = run_count + 1 WHERE id = ?",
                (time.time(), task["id"])
            )
            conn.commit()
            conn.close()
            logger.info(f"Scheduler: task {task['id']} completed ({result.llm_calls} LLM calls)")
        except Exception as e:
            logger.error(f"Scheduler: task {task['id']} failed: {e}")


async def scheduler_loop(interval: int = 60):
    """Background loop that checks for due tasks every `interval` seconds."""
    logger.info(f"Scheduler loop started (checking every {interval}s)")
    while True:
        try:
            await run_due_tasks()
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
        await asyncio.sleep(interval)
