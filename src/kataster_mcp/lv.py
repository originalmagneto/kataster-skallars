"""kataster_lv: build the URL of an LV extract (výpis z listu vlastníctva). No network.

The extract is behind Google reCAPTCHA; the user opens it in a browser and solves it
(the server never bypasses CAPTCHA), saves the page and imports it with kataster_lv_import.
"""

from pathlib import Path
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import Field

from . import ku as ku_mod
from . import navod
from .cache import PERSONAL_TTL, Cache, parser_version, ts_iso
from .envelope import Envelope, KatasterError
from .normalize import parcel_number
from .parsers import lv as lv_parser
from .parsers import lv_pdf
from .parsers import nahlad as nahlad_parser

GENERATE_URL = "https://kataster.skgeodesy.sk/Portal45/api/Bo/GeneratePrfPublic"
LV_VER = parser_version(*lv_parser.PARSERS, *nahlad_parser.PARSERS, *lv_pdf.PARSERS)
MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 300
SUFFIXES = (".html", ".htm", ".xhtml", ".pdf")
IMPORT = "lv_import"


def lv_url(ku_kod: str, lv: str, output: str, parcels: list[tuple[str, str]]) -> str:
    params = {"prfNumber": lv, "cadastralUnitCode": ku_kod, "outputType": output}
    if parcels:
        by_reg: dict[str, list[str]] = {}
        for reg, num in parcels:
            by_reg.setdefault(reg, []).append(num)
        params["filter"] = "".join(f"parcels{reg}:{','.join(nums)};" for reg, nums in sorted(by_reg.items()))
    return f"{GENERATE_URL}?{urlencode(params, safe=':;,/')}"


def ku_code(header: str) -> str:
    """k.ú. code from the header: the extract has '871541 Vyšný Kubín', the preview only the name."""
    if header[:6].isdigit():
        return header[:6]
    hits = [u["kod"] for u in ku_mod.table()["_by_code"].values() if u["nazov"] == header.strip()]
    return hits[0] if len(hits) == 1 else header.strip() or "?"


def parse_page(raw: bytes) -> dict:
    """One saved page or PDF -> parsed LV (extract or preview), or KatasterError."""
    is_pdf = raw.startswith(b"%PDF")
    page = "" if is_pdf else raw.decode("utf-8", errors="replace")
    is_preview = "Náhľad listu vlastníctva" in page
    try:
        if is_pdf:
            return lv_pdf.parse_lv_pdf(raw)
        return nahlad_parser.parse_nahlad(page) if is_preview else lv_parser.parse_lv(page)
    except ValueError as e:
        if is_pdf:
            raise KatasterError("parser_drift", f"Not a readable LV extract PDF: {e}.") from e
        known = is_preview or "LISTU VLASTN" in page
        raise KatasterError(
            "parser_drift" if known else "invalid_input",
            f"Not a readable LV page: {e}. Save the extract (GeneratePrfPublic) as 'HTML only', "
            "or the 'Náhľad listu vlastníctva' page as 'Web page, complete'.",
        ) from e


def _files(path: str) -> list[Path]:
    fp = Path(path).expanduser()
    if fp.is_dir():  # 'web page, complete' adds a *_files folder next to each page: not descended into
        return sorted(f for f in fp.iterdir() if f.is_file() and f.suffix.lower() in SUFFIXES)
    if not fp.is_file():
        raise KatasterError("not_found", f"File or folder not found: {fp}")
    return [fp]


def _rank(data: dict) -> tuple:
    """Which of two copies of one LV wins: newer data date, then the extract over the preview."""
    raw = data["hlavicka"].get("Údaje platné k", "")
    date = ()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt)
            date = (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second)
            break
        except ValueError:
            continue
    return date, data.get("zdroj_typ") != "nahlad_lv"


