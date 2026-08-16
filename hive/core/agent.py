"""
Agent loop — orchestrates LLM calls with tool execution.
Supports multi-turn conversations with tool calling.
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from hive.core.llm import chat, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an AI agent."""
    name: str
    system_prompt: str
    description: str = ""
    provider: str = "ollama"
    model: str = ""
    tools: list[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    max_iterations: int = 10


@dataclass
class AgentMessage:
    """A single message in a conversation."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_calls: list = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class AgentResult:
    """Result of an agent run."""
    response: str
    messages: list[AgentMessage]
    llm_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    tool_executions: int = 0
    finish_reason: str = ""


class ToolRegistry:
    """Registry of available tools for agents."""

    def __init__(self):
        self._tools: dict[str, dict] = {}
        self._handlers: dict[str, callable] = {}

    def register(self, name: str, description: str, parameters: dict, handler: callable):
        """Register a tool with its schema and handler."""
        self._tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        }
        self._handlers[name] = handler

    def get_schema(self, tool_names: list[str] = None) -> list[dict]:
        """Get OpenAI-format tool schemas, optionally filtered."""
        if tool_names:
            return [self._tools[n] for n in tool_names if n in self._tools]
        return list(self._tools.values())

    async def execute(self, name: str, arguments: str) -> str:
        """Execute a tool by name with JSON arguments."""
        handler = self._handlers.get(name)
        if not handler:
            return f"Error: unknown tool '{name}'"
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            result = handler(**args)
            if hasattr(result, "__await__"):
                result = await result
            return str(result)
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return f"Error executing {name}: {e}"


# Global tool registry
tool_registry = ToolRegistry()


def register_tool(name: str, description: str, parameters: dict = None):
    """Decorator to register a function as an agent tool."""
    def decorator(fn):
        tool_registry.register(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            handler=fn,
        )
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------

@register_tool(
    name="calculator",
    description="Evaluate a math expression. Examples: '2 + 3 * 4', '(100 - 20) / 4'",
    parameters={"type": "object", "properties": {"expression": {"type": "string", "description": "Math expression"}}, "required": ["expression"]},
)
def builtin_calculator(expression: str) -> str:
    import ast
    try:
        node = ast.parse(expression, mode="eval")
        result = _safe_eval(node.body)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp):
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        ops = {
            ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b, ast.Mod: lambda a, b: a % b,
            ast.Pow: lambda a, b: a ** b,
            ast.Div: lambda a, b: a / b if b != 0 else (_ for _ in ()).throw(ValueError("Division by zero")),
        }
        op = type(node.op)
        if op in ops:
            return ops[op](left, right)
        raise ValueError(f"Unsupported: {op.__name__}")
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval(node.operand)
    raise ValueError(f"Unsupported: {type(node).__name__}")


import ast


@register_tool(
    name="get_time",
    description="Get the current date and time (UTC and local).",
)
def builtin_get_time() -> str:
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    return f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}\nLocal: {now_local.strftime('%Y-%m-%d %H:%M:%S')}"


@register_tool(
    name="list_agents",
    description="List all available agents in the hive.",
)
async def builtin_list_agents() -> str:
    from hive.core.db import get_all_agents
    try:
        agents = await get_all_agents()
        if not agents:
            return "No agents available."
        names = [a["name"] for a in agents]
        return f"Available agents ({len(names)}): {', '.join(names)}"
    except Exception as e:
        return f"Error listing agents: {e}"


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent(
    config: AgentConfig,
    user_message: str,
    conversation: list[dict] = None,
) -> AgentResult:
    """
    Run the agent loop: send messages to LLM, execute tools, repeat until done.

    The loop:
    1. Send conversation + user message to LLM
    2. If LLM returns tool_calls → execute them → add results → go to 1
    3. If LLM returns text → return as final answer
    4. If max_iterations reached → return with warning
    """
    messages = conversation or []

    # Add system prompt if not present
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": config.system_prompt}] + messages

    # Add user message
    messages.append({"role": "user", "content": user_message})

    # Get tool schemas
    tool_schemas = tool_registry.get_schema(config.tools if config.tools else None)

    total_llm_calls = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    total_latency = 0.0
    tool_executions = 0
    all_messages = [AgentMessage(role=m["role"], content=m.get("content", ""), timestamp=time.time()) for m in messages]

    for iteration in range(config.max_iterations):
        # Call LLM
        resp: LLMResponse = await chat(
            provider=config.provider,
            model=config.model,
            messages=messages,
            tools=tool_schemas if tool_schemas else None,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        total_llm_calls += 1
        total_tokens_in += resp.tokens_in
        total_tokens_out += resp.tokens_out
        total_cost += resp.cost_usd
        total_latency += resp.latency_ms

        # If no tool calls, we're done
        if not resp.tool_calls:
            messages.append({"role": "assistant", "content": resp.content})
            all_messages.append(AgentMessage(
                role="assistant", content=resp.content, timestamp=time.time()
            ))
            return AgentResult(
                response=resp.content,
                messages=all_messages,
                llm_calls=total_llm_calls,
                total_tokens_in=total_tokens_in,
                total_tokens_out=total_tokens_out,
                total_cost_usd=round(total_cost, 6),
                total_latency_ms=round(total_latency, 1),
                tool_executions=tool_executions,
                finish_reason=resp.finish_reason,
            )

        # Process tool calls
        messages.append({
            "role": "assistant",
            "content": resp.content or "",
            "tool_calls": resp.tool_calls,
        })
        all_messages.append(AgentMessage(
            role="assistant", content=resp.content or "",
            tool_calls=resp.tool_calls, timestamp=time.time()
        ))

        for tc in resp.tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]

            logger.info(f"  Tool call: {fn_name}({fn_args[:100]})")
            result = await tool_registry.execute(fn_name, fn_args)
            tool_executions += 1

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": fn_name,
                "content": result,
            })
            all_messages.append(AgentMessage(
                role="tool", content=result,
                tool_call_id=tc["id"], name=fn_name, timestamp=time.time()
            ))

    # Max iterations reached
    return AgentResult(
        response="I've reached my maximum number of reasoning steps. Here's what I have so far.",
        messages=all_messages,
        llm_calls=total_llm_calls,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        total_cost_usd=round(total_cost, 6),
        total_latency_ms=round(total_latency, 1),
        tool_executions=tool_executions,
        finish_reason="max_iterations",
    )
