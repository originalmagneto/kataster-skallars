"""CLI contracts exercised as a process, outside the checkout."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "lv_vypis_anon.html"


pytestmark = pytest.mark.usefixtures("isolated_subprocess_limits")


def run_cli(tmp_path, *args):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "kataster_mcp.cli",
            "--json",
            "--data-dir",
            str(tmp_path / "data"),
            *args,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    return result, json.loads(result.stdout)


def test_doctor_runs_without_network_or_creating_cache(tmp_path):
    result, out = run_cli(tmp_path, "doctor")
    assert result.returncode == 0
    assert out["data"]["mode"] == "local"
    assert out["data"]["auth"] == "not_required"
    assert not (tmp_path / "data").exists()


def test_inspect_defaults_to_compact_without_personal_fields(tmp_path):
    result, out = run_cli(tmp_path, "lv", "inspect", str(FIXTURE.resolve()))
    assert result.returncode == 0
    assert out["data"]["lv"] == "1926"
    assert out["data"]["parcely"] == 26
    assert "FIKTÍVNY" not in result.stdout
    assert out["data"]["tarchy"] == "none"
    assert out["varovania"]
    assert not (tmp_path / "data").exists()


def test_import_dry_run_and_actual_import(tmp_path):
    result, out = run_cli(tmp_path, "lv", "import", str(FIXTURE.resolve()), "--dry-run")
    assert result.returncode == 0 and out["data"]["dry_run"]
    assert not (tmp_path / "data").exists()
    result, out = run_cli(tmp_path, "lv", "import", str(FIXTURE.resolve()))
    assert result.returncode == 0 and out["data"]["ulozenie"]["stav"] == "stored"
    assert (tmp_path / "data" / "osoby.sqlite").exists()
    result, out = run_cli(tmp_path, "person", "overview", "--name", "Fiktívny Vlastník")
    assert result.returncode == 0
    assert out["data"]["osoby"][0]["pocet_parciel"] == 26


def test_missing_file_and_invalid_flags_are_json_errors(tmp_path):
    for args in [("lv", "inspect", "missing.html"), ("nonsense",)]:
        result, out = run_cli(tmp_path, *args)
        assert result.returncode != 0
        assert out["chyba"]["typ"] in ("invalid_input", "not_found")


def test_ku_resolve_and_local_url(tmp_path):
    result, out = run_cli(tmp_path, "ku", "resolve", "Vyšný Kubín")
    assert result.returncode == 0 and out["data"]["kod"] == "871541"
    result, out = run_cli(tmp_path, "lv", "url", "--ku", "871541", "--lv", "1926")
    assert result.returncode == 0 and "prfNumber=1926" in out["data"]["url"]
    assert not (tmp_path / "data").exists()


def test_discovery_only_emits_names_until_tool_is_requested(tmp_path):
    result, out = run_cli(tmp_path, "tools")
    assert result.returncode == 0 and "kataster_lv_import" in out["data"]["tools"]
    assert "inputSchema" not in result.stdout
    result, out = run_cli(tmp_path, "tools", "kataster_lv_import")
    assert result.returncode == 0 and out["data"]["name"] == "kataster_lv_import"
    description = out["data"]["description"]
    assert "`jednotky`" in description and "`jednotka`" in description


def test_standalone_data_dir_is_separate_and_configurable(monkeypatch, tmp_path):
    from kataster_mcp import cache

    monkeypatch.delenv("SK_KATASTER_DATA_DIR", raising=False)
    assert cache.standalone_data_dir().name == "kataster-skallars"
    monkeypatch.setenv("SK_KATASTER_DATA_DIR", str(tmp_path / "isolated"))
    assert cache.standalone_data_dir() == tmp_path / "isolated"


def test_cli_json_is_utf8_even_with_legacy_console_encoding(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "kataster_mcp.cli", "--json", "ku", "resolve", "871541"],
        cwd=tmp_path,
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"},
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert json.loads(result.stdout.decode("utf-8"))["data"]["nazov"] == "Vyšný Kubín"


def test_doctor_reads_shared_quota_without_writing(tmp_path):
    import sqlite3
    from kataster_mcp.cache import today

    _, fresh = run_cli(tmp_path, "doctor")
    limits = Path(fresh["data"]["limits_dir"])
    assert limits.is_relative_to(tmp_path) and not limits.exists()
    quota = fresh["data"]["kvota_vlastnici"]
    assert quota == {"den": today(), "pouzite": 0, "limit": 50, "zostava": 50}
    limits.mkdir(parents=True)
    state = limits / "stav.sqlite"
    with sqlite3.connect(state) as conn:
        conn.execute("CREATE TABLE kvota (den TEXT, parcela TEXT)")
        conn.executemany("INSERT INTO kvota VALUES (?, ?)", [(today(), "one"), ("2000-01-01", "two")])
    before = state.read_bytes(), state.stat().st_mtime_ns
    result, out = run_cli(tmp_path, "doctor")
    assert result.returncode == 0 and out["data"]["kvota_vlastnici"]["pouzite"] == 1
    assert (state.read_bytes(), state.stat().st_mtime_ns) == before and not (tmp_path / "data").exists()


def test_separate_person_names_match_existing_full_name(tmp_path):
    run_cli(tmp_path, "lv", "import", str(FIXTURE.resolve()))
    result, split = run_cli(tmp_path, "person", "overview", "--surname", "Vlastník", "--first-name", "Fiktívny")
    _, full = run_cli(tmp_path, "person", "overview", "--name", "Fiktívny Vlastník")
    assert result.returncode == 0 and split["data"]["osoby"] == full["data"]["osoby"]
    assert split["data"]["osoby"][0]["pocet_parciel"] == 26


def test_call_error_keeps_server_envelope(tmp_path):
    result, out = run_cli(tmp_path, "call", "kataster_lv", '{"ku":"000000","lv":"1"}')
    assert result.returncode == 1
    assert out["chyba"]["typ"] == "not_found"
    assert "000000" in out["chyba"]["sprava"] and out["chyba"]["coverage"]
    assert out["zdroje"] == [] and out["varovania"] == []


def test_plain_tool_error_keeps_message_and_envelope(tmp_path):
    result, out = run_cli(tmp_path, "call", "kataster_missing_tool", "{}")
    assert result.returncode == 1
    assert "kataster_missing_tool" in out["chyba"]["sprava"]
    assert out["zdroje"] == [] and out["varovania"] == []