def replacement_decision(candidate: dict, previous: dict) -> tuple[bool, dict[str, int]]:
    """Compare the same identities as the cache selection policy, counting only missing entries."""
    def owner_key(owner: dict) -> tuple:
        unit = owner.get("jednotka") or {}
        return tuple(" ".join((owner.get(k) or "").casefold().split())
                     for k in ("meno", "datum_narodenia", "ico")) + tuple(
            unit.get(k) for k in ("druh", "vchod", "cislo", "supisne_cislo"))

    old, new = previous.get("uplnost", {}), candidate.get("uplnost", {})
    before = {owner_key(o) for o in previous["cast_b"]["vlastnici"]}
    after = {owner_key(o) for o in candidate["cast_b"]["vlastnici"]}
    counts = {
        "vlastnici": len(before - after),
        "casti": sum(old.get(p) == "read" and new.get(p) != "read" for p in ("cast_a", "cast_b", "cast_c")),
    }
    for key, fields in (("cast_a", ("register", "cislo")), ("stavby", ("supisne_cislo", "parcela")),
                        ("jednotky", ("druh", "vchod", "cislo", "supisne_cislo"))):
        before = {tuple(row.get(k) for k in fields) for row in previous.get(key, [])}
        after = {tuple(row.get(k) for k in fields) for row in candidate.get(key, [])}
        counts["parcely" if key == "cast_a" else key] = len(before - after)
    missing = {key: count for key, count in counts.items() if count}
    narrower = new.get("rozsah") == "partial" and old.get("rozsah") != "partial"
    return not missing and not narrower and _rank(candidate) >= _rank(previous), missing


def can_replace(candidate: dict, previous: dict) -> bool:
    return replacement_decision(candidate, previous)[0]


def store_import(cache: Cache, data: dict, names: list[str]) -> tuple[float, dict]:
    """Select and compare under one write lock. A rejected import keeps its predecessor's timestamp."""
    key = f"{ku_code(data['hlavicka'].get('Katastrálne územie', ''))}|{data['lv']}"
    with cache.db:
        cache.db.execute("BEGIN IMMEDIATE")
        previous = cache.get(IMPORT, LV_VER, key, PERSONAL_TTL)
        if previous:
            replace, missing = replacement_decision(data, previous[0]["lv"])
            if not replace:
                report = {"stav": "preserved_existing"}
                if missing:
                    report["ubudlo"] = missing
                return previous[1], report
        ts = cache.put(IMPORT, LV_VER, key, {"zdroj": names[0], "subory": names, "lv": data})
    return ts, {"stav": "stored"}


def document_warnings(data: dict) -> list[str]:
    """Describe this input even if a different copy remains in the cache."""
    notes = []
    coverage = data["uplnost"]
    missing = [part[-1].upper() for part in ("cast_a", "cast_b", "cast_c") if coverage.get(part) == "missing"]
    if missing:
        notes.append(f"V dokumente chýbajú časti {', '.join(missing)}.")
    if data["tarchy"] == "unknown":
        notes.append("Chýbajúca alebo neprečítaná časť C nepotvrdzuje neprítomnosť tiarch.")
    if coverage.get("rozsah") == "partial":
        notes.append("Čiastočný výpis zachytáva iba vybrané položky.")
    if data.get("jednotky_poznamka"):
        notes.append(data["jednotky_poznamka"])
    if data.get("stavby_neprecitane"):
        notes.append("Výpis uvádza stavby, ktoré sa nepodarilo prečítať. Overte ich v náhľade toho istého LV.")
    report = data.get("ulozenie", {})
    if report.get("stav") == "preserved_existing":
        notes.append("Import nenahradil uložený výpis vzhľadom na dátum, druh alebo rozsah vstupu. "
                     "Prehľad osôb naďalej používa pôvodný záznam.")
        if report.get("ubudlo"):
            labels = {"vlastnici": "vlastníci", "parcely": "parcely", "stavby": "stavby",
                      "jednotky": "jednotky", "casti": "prečítané časti"}
            counts = ", ".join(f"{labels[k]} ({n})" for k, n in report["ubudlo"].items())
            notes.append(f"Oproti uloženému výpisu ubudli položky v kategóriách {counts}.")
    notes.append("Rozsah dokumentu nie je overený ako úplný.")
    return [f"LV {data['lv']}: {note}" for note in notes]


