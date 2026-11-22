"""Historical imagery and acquisition dates, with synthetic frames and offline transport."""

import io
import re
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from PIL import Image

from kataster_mcp import render
from kataster_mcp.policy import PUBLIC_POLICY
from kataster_mcp.server import create_server
from test_core import FakeTime, _call, _mock_http
from test_map_crops import _shifted

CYCLES = [("2017-2019", 1, 2018), ("2020-2022", 2, 2021)]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _date_row(year, day):
    stamp = datetime(year, 7, day, tzinfo=timezone.utc).timestamp()
    return {"attributes": {"DATUM": int(stamp * 1000)}}


@pytest.mark.anyio
@pytest.mark.parametrize("cycle,service,year", CYCLES)
async def test_historical_export(tmp_path, cycle, service, year):
    queries, exports, kn = [], [], []

    def handler(req):
        path, params = req.url.path, req.url.params
        if "cp_uo" in path:
            number = re.search(r"871541_(\d+)\.E", params["CQL_FILTER"])[1]
            return httpx.Response(200, json=_shifted(number))
        if params.get("REQUEST") == "GetMap":
            assert str(req.url).startswith(render.KN_URL)
            kn.append(path)
            buf = io.BytesIO()
            Image.new("RGBA", (int(params["WIDTH"]), int(params["HEIGHT"]))).save(buf, "PNG")
            return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})
        if path.endswith("/0/query"):
            assert f"/Ortofoto_{service}cyklus/MapServer/" in path
            queries.append(params["geometry"])
            assert params["inSR"] == "4326" and params["outFields"] == "DATUM"
            rows = [_date_row(year, 11)]
            if len(queries) == 1:
                rows.append(_date_row(year, 9))
            return httpx.Response(200, json={"features": rows})
        if path.endswith("/export"):
            assert f"/Ortofoto_{service}cyklus/MapServer/" in path
            w, h = map(int, params["size"].split(","))
            x1, y1, x2, y2 = map(float, params["bbox"].split(","))
            assert (x2 - x1) / (y2 - y1) == pytest.approx(w / h)
            exports.append((x1, y1, x2, y2, w))
            buf = io.BytesIO()
            Image.new("RGB", (w, h), "#50826c").save(buf, "PNG")
            return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})
        pytest.fail(f"Unexpected provider: {path}")

    http = _mock_http(PUBLIC_POLICY, handler, FakeTime())
    server = create_server(data_dir=tmp_path / "data", limits_dir=tmp_path / "limits", http=http)
    result = await _call(server, "kataster_mapa", {
        "parcely": [{"ku": "871541", "cislo": "E " + n} for n in ("503", "999")],
        "format": ["html", "png"], "podklad": "orto+kn" if service == 2 else "orto", "cyklus": cycle, "out_dir": str(tmp_path),
    })
    data = result["data"]
    assert len(kn) == (3 if service == 2 else 0)
    assert len(set(queries)) == len(exports) == 3
    for query, (left, bottom, right, top, width) in zip(queries, exports, strict=True):
        west, south, east, north = map(float, query.split(","))
        assert (south, north) == (bottom, top)
        assert (west + east) / 2 == pytest.approx((left + right) / 2, abs=1e-10)
        assert 0 <= west - left < (right - left) / width
    assert data["ortofoto"]["datum_od"] == date(year, 7, 9).isoformat()
    assert data["ortofoto"]["datum_do"] == date(year, 7, 11).isoformat()
    assert all(c["ortofoto"]["datum_od"] == f"{year}-07-11" for c in data["vyrezy"])
    page = Path(data["subory"]["html"]).read_text()
    with Image.open(data["subory"]["png"]) as image:
        caption = image.info["Description"]
        assert image.size == tuple(data["rozmer_px"])
    for text in (page, caption):
        for value in (cycle, f"{year}-07-09", f"{year}-07-11", "GKÚ Bratislava, NLC", "Hranice parciel sú súčasné"):
            assert value in text
    assert "tile.openstreetmap" not in page and page.count("L.imageOverlay(") == 3
    assert all("Ortofoto_" in entry["url"] for entry in result["zdroje"] if "ortofoto" in entry["id"])


@pytest.mark.parametrize("payload", [
    {}, {"features": []}, {"features": [_date_row(2018, 9)], "exceededTransferLimit": True},
    {"features": [_date_row(2018, 9), {"attributes": {"DATUM": None}}]},
    {"features": [_date_row(2021, 1)]}, {"error": {"code": 400}},
])
def test_incomplete_or_invalid_dates(payload):
    from kataster_mcp.ortofoto import acquisition

    info = acquisition("2017-2019", payload)
    assert info.start is info.end is None
    assert info.dates == "nezistený"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["unavailable", "blocked", "captcha_required"])
async def test_date_service_failure(failure):
    from kataster_mcp import ortofoto
    from kataster_mcp.envelope import Envelope, KatasterError

    class Offline:
        async def get(self, url, params):
            size = tuple(map(int, params["size"].split(",")))
            buf = io.BytesIO()
            Image.new("RGB", size, "#aaaaaa").save(buf, "PNG")
            return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})

        async def get_json(self, url, params):
            raise KatasterError(failure, "synthetic provider response")

    frame = render.Frame((19.1, 48.7, 19.11, 48.71))
    env = Envelope()
    if failure == "unavailable":
        _, info = await ortofoto.background(Offline(), frame, "2017-2019", env, {})
        assert info.start is None and env.varovania
    else:
        with pytest.raises(KatasterError) as caught:
            await ortofoto.background(Offline(), frame, "2017-2019", env, {})
        assert caught.value.kind == failure


@pytest.mark.anyio
async def test_archive_unavailable_has_no_fallback():
    from kataster_mcp import ortofoto
    from kataster_mcp.envelope import Envelope, KatasterError

    class Offline:
        async def get(self, url, params):
            assert "/Ortofoto_2cyklus/" in url
            return httpx.Response(200, json={"error": {"code": 500}})

    with pytest.raises(KatasterError, match="Ortofoto 2020-2022"):
        await ortofoto.background(Offline(), render.Frame((19, 48, 19.01, 48.01)), "2020-2022", Envelope(), {})


@pytest.mark.anyio
@pytest.mark.parametrize("background,formats", [("osm", ["png"]), ("kn", ["html"]), ("orto", ["kml"])])
async def test_invalid_options_before_parcel_lookup(tmp_path, background, formats):
    from mcp.server.mcpserver.exceptions import ToolError
    from kataster_mcp.envelope import tool_error_envelope

    def unexpected(req):
        pytest.fail("Invalid input must be rejected before a network request")

    server = create_server(data_dir=tmp_path, http=_mock_http(PUBLIC_POLICY, unexpected, FakeTime()))
    with pytest.raises(ToolError) as caught:
        await server.call_tool("kataster_mapa", {
            "parcely": [{"ku": "871541", "cislo": "E 503"}], "format": formats,
            "cyklus": "2017-2019", "podklad": background,
        })
    assert tool_error_envelope(str(caught.value))["chyba"]["typ"] == "invalid_input"


def test_png_font_renders_slovak_accents_without_system_fonts(monkeypatch):
    truetype = render.ImageFont.truetype

    def packaged_only(font, size):
        if Path(font).is_absolute():
            return truetype(font, size)
        raise OSError("No system fonts")

    monkeypatch.setattr(render.ImageFont, "truetype", packaged_only)
    font = render._font(20)
    missing = bytes(font.getmask("\u0378"))
    assert all(bytes(font.getmask(c)) != missing for c in "áčéíľňóšťúýžÚ")
