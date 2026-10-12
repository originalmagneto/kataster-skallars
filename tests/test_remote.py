"""Remote trust boundaries, without calling cadastral providers."""

import hashlib
import json
import time

import pytest
from starlette.testclient import TestClient

from kataster_mcp.remote import create_app, MAX_UPLOAD
from test_core import FIX


@pytest.fixture
def remote(tmp_path):
    tokens = tmp_path / "tokens.json"
    tokens.write_text(
        json.dumps(
            [
                {
                    "tenant": name,
                    "sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires": time.time() + 3600,
                }
                for name, token in [("alice", "a" * 48), ("bob", "b" * 48)]
            ]
        )
    )
    app = create_app(tmp_path / "data", tokens, "http://testserver")
    with TestClient(app) as client:
        yield client, tokens


def headers(token="a" * 48):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }


def call(client, name, arguments, token="a" * 48):
    response = client.post(
        "/mcp",
        headers=headers(token),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_auth_expiry_revocation_and_origin(remote):
    client, tokens = remote
    assert client.get("/health").status_code == 200
    assert client.post("/mcp").status_code == 401
    assert client.post("/uploads", headers=headers("wrong")).status_code == 401
    assert (
        client.post(
            "/uploads", headers={**headers(), "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 421
    records = json.loads(tokens.read_text())
    records[0]["expires"] = time.time() - 1
    tokens.write_text(json.dumps(records))
    assert client.post("/uploads", headers=headers()).status_code == 401
    tokens.write_text("[]")
    assert client.post("/mcp", headers=headers("b" * 48)).status_code == 401


def test_upload_import_isolation_and_no_server_paths(remote):
    client, _ = remote
    uploaded = client.post(
        "/uploads",
        headers={**headers(), "Content-Type": "text/html"},
        content=(FIX / "lv_vypis_anon.html").read_bytes(),
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["file_id"]
    assert call(client, "kataster_lv_import", {"file_id": file_id}, "b" * 48)["isError"]
    result = call(client, "kataster_lv_import", {"file_id": file_id})
    assert not result.get("isError"), result
    assert "stored" in json.dumps(result)
    assert "/uploads/" not in json.dumps(result)
    assert call(client, "kataster_lv_import", {"path": "/etc/passwd"})["isError"]
    assert call(client, "kataster_lv_import", {"file_id": "../tokens.json"})["isError"]
    a = call(client, "kataster_osoba_prehlad", {"nazov": "FIKTÍVNY Vlastník"})
    b = call(client, "kataster_osoba_prehlad", {"nazov": "FIKTÍVNY Vlastník"}, "b" * 48)
    assert json.loads(a["content"][0]["text"])["data"]["osoby"][0]["pocet_lv"] == 1
    assert json.loads(b["content"][0]["text"])["data"]["osoby"] == []
    assert json.loads(b["content"][0]["text"])["data"]["importy"]["pocet_lv"] == 0


def test_limits_and_safe_discovery(remote):
    client, _ = remote
    assert (
        client.post(
            "/uploads",
            headers={**headers(), "Content-Type": "text/html"},
            content=b"x" * (MAX_UPLOAD + 1),
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/uploads",
            headers={**headers(), "Content-Type": "application/zip"},
            content=b"zip",
        ).status_code
        == 415
    )
    result = client.post(
        "/mcp",
        headers=headers(),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ).json()
    tools = {t["name"]: t for t in result["result"]["tools"]}
    assert "kataster_mapa" not in tools
    assert "path" not in tools["kataster_lv_import"]["inputSchema"]["properties"]
    assert "data_dir" not in json.dumps(call(client, "kataster_status", {}))


def test_expired_upload_and_unreadable_document(remote):
    import os

    client, tokens = remote
    upload = client.post(
        "/uploads",
        headers={**headers(), "Content-Type": "text/html"},
        content=b"not an LV",
    ).json()
    assert call(client, "kataster_lv_import", upload | {"expires": None})["isError"]
    assert call(client, "kataster_lv_import", {"file_id": upload["file_id"]})["isError"]
    path = tokens.parent / "data/users/alice/uploads" / upload["file_id"]
    os.utime(path, (time.time() - 90000, time.time() - 90000))
    assert call(client, "kataster_lv_import", {"file_id": upload["file_id"]})["isError"]


def test_shared_provider_limits_and_periodic_purge(tmp_path):
    import asyncio
    from kataster_mcp.remote import UPLOAD_TTL
    from kataster_mcp.cache import PERSONAL_TTL

    tokens = tmp_path / "tokens.json"
    tokens.write_text(
        json.dumps(
            [
                {
                    "tenant": name,
                    "sha256": hashlib.sha256(name.encode()).hexdigest(),
                    "expires": time.time() + 60,
                }
                for name in ["alice", "bob"]
            ]
        )
    )
    app = create_app(tmp_path / "data", tokens, "http://testserver")
    a, b = app.servers.values()
    assert a.app_state.http is b.app_state.http
    assert a.app_state.quota is b.app_state.quota
    assert a.app_state.http.blocks is app.shared
    a.app_state.osoby.put("test", "1", "private", {})
    a.app_state.osoby.db.execute(
        "UPDATE cache SET ulozene=?", (time.time() - PERSONAL_TTL - 1,)
    )
    a.app_state.osoby.db.commit()
    with TestClient(app):
        for _ in range(100):
            if not a.app_state.osoby.stats():
                break
            time.sleep(0.01)
        assert not a.app_state.osoby.stats()


def test_parser_timeout_kills_worker(monkeypatch):
    import asyncio
    from kataster_mcp import remote as module
    from mcp.server.mcpserver.exceptions import ToolError

    class Process:
        returncode = None
        killed = False

        async def communicate(self, raw):
            raise TimeoutError()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.returncode = -9

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(ToolError, match="20"):
        asyncio.run(module.parse_upload(b"input"))
    assert process.killed


def test_revoked_tenant_data_still_expires(tmp_path):
    import asyncio
    from contextlib import suppress
    from kataster_mcp.cache import Cache, PERSONAL_TTL
    from kataster_mcp.remote import UPLOAD_TTL

    old = tmp_path / "data/users/revoked"
    cache = Cache(old / "osoby.sqlite", private=True, max_age_s=PERSONAL_TTL)
    cache.put("lv", "1", "old", {})
    cache.db.execute("UPDATE cache SET ulozene=?", (time.time() - PERSONAL_TTL - 1,))
    cache.db.commit()
    cache.db.close()
    tokens = tmp_path / "tokens.json"
    tokens.write_text("[]")
    with TestClient(create_app(tmp_path / "data", tokens, "http://testserver")):
        for _ in range(100):
            import sqlite3

            with sqlite3.connect(old / "osoby.sqlite") as db:
                count = db.execute("SELECT count(*) FROM cache").fetchone()[0]
            if not count:
                break
            time.sleep(0.01)
        assert count == 0


def test_parallel_harness_discovery_waits_instead_of_failing(remote):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    client, _ = remote
    entered = threading.Event()

    @client.app.servers["alice"].tool()
    async def slow_probe() -> dict:
        entered.set()
        await asyncio.sleep(0.3)
        return {"ok": True}

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, client, "slow_probe", {})
        assert entered.wait(3)
        second = pool.submit(call, client, "kataster_status", {})
        assert not first.result().get("isError")
        assert not second.result().get("isError")
