import asyncio
import os
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools

async def test():
    E2B_API_KEY = os.environ.get("E2B_API_KEY", "dummy")
    params = StdioServerParameters(
        command="npx.cmd",
        args=["-y", "@e2b/mcp-server"],
        env={"E2B_API_KEY": E2B_API_KEY, "PATH": os.environ["PATH"]}
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            for t in tools:
                print("Tool:", t.name, t.args_schema.model_json_schema())

asyncio.run(test())
