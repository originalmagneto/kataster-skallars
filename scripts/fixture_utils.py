"""Shared input checks and inert HTML for the offline fixture generators."""
import argparse
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path


def arguments(*, units=False):
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    if units:
        parser.add_argument("counts", nargs="*", type=int, metavar="COUNT")
    args = parser.parse_args()
    if args.src.resolve() == args.dst.resolve() or (args.dst.exists() and args.dst.samefile(args.src)):
        parser.error("Use a different file for the output.")
    counts = getattr(args, "counts", [])
    if counts and (len(counts) != 2 or min(counts) < 0 or sum(counts) == 0):
        parser.error("Give two nonnegative counts (first and last), keeping at least one unit.")
    return (args.src, args.dst, *counts)


def unit_indices(size, first, last):
    if not size:
        raise SystemExit("No unit headers to sample.")
    return [i for i in range(size) if i < first or i >= size - last]


class FixtureHTML(HTMLParser):
    """Keep parser-relevant markup. Drop form controls, script bodies, URLs and event attributes."""
    tags = set("html body main article div span strong em i b p h1 h2 h3 h4 a table thead tbody tr td th ul li br sup".split())

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "textarea"}:
            self.skip += 1
        if self.skip or tag not in self.tags:
            return
        attributes = []
        for key, value in attrs:
            if value is None:
                continue
            if (key in {"class", "colspan", "rowspan"} or
                (key == "id" and re.fullmatch(r"j_idt[\w:-]+", value)) or
                (key == "title" and value == "Údaje platné k dátumu")):
                attributes.append(f' {key}="{escape(value, quote=True)}"')
        self.parts.append("<" + tag + "".join(attributes) + ">")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "textarea"}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.tags:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(escape(data, quote=False))


def inert_html(text):
    parser = FixtureHTML()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def check_roles(parsed):
    # Free text about other entitled parties is outside the supported owner layouts.
    for row in parsed["cast_b"].get("ine_opravnene_osoby", []):
        if row["text"].strip().rstrip(".").casefold() not in {"neevidovaní", "neevidované", "bez zápisu"}:
            raise SystemExit("Unsupported nonempty section of other entitled parties.")
