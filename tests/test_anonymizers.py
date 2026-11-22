"""Exercise the fixture generators with synthetic inputs only."""
from pathlib import Path
import json
import subprocess
import sys

import pytest

from kataster_mcp import lv
from kataster_mcp.sources import eskn_building

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def run_script(kind, src, dst, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / f"anonymize_{kind}.py"),
                           str(src), str(dst), *map(str, args)], cwd=dst.parent,
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


def synthetic_html(fixture):
    page = (FIX / fixture).read_text(encoding="utf-8")
    replacements = {"FIKTÍVNY": "CanaryPrimary", "VYMYSLENÁ": "CanarySecondary",
                    "Fiktívny": "CanaryPrimary", "Vymyslená": "CanarySecondary",
                    "01.01.1900": "01.01.1888", "02.02.1900": "02.02.1888",
                    "Testovacia 1/1": "CanaryRoad 5", "Pokusná 2": "CanaryRoad 6",
                    "Skúšobná": "CanaryAlias", "Nikde": "CanaryTown", "000 00": "000 91",
                    "TEST-1/2000": "CANARY-485/2099", "FIKTÍVNA banka": "CanaryBank"}
    for old, new in replacements.items():
        page = page.replace(old, new)
    return page.replace("</main>", '<input name="javax.faces.ViewState" value="CanarySession"></main>')


@pytest.mark.parametrize(("kind","fixture"), [
    ("lv_extract", "lv_vypis_byty_anon.html"), ("lv_nahlad", "lv_nahlad_byty_anon.html"),
])
def test_reduced_html_keeps_first_and_last_units(tmp_path, kind, fixture):
    src, dst = tmp_path / "source.html", tmp_path / "fixture.html"
    src.write_text(synthetic_html(fixture), encoding="utf-8")
    result = run_script(kind, src, dst, 1, 1)
    assert result.returncode == 0, result.stderr
    data = lv.parse_page(dst.read_bytes())
    assert [(u["druh"], u["cislo"]) for u in data["jednotky"]] == [("byt","1"), ("nebytovy_priestor","16")]
    assert "canary" not in dst.read_text(encoding="utf-8").lower()


def test_building_owner_pair_and_session_removed(tmp_path):
    src, dst = tmp_path / "source.html", tmp_path / "fixture.html"
    src.write_text(synthetic_html("eskn_detail_st_anon.html"), encoding="utf-8")
    result = run_script("eskn_detail", src, dst)
    assert result.returncode == 0, result.stderr
    page = dst.read_text(encoding="utf-8")
    assert "Canary" not in page and len(eskn_building.parse_building(page)["vlastnici"]) == 2


def test_pdf_outputs_parseable_runs(tmp_path):
    from kataster_mcp.parsers import lv_pdf

    src, dst = FIX / "lv_vypis_anon_generated.pdf", tmp_path / "runs.json"
    result = run_script("lv_pdf", src, dst)
    assert result.returncode == 0, result.stderr
    parsed = lv_pdf.parse_runs(json.loads(dst.read_text(encoding="utf-8")))
    assert len(parsed["cast_b"]["vlastnici"]) == 2
    assert parsed["cast_a"] == lv_pdf.parse_lv_pdf(src.read_bytes())["cast_a"]


def test_anonymizer_refuses_overwrite_and_unknown_layout(tmp_path):
    src, dst = tmp_path / "source.html", tmp_path / "fixture.html"
    src.write_text("<main>Canary</main>", encoding="utf-8")
    assert run_script("lv_extract", src, src).returncode != 0
    assert src.read_text(encoding="utf-8") == "<main>Canary</main>"
    assert run_script("lv_extract", src, dst).returncode != 0
    assert not dst.exists()


@pytest.mark.parametrize("counts", [(), (2, 1), (5, 5)])
def test_pdf_unit_selection_and_shares(tmp_path, monkeypatch, counts):
    from kataster_mcp.parsers import lv_pdf

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import anonymize_lv_pdf as generator

    source = FIX / "lv_pdf_runs_byty_anon.json"
    original = lv_pdf.parse_runs(json.loads(source.read_bytes()))
    # Exercise the positional layout independently of the PDF text decoder.
    monkeypatch.setattr(lv_pdf, "pdf_runs", lambda _: json.loads(source.read_bytes()))
    monkeypatch.setattr(generator, "independent_pieces", lambda _: set())
    dst = tmp_path / "runs.json"
    generator.main(FIX / "lv_vypis_anon_generated.pdf", dst, *counts)
    parsed = lv_pdf.parse_runs(json.loads(dst.read_bytes()))
    units = original["jednotky"]
    expected = [u for i, u in enumerate(units) if not counts or i < counts[0] or i >= len(units) - counts[1]]
    assert parsed["jednotky"] == expected
    assert parsed["cast_a"] == original["cast_a"]
