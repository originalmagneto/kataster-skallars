"""Remote CLI uses the same public HTTP/MCP endpoints as other clients."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .envelope import Envelope, KatasterError


def add_parser(commands) -> None:
    remote = commands.add_parser(
        "remote", help="Samostatný Dokploy server: upload a MCP."
    )
    remote.add_argument(
        "--url",
        default=os.environ.get(
            "SK_KATASTER_URL", "https://mcp-kataster.aittorney.online"
        ),
    )
    remote.add_argument(
        "--token-file",
        type=Path,
        default=Path.home() / ".config/kataster-skallars/remote.token",
    )
    actions = remote.add_subparsers(dest="action", required=True)
    actions.add_parser("doctor")
    actions.add_parser("upload").add_argument("path", type=Path)
    actions.add_parser("tools").add_argument("name", nargs="?")
    call = actions.add_parser("call")
    call.add_argument("name")
    call.add_argument("arguments")


async def mcp_request(args: argparse.Namespace, headers: dict[str, str]) -> dict:
    async with httpx2.AsyncClient(headers=headers, timeout=125) as client:
        async with streamable_http_client(
            args.url.rstrip("/") + "/mcp", http_client=client
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if args.action == "tools":
                    tools = (await session.list_tools()).tools
                    if not args.name:
                        return Envelope().ok({"tools": [tool.name for tool in tools]})
                    tool = next(
                        (tool for tool in tools if tool.name == args.name), None
                    )
                    if tool is None:
                        raise KatasterError("not_found", "Nástroj sa nenašiel.")
                    return Envelope().ok(
                        tool.model_dump(by_alias=True, exclude_none=True)
                    )
                arguments = json.loads(args.arguments)
                if not isinstance(arguments, dict):
                    raise KatasterError(
                        "invalid_input", "Argumenty musia byť JSON objekt."
                    )
                result = await session.call_tool(args.name, arguments)
                if result.is_error:
                    raise KatasterError(
                        "unavailable",
                        "\n".join(c.text for c in result.content if hasattr(c, "text")),
                    )
                return result.structured_content or json.loads(result.content[0].text)


def execute(args: argparse.Namespace) -> dict:
    url = urlsplit(args.url)
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
    ):
        raise KatasterError("invalid_input", "Remote URL vyžaduje HTTPS.")
    token = (
        os.environ.get("SK_KATASTER_TOKEN")
        or args.token_file.read_text(encoding="utf-8").strip()
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if args.action in ("tools", "call"):
            return asyncio.run(mcp_request(args, headers))
        with httpx.Client(timeout=125, follow_redirects=False) as client:
            if args.action == "doctor":
                response = client.get(args.url.rstrip("/") + "/health")
            else:
                with args.path.open("rb") as handle:
                    raw = handle.read(5 * 1024**2 + 1)
                if len(raw) > 5 * 1024**2:
                    raise KatasterError("invalid_input", "Limit uploadu je 5 MiB.")
                headers["Content-Type"] = (
                    "application/pdf" if raw.startswith(b"%PDF") else "text/html"
                )
                response = client.post(
                    args.url.rstrip("/") + "/uploads", headers=headers, content=raw
                )
            response.raise_for_status()
            return Envelope().ok(response.json())
    except (httpx.HTTPError, httpx2.HTTPError) as error:
        raise KatasterError(
            "unavailable", f"Remote požiadavka zlyhala: {type(error).__name__}."
        ) from None
    except ExceptionGroup:
        raise KatasterError(
            "unavailable",
            "MCP spojenie zlyhalo. Overte URL, token, expiráciu a dostupnosť servera.",
        ) from None
