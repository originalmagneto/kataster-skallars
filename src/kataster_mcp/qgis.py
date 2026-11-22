"""Portable QGIS project with local parcel geometry and optional public map services."""

import io
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from . import render
from .sources import layers, wfs

Theme = Literal["dmr", "ochrana"]


@dataclass(frozen=True)
class MapService:
    name: str
    credit: str
    url: str
    layers: tuple[str, ...]
    image_format: str = "image/png"

    def uri(self) -> str:
        return urlencode({"url": self.url, "layers": self.layers, "styles": [""] * len(self.layers),
                          "crs": "EPSG:4326", "format": self.image_format}, doseq=True, safe=":/")


SERVICES = {
    "kn": MapService("Katastrálna mapa", "ÚGKK SR", render.KN_URL, tuple(render.KN_LAYERS.split(","))),
    "orto": MapService("Ortofotomozaika", "GKÚ Bratislava, NLC", render.ORTO_URL, ("1",), "image/jpeg"),
    "dmr": MapService("Tieňovaný reliéf DMR 5.0", "ÚGKK SR", layers.DMR_URL, ("0",)),
    "ochrana": MapService("Chránené územia", "ŠOP SR", layers.SOP_URL + "/chranene_objekty/wms",
                          tuple(layer for workspace, layer, _, _ in layers.SOP_LAYERS if workspace == "chranene_objekty")),
}


def _crs(parent: ET.Element, web_mercator: bool = False) -> None:
    spatial = ET.SubElement(parent, "spatialrefsys")
    ET.SubElement(spatial, "srsid").text = "3857" if web_mercator else "3452"
    ET.SubElement(spatial, "authid").text = "EPSG:3857" if web_mercator else "EPSG:4326"


def _layer(project_layers, tree, key, name, provider, uri, checked):
    node = ET.SubElement(project_layers, "maplayer", type="vector" if provider == "ogr" else "raster")
    _crs(ET.SubElement(node, "srs"), web_mercator=(key == "osm"))
    layer_id = f"{key}_{uuid4().hex}"
    for tag, value in (("id", layer_id), ("layername", name), ("datasource", uri), ("provider", provider)):
        ET.SubElement(node, tag).text = value
    ET.SubElement(tree, "layer-tree-layer", id=layer_id, name=name, expanded="0", providerKey=provider, source=uri,
                  checked="Qt::Checked" if checked else "Qt::Unchecked")
    return node


def _parcel_style(node, labels):
    node.set("geometry", "Polygon")
    node.set("labelsEnabled", "1" if labels else "0")
    rend = ET.SubElement(node, "renderer-v2", type="singleSymbol", symbollevels="0")
    symbol = ET.SubElement(ET.SubElement(rend, "symbols"), "symbol", type="fill", name="0", alpha="1")
    fill = ET.SubElement(symbol, "layer", {"class": "SimpleFill", "enabled": "1"})
    options = ET.SubElement(fill, "Option", type="Map")
    for name, value in (("style", "no"), ("outline_color", "200,45,64,255"), ("outline_width", "0.65")):
        ET.SubElement(options, "Option", type="QString", name=name, value=value)
    if labels:
        settings = ET.SubElement(ET.SubElement(node, "labeling", type="simple"), "settings")
        ET.SubElement(settings, "text-style", fieldName="oznacenie", isExpression="0", fontSize="10")


def bundle(parcels: list[dict], frame: render.Frame, title: str, background: str,
           labels: bool, themes: list[Theme]) -> bytes:
    project = ET.Element("qgis", version="3.40.0", projectname=title)
    ET.SubElement(project, "title").text = title
    spatial = ET.SubElement(ET.SubElement(project, "properties"), "SpatialRefSys")
    ET.SubElement(spatial, "ProjectionsEnabled", type="int").text = "1"
    _crs(ET.SubElement(project, "projectCrs"))
    view = ET.SubElement(project, "ProjectViewSettings")
    extent = ET.SubElement(view, "DefaultViewExtent", xmin=str(frame.minx), ymin=str(frame.miny),
                           xmax=str(frame.maxx), ymax=str(frame.maxy))
    _crs(extent)
    tree = ET.SubElement(project, "layer-tree-group", name="", checked="Qt::Checked", expanded="1")
    project_layers = ET.SubElement(project, "projectlayers")
    vector = _layer(project_layers, tree, "parcely", "Vybrané parcely", "ogr", "./parcely.geojson", True)
    _parcel_style(vector, labels)

    sources = ["Parcely: ÚGKK SR, INSPIRE WFS. Hranice parciel sú súčasné."]
    sources.extend(wfs.url_for(reg) for reg in sorted({p["register"] for p in parcels}))
    for key in dict.fromkeys(["kn", *themes, "orto"]):
        service = SERVICES[key]
        visible = key in background.split("+")
        _layer(project_layers, tree, key, f"{service.name} ({service.credit})", "wms", service.uri(), visible)
        sources.append(f"{service.name}: {service.credit}\n{service.url}\nWMS: {', '.join(service.layers)}")
    if background == "osm":
        uri = urlencode({"type": "xyz", "url": render.OSM_TILES, "zmin": 0, "zmax": 19}, safe=":/")
        _layer(project_layers, tree, "osm", "OpenStreetMap (© OpenStreetMap contributors)", "wms", uri, True)
        sources.append("OpenStreetMap: © OpenStreetMap contributors\nhttps://www.openstreetmap.org/copyright")

    notes = ("Rozbaľte celý ZIP do jedného priečinka a otvorte kataster.qgs v QGIS. "
             "Geometria je uložená v parcely.geojson (WGS 84, EPSG:4326). "
             "Mapové služby vyžadujú pripojenie a zobrazujú údaje dostupné pri otvorení projektu.\n\n")
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("kataster.qgs", ET.tostring(project, encoding="utf-8", xml_declaration=True))
        archive.writestr("parcely.geojson", render.geojson(parcels))
        archive.writestr("ZDROJE.txt", notes + "\n\n".join(sources) + "\n")
    return output.getvalue()
