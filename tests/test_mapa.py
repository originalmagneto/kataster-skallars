"""kataster_mapa: one renderer, files locally, inline content remotely. No provider calls."""

import asyncio
import base64
import json

import pytest
from PIL import Image

from kataster_mcp import render, server
from test_core import FIX
from test_remote import call, remote  # noqa: F401  (pytest fixture)

GEOMETRY = json.loads((FIX / "wfs_e599_3_geom.json").read_text())
REQUEST = {"parcely": [{"ku": "800001", "cislo": "599/3", "register": "E"}]}


@pytest.fixture
def offline(monkeypatch):
    async def find_parcel(app, env, ku, cislo, register):
        return {"ku_kod": "800001", "register": "E", "cislo": cislo, "oznacenie": "E " + cislo,
                "vymera_m2": 1234, "geometria": GEOMETRY}

    async def background(http, frame, podklad, env):
        return Image.new("RGBA", (frame.width, frame.height), (255, 255, 255, 255))

    monkeypatch.setattr(server, "find_parcel", find_parcel)
    monkeypatch.setattr(render, "background", background)


def test_local_map_writes_requested_files(tmp_path, offline):
    mcp = server.create_server(data_dir=tmp_path / "data")
    out = tmp_path / "out"
    result = asyncio.run(mcp.call_tool(
        "kataster_mapa", {**REQUEST, "format": ["png", "geojson"], "out_dir": str(out)}))
    data = json.loads(result.content[0].text)["data"]
    assert set(data["subory"]) == {"png", "geojson"}
    assert (out / data["subory"]["png"].rsplit("/", 1)[1]).read_bytes()[:4] == b"\x89PNG"
    assert data["parcely"] == ["E 599/3"]


def test_remote_map_is_inline_and_leaves_no_files(remote, offline, tmp_path):
    client, _ = remote
    tools = client.post(
        "/mcp",
        headers={"Authorization": "Bearer " + "a" * 48, "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ).json()["result"]["tools"]
    schema = next(t for t in tools if t["name"] == "kataster_mapa")["inputSchema"]["properties"]
    assert "out_dir" not in schema and "nazov" not in schema

    result = call(client, "kataster_mapa", {**REQUEST, "format": ["png", "geojson", "kml", "html"]})
    assert not result.get("isError"), result
    content = result["content"]
    assert [c["type"] for c in content] == ["text", "image", "resource", "resource", "resource"]
    assert content[1]["mimeType"] == "image/png"
    assert base64.b64decode(content[1]["data"])[:4] == b"\x89PNG"
    resources = {c["resource"]["mimeType"]: c["resource"] for c in content[2:]}
    assert set(resources) == {"application/geo+json", "application/vnd.google-earth.kml+xml", "text/html"}
    assert "vlastn" not in resources["application/geo+json"]["text"].lower()

    data = json.loads(content[0]["text"])["data"]
    assert [f["format"] for f in data["subory"]] == ["png", "geojson", "kml", "html"]
    assert all(f["uri"].startswith("kataster://mapa/") for f in data["subory"])
    assert str(tmp_path) not in json.dumps(result)
    assert not [p for p in tmp_path.rglob("*") if p.suffix in {".png", ".geojson", ".kml", ".html"}]


def test_remote_map_rejects_oversized_output(remote, offline, monkeypatch):
    client, _ = remote
    monkeypatch.setattr(render, "render_png", lambda *a, **k: b"\x89PNG" + b"0" * (16 * 1024**2))
    result = call(client, "kataster_mapa", REQUEST)
    assert result.get("isError")
    assert "príliš veľká" in json.dumps(result, ensure_ascii=False)
