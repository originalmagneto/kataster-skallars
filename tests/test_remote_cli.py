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
