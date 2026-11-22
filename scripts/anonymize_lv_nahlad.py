"""Make a test fixture from a saved ESKN 'Náhľad listu vlastníctva' page: keep header and
parts A-C, replace every owner and acquisition title with fictitious text, drop scripts and
session state.

    uv run python scripts/anonymize_lv_nahlad.py <saved.html> tests/fixtures/<name>.html [first last]

For a block of flats give `first last`: only the first and the last unit tables are kept (the header count
of flats is set to match) and every row of part C is replaced with fictitious text.
Never commit the input file. Refuses to write if any piece of an original owner or title survives.
"""
import re
import sys

from fixture_utils import arguments, unit_indices, inert_html

from kataster_mcp.parsers.nahlad import _TOOLTIP, parse_nahlad  # noqa: E402

FAKE_OWNER = ["FIKTÍVNY Vlastník, 01.01.1900, Testovacia 1/1, Nikde, 000 00",
              "VYMYSLENÁ Osoba r. Skúšobná, 02.02.1900, Pokusná 2, Nikde, 000 00"]
FAKE_TITLE = "Titul nadobudnutia<br>Zmluva č. TEST-1/2000 - 1/00<br>"
FAKE_C = "Záložné právo v prospech FIKTÍVNA banka, a.s., IČO: 00000000 na byt č. 1 - TEST-2/2000"


def keep_units(part_b: str, first: int, last: int) -> str:
    """Only the first `first` and the last `last` unit tables of part B; the header count of flats follows."""
    starts = [part_b.rfind("<table", 0, m.start()) for m in re.finditer("table-byt-data", part_b)]
    blocks = [part_b[a:b] for a, b in zip(starts, [*starts[1:], len(part_b)])]
    kept = [blocks[i] for i in unit_indices(len(blocks), first, last)]
    flats = sum("Číslo bytu" in b for b in kept)
    out = part_b[: starts[0]] + "".join(kept)
    return re.sub(r"(Počet bytov:\s*(?:<[^>]+>\s*)*)\d+", lambda m: m.group(1) + str(flats), out, count=1)


def fake_part_c(part_c: str) -> str:
    def replace_cell(match):
        value = re.sub("<[^>]+>", "", match[2]).strip()
        return match[0] if value in {"", "Bez tiarch."} else match[1] + FAKE_C + match[3]

    return re.sub(r"(<td\b[^>]*>)(.*?)(</td>)", replace_cell, part_c, flags=re.S)


def main(src, dst, first=None, last=None):
    page = open(src, encoding="utf8").read()
    orig = parse_nahlad(page)
    start = page.rfind("<div", 0, page.find("Katastrálne územie"))
    end = page.find("</main>", page.find('class="cast-c"'))
    frag = page[start:end]
    frag = re.sub(r"<script.*?</script>", "", frag, flags=re.S)
    frag = re.sub(r'(name="javax\.faces\.ViewState"[^>]*value=")[^"]*', r"\1REMOVED", frag)
    frag = re.sub(r"(nahlad\?p1=)[^\"&]+", r"\1REMOVED", frag)
    i = 0

    def owner(m):
        nonlocal i
        out = m.group(1) + FAKE_OWNER[i % len(FAKE_OWNER)] + m.group(3)
        i += 1
        return out

    b0, b1 = frag.find('class="cast-b"'), frag.find('class="cast-c"')
    if min(start, end, b0, b1) < 0 or b0 >= b1:
        sys.exit("Unrecognized preview layout.")
    frag = frag[:b1] + fake_part_c(frag[b1:])
    if first is not None:
        frag = frag[:b0] + keep_units(frag[b0:b1], first, last) + frag[b1:]
        b0, b1 = frag.find('class="cast-b"'), frag.find('class="cast-c"')
    part_b = re.sub(r"(<a[^>]*>)([^<]*\d{2}\.\d{2}\.\d{4}[^<]*|[^<]*IČO[^<]*)(</a>)", owner, frag[b0:b1])
    part_b = re.sub(r'(<td[^>]*colspan="3"[^>]*>).*?(</td>)', lambda m: m.group(1) + FAKE_TITLE + m.group(2),
                    part_b, flags=re.S)
    frag = frag[:b0] + part_b + frag[b1:]
    # code legends live in PrimeFaces tooltips placed after </main>
    frag += "".join(f'<div class="ui-tooltip">{m.group(0)}</div>' for m in _TOOLTIP.finditer(page[end:]))
    frag = inert_html(frag)
    pieces = set()
    for o in orig["cast_b"]["vlastnici"]:
        pieces.update(p.strip() for p in o["text"].split(",") if len(p.strip()) > 3)
        pieces.update(t for t in re.split(r"[\s,]+", o.get("titul_nadobudnutia") or "") if len(t) > 4 and any(c.isdigit() for c in t))
    pieces.update(line for line in orig["cast_c"] if len(line) > 4 and line != "Bez tiarch.")
    checked = frag[frag.index('class="cast-b"'):]
    for literal in (*FAKE_OWNER, FAKE_C, FAKE_TITLE):
        checked = checked.replace(literal, "")
    leaks = [p for p in pieces if p in checked]
    if leaks:
        sys.exit(f"refusing: {len(leaks)} original pieces survived")
    with open(dst, "w", encoding="utf8") as f:
        f.write("<html><body><main>" + frag + "</main></body></html>\n")
    print(f"wrote {dst}: {i} owners replaced, checked {len(pieces)} pieces, {len(frag)} chars")


if __name__ == "__main__":
    main(*arguments(units=True))
