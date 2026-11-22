"""kataster_mapa: PNG / HTML / GeoJSON / KML of parcels. Geometry only, never owners."""

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Literal

from mcp import types
from pydantic import Field
from shapely.ops import unary_union

from . import geo, ortofoto, qgis, render
from .cache import restrict
from .envelope import Envelope, KatasterError
from .skupina import MAX_PARCELS, ParcelRef

Format = Literal["png", "html", "geojson", "kml", "qgis"]
MIME = {
    "png": "image/png",
    "html": "text/html",
    "geojson": "application/geo+json",
    "qgis": "application/zip",
    "kml": "application/vnd.google-earth.kml+xml",
}
MAX_INLINE = 8 * 1024**2  # remote result size, all formats together

Parcels = Annotated[list[ParcelRef], Field(description=f"Parcels to draw (max {MAX_PARCELS}).")]
Formats = Annotated[list[Format], Field(description="Outputs: png (rendered map), html (interactive Leaflet map), geojson, kml, qgis (ZIP containing a QGIS project and parcel GeoJSON).")]
Podklad = Annotated[Literal["orto", "kn", "orto+kn", "osm"], Field(description="Background: orto (ZBGIS orthophoto), kn (cadastral map), orto+kn, osm (OpenStreetMap).")]
Themes = Annotated[list[qgis.Theme] | None, Field(description="Optional QGIS WMS layers: dmr (shaded relief), ochrana (protected areas).")]
Cyklus = Annotated[ortofoto.Cycle | None, Field(description="Historical orthophoto cycle for PNG/HTML with orto or orto+kn. Omit for current imagery. Parcel boundaries are current.")]
Popisky = Annotated[bool, Field(description="Label parcels with register and number.")]


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")
    return s[:60] or "mapa"


async def build(app, env: Envelope, parcely: list[ParcelRef], formats: list[str], podklad: str, popisky: bool, cyklus: ortofoto.Cycle | None = None,
                qgis_vrstvy: list[qgis.Theme] | None = None):
    """Render the requested formats in memory. Returns parcels, rendered files and metadata shared by local and remote exports."""
    from .server import _with_ku, find_parcel

    if not parcely or len(parcely) > MAX_PARCELS:
        raise KatasterError("invalid_input", f"Give 1 to {MAX_PARCELS} parcels.")
    if cyklus and (podklad not in ("orto", "orto+kn") or not {"png", "html"}.intersection(formats)):
        raise KatasterError("invalid_input", "Historický cyklus vyžaduje podklad orto alebo orto+kn a formát png alebo html.")
    if qgis_vrstvy and "qgis" not in formats:
        raise KatasterError("invalid_input", "Parameter qgis_vrstvy vyžaduje formát qgis.")
    if cyklus and "qgis" in formats:
        raise KatasterError("invalid_input", "QGIS používa aktuálne mapové služby. Historický cyklus exportujte samostatne do PNG alebo HTML.")
    found = [_with_ku(await find_parcel(app, env, r.ku, r.cislo, r.register)) for r in parcely]
    shapes = [geo.parcel_shape(p["geometria"]) for p in found]
    frame = render.Frame(unary_union(shapes).bounds)
    fmts = list(dict.fromkeys(formats))
    stats: dict[str, int] = {}
    crop_info = []

    async def background(area):
        if cyklus is None:
            return await render.background(app.http, area, podklad, env, stats), None
        image, info = await ortofoto.background(app.http, area, cyklus, env, stats)
        if podklad == "orto+kn":
            image = await render.add_kn(app.http, area, image, env, stats)
        return image, info

    bg, overview = None, None
    if "png" in fmts or "html" in fmts:
        bg, overview = await background(frame)
    title = ", ".join(f"{p['register']} {p['cislo']}" for p in found[:5]) + f" · {found[0].get('ku_nazov') or found[0]['ku_kod']}"
    outputs = {}
    for fmt in fmts:
        if fmt == "png":
            outputs[fmt] = render.render_png(bg, frame, found, shapes, podklad, popisky, overview)
        elif fmt == "html":
            details = []
            captions = []
            crops = render.detail_frames(shapes, frame)
            if len(crops) > render.MAX_DETAILS:
                env.warn(f"Mapa obsahuje {len(crops)} skupín na priblíženie. Podrobný výrez má prvých {render.MAX_DETAILS}.")
            for group, crop in crops[:render.MAX_DETAILS]:
                image, info = await background(crop)
                details.append((crop, render.jpeg(image)))
                summary = _summary([found[i] for i in group], crop)
                if info:
                    summary["ortofoto"] = info.metadata()
                    captions.append((", ".join(summary["parcely"]), info.dates))
                crop_info.append(summary)
            outputs[fmt] = render.html(found, frame, render.jpeg(bg), title, podklad, details, overview, captions)
        elif fmt == "qgis":
            outputs[fmt] = qgis.bundle(found, frame, title, podklad, popisky, qgis_vrstvy or [])
        elif fmt == "geojson":
            outputs[fmt] = render.geojson(found)
        elif fmt == "kml":
            outputs[fmt] = render.kml(found, shapes)
    summary = _summary(found, frame)
    summary["vyrezy"] = crop_info
    summary["podklad_dotazy"] = {"wms": stats.get("wms_dotazy", 0), "osm_dlazdice": stats.get("osm_dlazdice", 0)}
    if overview:
        summary["ortofoto"] = overview.metadata()
        summary["podklad_dotazy"].update({k: stats[k] for k in ("archivne_vyrezy", "datum_dotazy")})
    return found, outputs, summary


