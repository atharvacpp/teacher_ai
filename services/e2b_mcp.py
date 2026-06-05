import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools

from config import E2B_API_KEY

# Determine the correct npx command for the OS
_NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"

@asynccontextmanager
async def e2b_mcp_session() -> AsyncGenerator[tuple[ClientSession, list], None]:
    """
    Spins up the @e2b/mcp-server via npx, initializes an MCP ClientSession,
    and returns the LangChain-compatible tools.
    """
    if not E2B_API_KEY:
        raise RuntimeError("E2B_API_KEY is not set. Cannot use E2B MCP Sandbox.")

    env = os.environ.copy()
    env["E2B_API_KEY"] = E2B_API_KEY

    server_params = StdioServerParameters(
        command=_NPX_CMD,
        args=["-y", "@e2b/mcp-server"],
        env=env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Load tools bound as LangChain BaseTool objects
            lc_tools = await load_mcp_tools(session)
            
            yield session, lc_tools
