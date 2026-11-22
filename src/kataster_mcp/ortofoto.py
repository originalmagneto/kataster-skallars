"""Archived ZBGIS orthophotos and the acquisition footprints for each exported frame."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, Literal

from PIL import Image

from . import render
from .envelope import KatasterError

Cycle = Literal["2017-2019", "2020-2022"]
_SERVICES = {"2017-2019": "Ortofoto_1cyklus", "2020-2022": "Ortofoto_2cyklus"}
BOUNDARIES = "Hranice parciel sú súčasné."


@dataclass(frozen=True)
class Acquisition:
    source: ClassVar[str] = "GKÚ Bratislava, NLC"
    cycle: Cycle
    start: str | None
    end: str | None

    @property
    def dates(self) -> str:
        if self.start is None:
            return "nezistený"
        return self.start if self.start == self.end else f"{self.start} až {self.end}"

    def metadata(self) -> dict:
        return {"cyklus": self.cycle, "datum_od": self.start, "datum_do": self.end,
                "zdroj": self.source, "hranice": BOUNDARIES}

    def lines(self) -> list[str]:
        return [f"Ortofoto {self.cycle} · {self.source}", f"Dátum snímkovania: {self.dates}", BOUNDARIES]


def acquisition(cycle: Cycle, payload) -> Acquisition:
    unknown = Acquisition(cycle, None, None)
    if not isinstance(payload, dict) or payload.get("error") or payload.get("exceededTransferLimit"):
        return unknown
    rows = payload.get("features")
    if not isinstance(rows, list) or not rows:
        return unknown
    dates = []
    first, last = map(int, cycle.split("-"))
    for row in rows:
        try:
            stamp = row["attributes"]["DATUM"]
            if type(stamp) is not int:
                return unknown
            day = datetime.fromtimestamp(stamp / 1000, timezone.utc).date()
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            return unknown
        if not first <= day.year <= last:
            return unknown
        dates.append(day.isoformat())
    return Acquisition(cycle, min(dates), max(dates))


async def background(http, frame: render.Frame, cycle: Cycle, env, stats):
    url = f"https://zbgis.skgeodesy.sk/zbgis/rest/services/{_SERVICES[cycle]}/MapServer"
    # ArcGIS expands a mismatched bbox to square angular pixels. Request that grid
    # explicitly, then resample its exact inner extent onto the parcel frame.
    step = (frame.maxy - frame.miny) / frame.height
    span = (frame.maxx - frame.minx) / step
    width = math.ceil(span)
    margin = (width - span) / 2
    bounds = f"{frame.minx},{frame.miny},{frame.maxx},{frame.maxy}"
    expanded = f"{frame.minx - margin * step},{frame.miny},{frame.maxx + margin * step},{frame.maxy}"
    stats["archivne_vyrezy"] = stats.get("archivne_vyrezy", 0) + 1
    response = await http.get(url + "/export", {
        "bbox": expanded, "bboxSR": "4326", "imageSR": "4326", "size": f"{width},{frame.height}",
        "format": "png32", "transparent": "true", "f": "image",
    })
    try:
        image = render._image(response, f"Ortofoto {cycle}")
    except OSError as exc:
        raise KatasterError("unavailable", f"Archív nevrátil čitateľný obrázok pre cyklus {cycle}.") from exc
    if image.size != (width, frame.height) or not image.getchannel("A").getbbox():
        raise KatasterError("unavailable", f"Archív nevrátil požadovaný výrez pre cyklus {cycle}.")
    image = image.resize((frame.width, frame.height), Image.Resampling.BILINEAR,
                         box=(margin, 0, width - margin, frame.height))
    env.source("zbgis_ortofoto_archiv", url, oficialny=True, z_cache=False)
    query = url + "/0/query"
    params = {"geometry": bounds, "geometryType": "esriGeometryEnvelope", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects", "outFields": "DATUM", "returnGeometry": "false", "f": "json"}
    stats["datum_dotazy"] = stats.get("datum_dotazy", 0) + 1
    try:
        payload = await http.get_json(query, params)
        env.source("zbgis_ortofoto_datum", query, oficialny=True, z_cache=False)
    except KatasterError as exc:
        if exc.kind not in ("unavailable", "parser_drift"):
            raise
        payload = None
    info = acquisition(cycle, payload)
    if info.start is None:
        env.warn(f"Pre výrez ortofota {cycle} sa nepodarilo zistiť úplné údaje o dátume snímkovania.")
    return image, info
