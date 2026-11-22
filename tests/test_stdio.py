"""Real local stdio handshake and tool calls; synthetic inputs and isolated state."""

import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


pytestmark = pytest.mark.usefixtures("isolated_subprocess_limits")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_stdio_discovery_and_incomplete_lv(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "kataster_mcp.server"],
        env={**os.environ, "SK_KATASTER_DATA_DIR": str(tmp_path / "data")},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as client,
    ):
        init = await client.initialize()
        assert init.server_info.version == "0.12.0"
        tools = await client.list_tools()
        assert "kataster_lv_import" in {tool.name for tool in tools.tools}
        result = await client.call_tool(
            "kataster_lv_import", {"html": "<p>VÝPIS Z LISTU VLASTNÍCTVA č. 1</p>"}
        )
        assert not result.is_error
        out = result.structured_content or json.loads(result.content[0].text)
        assert out["data"]["tarchy"] == "unknown"
        assert out["varovania"]
        result = await client.call_tool("kataster_osoba_prehlad", {"ico": "abc"})
        assert result.is_error
    assert (tmp_path / "data" / "osoby.sqlite").exists()


@pytest.mark.anyio
async def test_local_cli_and_stdio_share_migrated_quota(tmp_path):
    import sqlite3
    import subprocess

    from kataster_mcp.cache import today

    cli_dir, mcp_dir = tmp_path / "cli", tmp_path / "mcp"
    cli_dir.mkdir()
    with sqlite3.connect(cli_dir / "osoby.sqlite") as old:
        old.execute("CREATE TABLE kvota (den TEXT, parcela TEXT, PRIMARY KEY (den, parcela))")
        old.execute("INSERT INTO kvota VALUES (?, ?)", (today(), "synthetic-parcel"))

    output = subprocess.check_output(
        [sys.executable, "-m", "kataster_mcp.cli", "--json", "--data-dir", str(cli_dir),
         "call", "kataster_status", "{}"], timeout=30,
    )
    cli_state = json.loads(output)["data"]
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "kataster_mcp.server"],
        env={**os.environ, "SK_KATASTER_DATA_DIR": str(mcp_dir)},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        await client.initialize()
        result = await client.call_tool("kataster_status", {})
        assert not result.is_error
        mcp_state = (result.structured_content or json.loads(result.content[0].text))["data"]
    assert cli_state["data_dir"] != mcp_state["data_dir"]
    assert cli_state["limity_dir"] == mcp_state["limity_dir"]
    assert cli_state["kvota_vlastnici"]["pouzite"] == mcp_state["kvota_vlastnici"]["pouzite"] == 1


def test_offline_smoke_isolated_and_refuses_provider(tmp_path):
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_stdio.py"
    command = [sys.executable, str(script), "--offline"]
    state = tmp_path / "normal-state"
    env = {**os.environ, "SK_KATASTER_DATA_DIR": str(state)}
    args = ["kataster_status", "{}", "kataster_parcela", '{"ku":"871541","cislo":"E 503"}']
    run = subprocess.run(command + args, cwd=tmp_path, env=env, capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert run.returncode != 0 and "offline smoke" in run.stdout
    assert "kataster_status" in run.stdout and not state.exists()