def _summary(ku: str, data: dict, files: list[str], ts: float) -> dict:
    b = data.get("cast_b") or {}
    return {
        "ku_kod": ku, "lv": data["lv"], "zdroj_typ": data.get("zdroj_typ"), "subory": files,
        "udaje_platne_k": data["hlavicka"].get("Údaje platné k"), "parcely": len(data.get("cast_a") or []),
        "stavby": len(data.get("stavby") or []),
        **({"jednotky": data["jednotky_pocet"]} if "jednotky_pocet" in data else {}),
        "vlastnici": len(b.get("vlastnici") or []), "tarchy": data["tarchy"], "importovane": ts_iso(ts),
    }


def register(mcp, app) -> None:

    @mcp.tool()
    async def kataster_lv(
        ku: Annotated[str, Field(description="Cadastral unit (k.ú.): name or 6-digit code.")],
        lv: Annotated[str, Field(description="LV number (číslo listu vlastníctva), e.g. from kataster_vlastnici.")],
        parcely: Annotated[list[str] | None, Field(description="Optional parcels for a partial extract (čiastočný výpis), e.g. ['E 503']. Register prefix required.")] = None,
        format: Annotated[Literal["html", "pdf"], Field(description="html can be imported with kataster_lv_import; pdf is for printing.")] = "html",
    ) -> dict:
        """URL of the LV extract (výpis z LV) on the ESKN portal and a guide (navod) for the user.

        Makes no network request. The portal shows a reCAPTCHA ('Nie som robot') that only the user
        may solve; this tool never bypasses it. The extract is the only public source of
        encumbrances (ťarchy, časť C), administrators and tenants. The guide explains LV preview vs.
        extract vs. official extract (eID, paid); walk the user through it one step at a time.
        """
        env = Envelope()
        try:
            unit = ku_mod.resolve(ku)
            if not lv.strip().isdigit():
                raise KatasterError("invalid_input", f"LV must be a number, not '{lv}'.")
            parsed = []
            for p in parcely or []:
                reg, num = parcel_number(p)
                if reg == "auto":
                    raise KatasterError("invalid_input", f"Give the register for '{p}', e.g. 'E {p}' or 'C {p}'.")
                parsed.append((reg, num))
            url = lv_url(unit["kod"], lv.strip(), format, parsed)
            env.source("eskn_vypis_lv", GENERATE_URL, oficialny=False, z_cache=False)
            if parsed:
                env.warn("Partial-extract filter syntax is verified only for one E parcel (parcelsE:503;); "
                         "for other combinations check that the extract lists the expected parcels.")
            return env.ok({
                "url": url,
                "ku": unit,
                "lv": lv.strip(),
                "ciastocny": bool(parsed),
                "navod": navod.lv(url),
            })
        except KatasterError as e:
            raise env.fail(e) from e

    @mcp.tool()
    async def kataster_lv_import(
        path: Annotated[str | None, Field(description="Saved LV page or PDF, or a FOLDER with several of them.")] = None,
        paths: Annotated[list[str] | None, Field(description="Several files or folders at once.")] = None,
        html: Annotated[str | None, Field(description="The HTML itself, instead of a path.")] = None,
    ) -> dict:
        """Read LV extracts (výpis z LV, HTML or PDF) and LV previews (Náhľad LV, HTML) saved from the browser.

        One file: returns the parsed LV: header (district, municipality, k.ú., date of data), part A (parcels with
        area, land type, location; codes translated by the legend; buildings in `stavby` with súpisné číslo,
        the parcel under the building, kind and the LV of the land), part B (owners with shares, acquisition titles,
        notes; administrators and tenants) and part C (encumbrances, ťarchy). zdroj_typ tells the input:
        vypis_lv_html, vypis_lv_pdf or nahlad_lv (the preview has no administrators/tenants section).
        A folder or several paths: a summary per LV (the same LV twice is merged: newer data, extract before
        preview), unreadable files are listed in varovania. Makes no network request. Results are kept in the
        local personal-data cache for 7 days (owner-only permissions on POSIX); kataster_osoba_prehlad reads them.
        """
        return import_lv(app.osoby, path=path, paths=paths, html=html)


