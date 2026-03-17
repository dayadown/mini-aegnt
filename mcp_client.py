from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

from mcp import ClientSession, StdioServerParameters, stdio_client

from utils import *


class McpClient:

    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.server_path: Path = WORKSPACE_DIR / "mcp_server_examples"/"weather-server-python"/"weather.py"
        self.exit_stack = AsyncExitStack()

    async def get_claude_tools(self):
        """Convert MCP tools to Claude's tool format."""
        mcp_tools = await self.session.list_tools()

        claude_tools = []
        for tool in mcp_tools.tools:
            claude_tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema  # Rename inputSchema to input_schema
            })

        return claude_tools

    async def connect_to_server(self):
        """Connect to an MCP server
        """
        server_script_path = str(self.server_path)
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
