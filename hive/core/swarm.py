"""
Hive Swarm — agent-to-agent delegation.
An agent can call another agent in the hive to handle subtasks.
"""

import logging
from hive.core.agent import AgentConfig, run_agent, register_tool
from hive.core.db import get_agent, get_all_agents

import json

logger = logging.getLogger(__name__)


@register_tool(
    name="call_agent",
    description="Delegate a subtask to another agent in the hive. The target agent will process the task and return its response. Use this when a task requires a different specialist.",
    parameters={
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "Name of the agent to call"},
            "task": {"type": "string", "description": "The task/question to delegate"},
        },
        "required": ["agent_name", "task"],
    },
)
async def call_agent(agent_name: str, task: str) -> str:
    """Delegate a subtask to another agent in the hive."""
    agents = await get_all_agents()
    target = None
    for a in agents:
        if a["name"].lower() == agent_name.lower():
            target = a
            break

    if not target:
        available = [a["name"] for a in agents]
        return f"Agent '{agent_name}' not found. Available: {', '.join(available)}"

    config = AgentConfig(
        name=target["name"],
        system_prompt=target["system_prompt"],
        provider=target["provider"],
        model=target["model"],
        tools=json.loads(target["tools"]) if isinstance(target["tools"], str) else target["tools"],
        temperature=target["temperature"],
        max_tokens=target["max_tokens"],
    )

    logger.info(f"Swarm: delegating to {agent_name}: {task[:100]}")
    result = await run_agent(config, task)
    return f"[{agent_name}]: {result.response}"


@register_tool(
    name="list_hive_agents",
    description="List all available agents in the hive that can be called for delegation.",
)
async def list_hive_agents() -> str:
    """List all agents available for swarm delegation."""
    agents = await get_all_agents()
    if not agents:
        return "No agents in the hive."
    lines = [f"🐝 Hive agents ({len(agents)}):"]
    for a in agents:
        lines.append(f"  • {a['name']} ({a['provider']}/{a['model'] or 'default'})")
    return "\n".join(lines)
