"""The same private remote plugin can be loaded by both clients."""

import json
import tomllib
import hashlib
import importlib.util
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REF = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


@pytest.fixture
def packages(tmp_path):
    subprocess.run([
        shutil.which("uv"), "run", "--frozen", "python", "scripts/package_plugin.py",
        "--source-ref", SOURCE_REF, "--output-dir", str(tmp_path / "packages"),
    ], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
    return {path.stem: path for path in (tmp_path / "packages").glob("*.zip")}


def test_packages_are_reproducible_and_selfcontained(packages, tmp_path):
    subprocess.run([
        shutil.which("uv"), "run", "--frozen", "python", "scripts/package_plugin.py",
        "--source-ref", SOURCE_REF, "--output-dir", str(tmp_path / "again"),
    ], cwd=ROOT, check=True, capture_output=True)
    assert len(packages) == 2
    for name, path in packages.items():
        assert path.read_bytes() == (tmp_path / "again" / path.name).read_bytes()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            inventory = json.loads(archive.read("SOURCE.json"))
            assert inventory["source_commit"] == SOURCE_REF
            assert set(inventory["sha256"]) == set(names) - {"SOURCE.json"}
            for filename, digest in inventory["sha256"].items():
                assert hashlib.sha256(archive.read(filename)).hexdigest() == digest
            assert sum(n.endswith("SKILL.md") for n in names) == 1
            assert not any(".env" in n or "fixture" in n or ".git/" in n for n in names)
            assert ".codex-plugin/plugin.json" in names
            assert ".claude-plugin/plugin.json" in names
            portable = json.loads(archive.read("plugin.json"))
            transport = json.loads(archive.read("mcp.json"))["mcpServers"]
            legacy = json.loads(archive.read(".mcp.json"))["mcpServers"]
            assert len(transport) == len(legacy) == 1
            if name.startswith("kataster-skallars-local"):
                assert portable["name"] == "kataster-skallars-local"
                assert "runtime/uv.lock" in names
                assert "runtime/src/kataster_mcp/data/ku.json" in names
                server = transport["kataster-skallars-local"]
                assert server["args"] == ["run", "--frozen", "--no-dev", "--directory", "${PLUGIN_ROOT}/runtime", "kataster-mcp"]
                assert legacy["kataster-skallars-local"]["args"][4] == "${CLAUDE_PLUGIN_ROOT}/runtime"
            else:
                assert portable["name"] == "kataster-skallars"
                assert not any(n.startswith("runtime/") for n in names)
                assert transport["kataster-skallars-remote"]["url"] == "https://mcp-kataster.aittorney.online/mcp"
                assert "headers" not in transport["kataster-skallars-remote"]


def test_packager_rejects_symlinks_and_unapproved_sources():
    spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "scripts/package_plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path in ("src/kataster_mcp/data/private.json", "src/kataster_mcp/.env", "tests/fixture.html"):
        assert not module.runtime_path_allowed(path)
    assert module.runtime_path_allowed("src/kataster_mcp/data/ku.json")
    with pytest.raises(ValueError, match="symbolic"):
        module.check_source_mode("120000", "src/kataster_mcp/cache.py")


@pytest.mark.anyio
async def test_extracted_local_package_stdio_from_fresh_cwd(packages, tmp_path):
    artifact = tmp_path / "extracted"
    with zipfile.ZipFile(packages["kataster-skallars-local-0.2.0"]) as archive:
        archive.extractall(artifact)
    outside = tmp_path / "outside"
    outside.mkdir()
    manifest = json.loads((artifact / "mcp.json").read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["kataster-skallars-local"]
    params = StdioServerParameters(
        command=shutil.which(server["command"]),
        args=[arg.replace("${PLUGIN_ROOT}", str(artifact)) for arg in server["args"]],
        cwd=str(outside),
        env={**os.environ, "UV_OFFLINE": "1", "SK_KATASTER_DATA_DIR": str(tmp_path / "state"), "PYTHONUTF8": "1"},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
        initialized = await client.initialize()
        assert initialized.server_info.version == tomllib.loads(
            (artifact / "runtime" / "pyproject.toml").read_text()
        )["project"]["version"]
        assert "kataster_status" in {tool.name for tool in (await client.list_tools()).tools}
        result = await client.call_tool("kataster_status", {})
        assert not result.is_error
    cli = subprocess.run([
        params.command, *params.args[:-1], "sk-kataster", "doctor",
    ], cwd=outside, env=params.env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert cli.returncode == 0, cli.stderr


def test_plugin_identity_and_oauth_transport():
    portable = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    for manifest in (portable, codex, claude):
        assert manifest["name"] == "kataster-skallars"
        assert manifest["version"] == portable["version"]
    assert len(portable["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
    assert codex["mcpServers"] == "./.mcp.json"
    assert codex["skills"] == "./skills/"
    legacy = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert legacy == {"mcpServers": {"kataster-skallars-remote": {
        "type": "http", "url": "https://mcp-kataster.aittorney.online/mcp"
    }}}
    transport = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
    server = transport["mcpServers"]["kataster-skallars-remote"]
    assert server == {
        "type": "streamable-http",
        "url": "https://mcp-kataster.aittorney.online/mcp",
        "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
    }


def test_address_workflow_keeps_person_search_and_captcha_limits():
    skill = (ROOT / "skills/kataster-skallars/SKILL.md").read_text(encoding="utf-8")
    for phrase in ("Pri adrese", "kataster_ku", "kataster_parcela", "kataster_vlastnici",
                   "CAPTCHA rieši používateľ", "iba s importovanými LV"):
        assert phrase in skill
    assert "Lesnícka" not in skill
