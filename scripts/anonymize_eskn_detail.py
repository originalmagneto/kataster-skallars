"""Make a test fixture from a saved ESKN parcel or building (detail_st) page: keep the parcel or building,
parcel/building lists and owner sections, replace every owner with a fictitious person and every house number with 1, drop session tokens.

    uv run python scripts/anonymize_eskn_detail.py <saved.html> tests/fixtures/<name>.html

Never commit the input file. The script refuses to write if any original owner text survives.
"""
import re
import sys

from fixture_utils import arguments, inert_html

FAKE = [
    "Fiktívny Vlastník, 01.01.1900, Testovacia 1/1, Nikde, 000 00, Slovenská republika",
    "Vymyslená Osoba r. Skúšobná, 02.02.1900, Pokusná 2, Nikde, 000 00, Slovenská republika",
]


def main(src, dst):
    page = open(src, encoding="utf8").read()
    first = "Informácie o stavbe" if "Informácie o stavbe" in page else "Informácie o parcele"  # building or parcel
    start = page.index(first)
    start = page.rfind('<div class="b_white">', 0, start)
    owners = re.compile(r"<h3[^>]*>\s*vlastn", re.I).search(page, start)  # was "VLASTNÍK", now "Vlastník"
    if start < 0 or owners is None:
        sys.exit("Unrecognized detail layout.")
    end = page.index("Informácia", owners.start())
    end = page.find("</main>", end)
    if start < 0 or end < 0:
        sys.exit("Unrecognized detail layout.")
    frag = inert_html(page[start:end])
    originals = [m.group(1) for m in re.finditer(r"ucastnik-link[^>]*>(.*?)</a>", frag, re.S)]
    i = 0

    def repl(m):
        nonlocal i
        out = m.group(1) + FAKE[i % len(FAKE)] + m.group(3)
        i += 1
        return out

    frag = re.sub(r"(ucastnik-link[^>]*>)(.*?)(</a>)", repl, frag, flags=re.S)
    frag = re.sub(r"token=[0-9a-f-]+", "token=REMOVED", frag)
    frag = re.sub(r"(Súpisné číslo:\s*)\S+?(<)", r"\g<1>1\2", frag)  # house number -> fictitious
    checked = frag
    for literal in FAKE:
        checked = checked.replace(literal, "")
    for o in originals:
        name = re.sub(r"\s+", " ", o).strip().split(",")[0]
        if name and name in checked:
            sys.exit("refusing: original owner text survived")
    with open(dst, "w", encoding="utf8") as f:
        f.write("<html><body><main>" + frag + "</main></body></html>\n")
    print(f"wrote {dst}: {i} owners replaced")


if __name__ == "__main__":
    main(*arguments())
