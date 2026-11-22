"""Exercise the MCP server over stdio using this interpreter and a temporary data directory.

    uv run --offline --frozen python scripts/smoke_stdio.py --offline kataster_status '{}'
    uv run python scripts/smoke_stdio.py --live TOOL_NAME '{"argument":"value"}'
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(mode: str, calls: list[tuple[str, dict]]) -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("smoke_server.py")), mode])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        init = await client.initialize()
        print("server:", init.server_info.name, init.server_info.version, mode)
        print("tools:", [tool.name for tool in (await client.list_tools()).tools])
        failed = False
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            failed |= result.is_error
            text = getattr(result.content[0], "text", "") if result.content else ""
            print(f"{name} isError={result.is_error}\n{text[:1500]}")
        return int(failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true", help="Refuse all provider requests (default).")
    modes.add_argument("--live", action="store_true", help="Use real providers and the shared account quota.")
    parser.add_argument("calls", nargs="*", metavar="TOOL/JSON")
    args = parser.parse_args()
    if len(args.calls) % 2:
        parser.error("Each tool needs a JSON object.")
    try:
        calls = [(name, json.loads(raw)) for name, raw in zip(args.calls[::2], args.calls[1::2])]
    except ValueError as exc:
        parser.error(str(exc))
    if any(not isinstance(value, dict) for _, value in calls):
        parser.error("Tool arguments must be JSON objects.")
    sys.exit(asyncio.run(main("--live" if args.live else "--offline", calls)))
