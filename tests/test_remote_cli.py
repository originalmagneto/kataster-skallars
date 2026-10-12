"""Real subprocess HTTP client/server handshake with synthetic uploads."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

from test_core import FIX


def test_remote_cli_roundtrip(tmp_path):
    token = "synthetic-token-" + "a" * 40
    key = tmp_path / "remote.token"
    key.write_text(token)
    records = tmp_path / "tokens.json"
    records.write_text(
        json.dumps(
            [
                {
                    "tenant": "synthetic",
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires": time.time() + 120,
                }
            ]
        )
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    code = 'import uvicorn; from pathlib import Path; from kataster_mcp.remote import create_app; import sys; uvicorn.run(create_app(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]),host="127.0.0.1",port=int(sys.argv[4]),access_log=False)'
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            str(tmp_path / "data"),
            str(records),
            origin,
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def cli(*args):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kataster_mcp.cli",
                "--json",
                "remote",
                "--url",
                origin,
                "--token-file",
                str(key),
                *args,
            ],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        return result.returncode, json.loads(result.stdout)

    try:
        for _ in range(100):
            try:
                if httpx.get(origin + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        with httpx.stream(
            "GET",
            origin + "/mcp",
            headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"},
            timeout=2,
        ) as stream:
            assert stream.status_code == 405
        with httpx.stream(
            "POST",
            origin + "/mcp",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2026-07-28",
                "Mcp-Method": "subscriptions/listen",
            },
            json={
                "jsonrpc": "2.0",
                "id": "listen-test",
                "method": "subscriptions/listen",
                "params": {
                    "notifications": {"toolsListChanged": True},
                    "_meta": {
                        "io.modelcontextprotocol/clientCapabilities": {},
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    },
                },
            },
            timeout=2,
        ) as stream:
            assert stream.status_code == 200, stream.read().decode()
            response = httpx.post(
                origin + "/mcp",
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                timeout=2,
            )
            assert response.status_code == 200
            assert len(response.json()["result"]["tools"]) == 10
        assert cli("tools")[0] == 0
        code, result = cli("call", "kataster_ku", '{"query":"Záhorská Bystrica"}')
        assert code == 0 and result["data"][0]["kod"] == "871796"
        code, uploaded = cli("upload", str(FIX / "lv_vypis_anon.html"))
        assert code == 0
        code, imported = cli(
            "call",
            "kataster_lv_import",
            json.dumps({"file_id": uploaded["data"]["file_id"]}),
        )
        assert code == 0 and imported["data"]["lv"] == "1926"
        key.write_text("invalid")
        code, result = cli("tools")
        assert code == 1 and result["chyba"]["typ"] == "unavailable"
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_remote_oauth_default_and_explicit_legacy(tmp_path, monkeypatch):
    from kataster_mcp.cli import parser
    from kataster_mcp import remote_client
    from kataster_mcp.envelope import Envelope

    monkeypatch.delenv("SK_KATASTER_TOKEN", raising=False)
    calls = []
    monkeypatch.setattr(
        remote_client.cli_auth,
        "access_token",
        lambda path, resource: calls.append((path, resource)) or "synthetic-oauth",
    )

    async def request(args, headers):
        return Envelope().ok({"authorization": headers["Authorization"]})

    monkeypatch.setattr(remote_client, "mcp_request", request)
    args = parser().parse_args(
        ["remote", "--auth-file", str(tmp_path / "auth.json"), "tools"]
    )
    assert args.token_file is None
    assert (
        remote_client.execute(args)["data"]["authorization"] == "Bearer synthetic-oauth"
    )
    assert len(calls) == 1
    key = tmp_path / "legacy.token"
    key.write_text("synthetic-legacy")
    args = parser().parse_args(["remote", "--token-file", str(key), "tools"])
    assert (
        remote_client.execute(args)["data"]["authorization"]
        == "Bearer synthetic-legacy"
    )
    monkeypatch.setenv("SK_KATASTER_TOKEN", "synthetic-env")
    assert (
        remote_client.execute(args)["data"]["authorization"] == "Bearer synthetic-env"
    )
    assert len(calls) == 1


def test_remote_status_json_outside_checkout(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "kataster_mcp.cli",
            "--json",
            "remote",
            "--auth-file",
            str(tmp_path / "oauth.json"),
            "status",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["authenticated"] is False
    assert not result.stderr
