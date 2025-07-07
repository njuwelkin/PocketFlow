from ast import arguments
from openai import OpenAI
import os
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVER_PARAMS = StdioServerParameters(
            #command="uv",
            #args=["--directory", 
            #    "/opt/anaconda3/bin",
            #    "run",
            #    "mysql_mcp_server"
            #],
            command = "uvx",
            args = [
                "--from",
                "mysql-mcp-server",
                "mysql_mcp_server"
            ],
            env={
                "MYSQL_HOST": "127.0.0.1",
                "MYSQL_PORT": "3306",
                "MYSQL_USER": "root",
                "MYSQL_PASSWORD": "my-secret-pw",
                "MYSQL_DATABASE": "test"
            }
        )

async def mcp_get_tools():
    """Get available tools from an MCP server.
    Get available tools from an MCP server within an existing event loop."""
    server_params = MCP_SERVER_PARAMS
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            return tools_response.tools

async def mcp_call_tool(tool_name=None, arguments=None):
    """Call a tool on an MCP server.
    """
    server_params = MCP_SERVER_PARAMS
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.content[0].text

async def exec_steps(steps=[]):
    results = [0 for _ in steps]
    i = 0
    for step in steps:
        tool_name = step["tool"]
        raw_arguments = step["parameters"]
        print(f"Executing tool '{tool_name}' with parameters: {raw_arguments}")
        arguments = {}
        for k in raw_arguments:
            v = raw_arguments[k]
            if isinstance(v, str) and v[:len("$STEP_RESULT_")] == "$STEP_RESULT_":
                arguments[k] = results[int(v[len("$STEP_RESULT_"):])-1]
            else:
                arguments[k] = v

        print(f"Executing tool '{tool_name}' with parameters: {arguments}")
        results[i] = await mcp_call_tool(tool_name, arguments)
        print(f"Result: {results[i]}")
        i += 1
    return results