def _filename(base: str, fmt: str) -> str:
    return f"{base}.zip" if fmt == "qgis" else f"{base}.{fmt}"


def _base_name(found: list[dict], nazov: str | None = None) -> str:
    base = nazov or (found[0]["ku_kod"] + "_" + "_".join(f"{p['register']}{p['cislo']}" for p in found[:5]))
    return f"{_slug(base)}_{time.strftime('%Y%m%d-%H%M%S')}"


def _summary(found: list[dict], frame) -> dict:
    return {
        "parcely": [f"{p['register']} {p['cislo']}" for p in found],
        "rozmer_px": [frame.width, frame.height],
        "mierka_m_na_px": round(frame.metres_per_px, 3),
    }


def register(mcp, app) -> None:
    @mcp.tool()
    async def kataster_mapa(
        parcely: Parcels,
        format: Formats = ["png"],
        podklad: Podklad = "orto",
        popisky: Popisky = True,
        out_dir: Annotated[str | None, Field(description="Directory for the files; default <data dir>/mapy.")] = None,
        nazov: Annotated[str | None, Field(description="Base file name; default derived from the parcels.")] = None,
        cyklus: Cyklus = None,
        qgis_vrstvy: Themes = None,
    ) -> dict:
        """Draw parcels on a map and save files. Returns the file paths.

        PNG is rendered on the server (background from official WMS, outlines, labels, scale bar,
        attribution). HTML is an interactive Leaflet map with an embedded overview and sharper crops for separated parcel groups.
        QGIS is a portable ZIP with a project, parcel GeoJSON and layer sources.
        GeoJSON/KML contain only geometry and public attributes (no owners).
        """
        env = Envelope()
        try:
            found, outputs, metadata = await build(app, env, parcely, format, podklad, popisky, cyklus, qgis_vrstvy)
            directory = Path(out_dir).expanduser() if out_dir else app.data_dir / "mapy"
            directory.mkdir(parents=True, exist_ok=True)
            base = _base_name(found, nazov)
            files = {}
            for fmt, content in outputs.items():
                path = directory / _filename(base, fmt)
                if isinstance(content, bytes):
                    path.write_bytes(content)
                else:
                    path.write_text(content, encoding="utf-8")
                restrict(path, 0o644)
                files[fmt] = str(path)
            return env.ok({"subory": files, **metadata})
        except KatasterError as e:
            raise env.fail(e) from e


def register_remote(server, app) -> None:
    @server.tool()
    async def kataster_mapa(
        parcely: Parcels,
        format: Formats = ["png"],
        podklad: Podklad = "orto",
        popisky: Popisky = True,
        cyklus: Cyklus = None,
        qgis_vrstvy: Themes = None,
    ) -> types.CallToolResult:
        """Draw parcels on a map and return it in the result; nothing is stored on the server.

        PNG comes back as an image, HTML (interactive Leaflet map), GeoJSON and KML as embedded
        resources the client can save. Same rendering as the local tool; geometry and public
        attributes only. QGIS comes as an embedded ZIP. HTML includes sharp crops for separated groups. The combined file limit is 8 MiB.
        """
        env = Envelope()
        try:
            found, outputs, metadata = await build(app, env, parcely, format, podklad, popisky, cyklus, qgis_vrstvy)
            encoded = {fmt: c if isinstance(c, bytes) else c.encode("utf-8") for fmt, c in outputs.items()}
            if sum(map(len, encoded.values())) > MAX_INLINE:
                raise KatasterError(
                    "invalid_input",
                    "Mapa je príliš veľká na prenos. Zvoľ menej formátov, menej parciel alebo podklad osm.",
                )
            base = _base_name(found)
            listing, blocks = [], []
            for fmt, raw in encoded.items():
                uri = f"kataster://mapa/{_filename(base, fmt)}"
                listing.append({"format": fmt, "uri": uri, "mime": MIME[fmt], "bajty": len(raw)})
                if fmt == "png":
                    blocks.append(types.ImageContent(type="image", data=base64.b64encode(raw).decode(), mime_type=MIME[fmt]))
                elif fmt == "qgis":
                    blocks.append(types.EmbeddedResource(type="resource", resource=types.BlobResourceContents(
                        uri=uri, mime_type=MIME[fmt], blob=base64.b64encode(raw).decode("ascii"))))
                else:
                    blocks.append(types.EmbeddedResource(type="resource", resource=types.TextResourceContents(
                        uri=uri, mime_type=MIME[fmt], text=outputs[fmt])))
            summary = env.ok({"subory": listing, **metadata})
            return types.CallToolResult(content=[
                types.TextContent(type="text", text=json.dumps(summary, ensure_ascii=False)), *blocks])
        except KatasterError as e:
            raise env.fail(e) from e