def import_lv(cache: Cache, *, path: str | None = None, paths: list[str] | None = None,
              html: str | None = None) -> dict:
    """Shared local import service for MCP and CLI; does not start a server."""
    env = Envelope()
    try:
        if sum(bool(x) for x in (path, paths, html)) != 1:
            raise KatasterError("invalid_input", "Give exactly one of path, paths or html.")
        if html:
            if len(html.encode("utf-8")) > MAX_BYTES:
                raise KatasterError("invalid_input", "HTML prekračuje limit importu.")
            items = [("inline html", html.encode("utf-8"))]
        else:
            files = [f for p in ([path] if path else paths) for f in _files(p)]
            if not files:
                raise KatasterError("not_found", "No .html, .htm or .pdf files there.")
            if len(files) > MAX_FILES:
                raise KatasterError("invalid_input", f"{len(files)} files; import at most {MAX_FILES} at once.")
            items = []
            for f in files:
                if f.stat().st_size > MAX_BYTES:
                    if len(files) == 1:
                        raise KatasterError("invalid_input", f"File too large ({f.stat().st_size} B).")
                    env.warn(f"{f.name}: skipped, too large ({f.stat().st_size} B).")
                    continue
                items.append((str(f), f.read_bytes()))
        single = len(items) == 1 and not (path and Path(path).expanduser().is_dir()) and not paths
        best: dict[tuple[str, str], tuple[dict, list[str]]] = {}
        for origin, raw in items:
            try:
                data = parse_page(raw)
            except KatasterError as e:
                if single:
                    raise
                env.warn(f"{Path(origin).name}: not read ({e.kind}: {e.message})")
                continue
            key = (ku_code(data["hlavicka"].get("Katastrálne územie", "")), data["lv"])
            if key in best:
                old, names = best[key]
                if can_replace(data, old):
                    best[key] = (data, [origin, *names])
                else:
                    names.append(origin)
            else:
                best[key] = (data, [origin])
        out = []
        for (ku, lv_no), (data, names) in best.items():
            ts, report = store_import(cache, data, names)
            data["ulozenie"] = report
            notes = document_warnings(data)
            valid_date = data["hlavicka"].get("Údaje platné k", "?")
            notes.append(f"LV {lv_no}: informatívny výpis nepoužiteľný na právne úkony. Údaje platné k {valid_date}.")
            for note in notes:
                env.warn(note)
            saved = report["stav"] == "stored"
            env.source(IMPORT, names[0], oficialny=False, z_cache=False, cas=ts_iso(ts) if saved else None)
            summary = _summary(ku, data, names, ts)
            if not saved:
                summary["importovane"] = None
            out.append({**summary, "ulozenie": report, "uplnost": data["uplnost"], "varovania": notes})
        if single:
            return env.ok(next(iter(best.values()))[0])
        if not out:
            raise KatasterError("invalid_input", "None of the files is a readable LV page or PDF.",
                                details=env.varovania)
        return env.ok({"lv": sorted(out, key=lambda x: (x["ku_kod"], int(x["lv"]) if x["lv"].isdigit() else 0)),
                       "pocet_lv": len(out), "pocet_suborov": len(items)})
    except KatasterError as e:
        raise env.fail(e) from e
