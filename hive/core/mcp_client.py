"""
Cross-repo MCP integration — connect hive to external MCP servers.
Allows hive agents to use tools from mcp-agent-tools and mcp-rag-bridge.
"""

import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MCPClient:
    """Lightweight MCP client that connects to an MCP server via stdio.
    Discovers tools and makes them available to hive agents."""

    def __init__(self, name: str, command: str, args: list[str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self._tools: list[dict] = []
        self._connected = False

    async def connect(self) -> list[dict]:
        """Connect to MCP server and discover available tools."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(command=self.command, args=self.args)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self._tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {"type": "object", "properties": {}},
                        }
                        for t in tools.tools
                    ]
                    self._connected = True
                    logger.info(f"MCP {self.name}: connected, {len(self._tools)} tools available")
                    return self._tools
        except ImportError:
            logger.warning("mcp package not installed — run: pip install mcp")
            return []
        except Exception as e:
            logger.warning(f"MCP {self.name}: connection failed: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the MCP server."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(command=self.command, args=self.args)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return result.content[0].text if result.content else "(no result)"
        except Exception as e:
            return f"MCP error: {e}"

    @property
    def tools(self) -> list[dict]:
        return self._tools

    def get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-format tool schemas for all discovered tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{self.name}__{t['name']}",
                    "description": f"[{self.name}] {t['description']}",
                    "parameters": t["input_schema"],
                }
            }
            for t in self._tools
        ]


class MCPRegistry:
    """Registry of connected MCP servers. Manages tool discovery and routing."""

    def __init__(self):
        self._servers: dict[str, MCPClient] = {}

    def register(self, name: str, command: str, args: list[str] = None) -> MCPClient:
        """Register an MCP server."""
        client = MCPClient(name, command, args)
        self._servers[name] = client
        return client

    async def connect_all(self):
        """Connect to all registered MCP servers."""
        for name, client in self._servers.items():
            await client.connect()

    def get_all_tool_schemas(self) -> list[dict]:
        """Get all tool schemas from all connected servers."""
        schemas = []
        for client in self._servers.values():
            schemas.extend(client.get_tool_schemas())
        return schemas

    async def execute(self, qualified_name: str, arguments: dict) -> str:
        """Execute a tool by its qualified name (server__tool)."""
        parts = qualified_name.split("__", 1)
        if len(parts) != 2:
            return f"Error: invalid tool name format. Expected 'server__tool', got '{qualified_name}'"
        server_name, tool_name = parts
        client = self._servers.get(server_name)
        if not client:
            return f"Error: MCP server '{server_name}' not registered"
        return await client.call_tool(tool_name, arguments)

    @property
    def servers(self) -> dict[str, MCPClient]:
        return self._servers


# Global registry
mcp_registry = MCPRegistry()
