"""Exercise the transportable QGIS project through both map tool registrations."""

import asyncio
import base64
import io
import json
from pathlib import Path
from urllib.parse import parse_qs
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from kataster_mcp import render, server
from test_mapa import REQUEST, offline  # noqa: F401
from test_remote import call, remote  # noqa: F401


def test_local_project(tmp_path, offline, monkeypatch):
    def unexpected(*args):
        pytest.fail("QGIS export must not fetch basemaps or render images")

    monkeypatch.setattr(render, "background", unexpected)
    mcp = server.create_server(data_dir=tmp_path / "data")
    result = asyncio.run(mcp.call_tool("kataster_mapa", {
        **REQUEST, "format": ["qgis"], "qgis_vrstvy": ["dmr", "ochrana", "dmr"],
        "out_dir": str(tmp_path), "podklad": "orto+kn",
    }))
    data = json.loads(result.content[0].text)["data"]
    path = Path(data["subory"]["qgis"])
    assert path.suffix == ".zip" and not any(data["podklad_dotazy"].values())
    with ZipFile(path) as archive:
        assert set(archive.namelist()) == {"kataster.qgs", "parcely.geojson", "ZDROJE.txt"}
        root = ET.fromstring(archive.read("kataster.qgs"))
        features = json.loads(archive.read("parcely.geojson"))["features"]
        assert features[0]["geometry"]["type"] == "Polygon"
        assert set(features[0]["properties"]) == {"ku_kod","ku_nazov","cislo","register","oznacenie","vymera_m2"}
        layers = {el.findtext("id").split("_")[0]: el for el in root.findall("projectlayers/maplayer")}
        assert set(layers) == {"parcely", "orto", "kn", "dmr", "ochrana"}
        assert layers["parcely"].findtext("datasource") == "./parcely.geojson"
        assert root.findtext("projectCrs/spatialrefsys/authid") == "EPSG:4326"
        tree = root.findall("layer-tree-group/layer-tree-layer")
        assert tree[0].get("id") == layers["parcely"].findtext("id")
        assert {n.get("id").split("_")[0] for n in tree if n.get("checked") == "Qt::Checked"} == {"parcely","orto","kn"}
        for name in ("orto", "kn", "dmr", "ochrana"):
            uri = parse_qs(layers[name].findtext("datasource"), keep_blank_values=True)
            assert "crs=EPSG:4326" in layers[name].findtext("datasource")
            assert uri["url"][0].startswith("https://") and uri["crs"] == ["EPSG:4326"]
            assert len(uri["layers"]) == len(uri["styles"])
            assert uri["url"][0] in archive.read("ZDROJE.txt").decode()
        assert parse_qs(layers["kn"].findtext("datasource"))["layers"] == render.KN_LAYERS.split(",")


def test_remote_project(remote, offline):
    client, _ = remote
    result = call(client, "kataster_mapa", {**REQUEST, "format": ["qgis", "kml"]})
    assert not result.get("isError"), result
    summary, binary, text = result["content"]
    item = json.loads(summary["text"])["data"]["subory"][0]
    resource = binary["resource"]
    assert resource["mimeType"] == "application/zip" and resource["uri"] == item["uri"]
    assert item["format"] == "qgis" and item["uri"].endswith(".zip")
    raw = base64.b64decode(resource["blob"], validate=True)
    assert item["bajty"] == len(raw)
    with ZipFile(io.BytesIO(raw)) as archive:
        assert len(ET.fromstring(archive.read("kataster.qgs")).findall("projectlayers/maplayer")) == 3
    assert text["resource"]["text"].startswith("<?xml")


@pytest.mark.parametrize("extra", [0, 1])
def test_remote_qgis_combined_limit(remote, offline, monkeypatch, extra):
    from kataster_mcp import qgis

    monkeypatch.setattr(qgis, "bundle", lambda *args: b"x" * (8 * 1024**2 - 2))
    monkeypatch.setattr(render, "geojson", lambda *args: "{}" + " " * extra)
    result = call(remote[0], "kataster_mapa", {**REQUEST, "format": ["qgis", "geojson"]})
    if extra:
        assert result.get("isError") and "príliš veľká" in result["content"][0]["text"]
    else:
        assert not result.get("isError")
        assert sum(i["bajty"] for i in json.loads(result["content"][0]["text"])["data"]["subory"]) == 8 * 1024**2


def test_cli_saves_remote_qgis_attachment(tmp_path):
    from mcp import types
    from kataster_mcp.remote_client import save_qgis
    from kataster_mcp.envelope import KatasterError

    target = tmp_path / "projekt.zip"
    item = types.EmbeddedResource(type="resource", resource=types.BlobResourceContents(
        uri="kataster://mapa/priklad.zip", mime_type="application/zip", blob=base64.b64encode(b"bundle").decode()))
    with pytest.raises(KatasterError):
        save_qgis([], target)
    assert not target.exists()
    save_qgis([item], target)
    assert target.read_bytes() == b"bundle"
    with pytest.raises(FileExistsError):
        save_qgis([item], target)


def test_qgis_visible_layers_labels_and_invalid_options(remote, offline):
    client, _ = remote
    for background in ("kn", "orto", "osm"):
        res = call(client, "kataster_mapa", {**REQUEST, "format": ["qgis"], "podklad": background, "popisky": False})
        with ZipFile(io.BytesIO(base64.b64decode(res["content"][1]["resource"]["blob"]))) as archive:
            root = ET.fromstring(archive.read("kataster.qgs"))
        visible = [n.get("id").split("_")[0] for n in root.findall("layer-tree-group/layer-tree-layer")
                   if n.get("checked") == "Qt::Checked"]
        assert visible == ["parcely", background]
        assert root.findtext("properties/SpatialRefSys/ProjectionsEnabled") == "1"
        assert root.find("projectlayers/maplayer").get("labelsEnabled") == "0"
        assert root.find("ProjectViewSettings/DefaultViewExtent").get("xmin")
        for node in root.findall("projectlayers/maplayer"):
            assert len(node.findtext("id")) > 12 and node.findtext("srs/spatialrefsys/srsid")
    for options in ({"format": ["qgis", "html"], "cyklus": "2017-2019"},
                    {"format": ["geojson"], "qgis_vrstvy": ["ochrana"]},
                    {"format": ["qgis"], "qgis_vrstvy": ["https://example.invalid/"]}):
        result = call(client, "kataster_mapa", {**REQUEST, **options})
        assert result.get("isError")
