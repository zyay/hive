"""
Cross-repo MCP integrations — connect hive to mcp-agent-tools and mcp-rag-bridge.
Allows agents to use tools from external MCP servers.
"""

import asyncio
import json
import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MCPToolProxy:
    """Proxy that calls a tool on a remote MCP server via stdio."""

    def __init__(self, server_path: str, tool_name: str):
        self.server_path = server_path
        self.tool_name = tool_name

    async def call(self, arguments: dict) -> str:
        """Call the tool on the remote MCP server."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            python = sys.executable
            params = StdioServerParameters(
                command=python,
                args=[self.server_path],
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(self.tool_name, arguments)
                    return result.content[0].text if result.content else "(no result)"
        except ImportError:
            return "Error: mcp package not installed. Run: pip install mcp"
        except Exception as e:
            return f"MCP error: {e}"


class MCPServerConnection:
    """Represents a connection to an external MCP server."""

    def __init__(self, name: str, server_path: str):
        self.name = name
        self.server_path = server_path
        self._tools: list[str] = []

    async def discover_tools(self) -> list[str]:
        """Discover available tools on the MCP server."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            python = sys.executable
            params = StdioServerParameters(command=python, args=[self.server_path])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self._tools = [t.name for t in tools.tools]
                    logger.info(f"MCP {self.name}: discovered {len(self._tools)} tools: {self._tools}")
                    return self._tools
        except Exception as e:
            logger.warning(f"MCP {self.name}: discovery failed: {e}")
            return []

    def get_tool_proxy(self, tool_name: str) -> MCPToolProxy:
        """Get a proxy for a specific tool."""
        return MCPToolProxy(self.server_path, tool_name)

    @property
    def tools(self) -> list[str]:
        return self._tools


class IntegrationRegistry:
    """Registry of external MCP server integrations."""

    def __init__(self):
        self._connections: dict[str, MCPServerConnection] = {}

    def register(self, name: str, server_path: str) -> MCPServerConnection:
        """Register an external MCP server."""
        conn = MCPServerConnection(name, server_path)
        self._connections[name] = conn
        return conn

    async def discover_all(self) -> dict[str, list[str]]:
        """Discover tools on all registered servers."""
        results = {}
        for name, conn in self._connections.items():
            tools = await conn.discover_tools()
            results[name] = tools
        return results

    def get_all_tool_schemas(self) -> list[dict]:
        """Get OpenAI-format tool schemas for all tools across all servers."""
        schemas = []
        for name, conn in self._connections.items():
            for tool_name in conn.tools:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": f"{name}__{tool_name}",
                        "description": f"[{name}] Tool from {name} MCP server",
                        "parameters": {"type": "object", "properties": {}},
                    }
                })
        return schemas

    async def execute(self, qualified_name: str, arguments: dict) -> str:
        """Execute a tool by qualified name (server__tool)."""
        parts = qualified_name.split("__", 1)
        if len(parts) != 2:
            return f"Error: invalid tool name '{qualified_name}'. Expected 'server__tool'."
        server_name, tool_name = parts
        conn = self._connections.get(server_name)
        if not conn:
            return f"Error: MCP server '{server_name}' not registered."
        proxy = conn.get_tool_proxy(tool_name)
        return await proxy.call(arguments)

    @property
    def connections(self) -> dict[str, MCPServerConnection]:
        return self._connections


# Global integration registry
integrations = IntegrationRegistry()


def setup_default_integrations():
    """Set up integrations with sibling projects if they exist."""
    base = Path(__file__).parent.parent.parent.parent

    # mcp-agent-tools
    agent_tools_path = base.parent / "mcp-agent-tools" / "server.py"
    if agent_tools_path.exists():
        integrations.register("agent-tools", str(agent_tools_path))
        logger.info(f"Registered mcp-agent-tools: {agent_tools_path}")

    # mcp-rag-bridge
    rag_bridge_path = base.parent / "mcp-rag-bridge" / "server.py"
    if rag_bridge_path.exists():
        integrations.register("rag-bridge", str(rag_bridge_path))
        logger.info(f"Registered mcp-rag-bridge: {rag_bridge_path}")
