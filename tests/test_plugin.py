"""The same private remote plugin can be loaded by both clients."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_plugin_identity_and_oauth_transport():
    portable = json.loads((ROOT / "plugin.json").read_text())
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    for manifest in (portable, codex, claude):
        assert manifest["name"] == "kataster-skallars"
        assert manifest["version"] == portable["version"]
    assert len(portable["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
    assert codex["mcpServers"] == "./.mcp.json"
    assert codex["skills"] == "./skills/"
    legacy = json.loads((ROOT / ".mcp.json").read_text())
    assert legacy == {"mcpServers": {"kataster-skallars-remote": {
        "type": "http", "url": "https://mcp-kataster.aittorney.online/mcp"
    }}}
    transport = json.loads((ROOT / "mcp.json").read_text())
    server = transport["mcpServers"]["kataster-skallars-remote"]
    assert server == {
        "type": "streamable-http",
        "url": "https://mcp-kataster.aittorney.online/mcp",
        "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
    }


def test_address_workflow_keeps_person_search_and_captcha_limits():
    skill = (ROOT / "skills/kataster-skallars/SKILL.md").read_text()
    for phrase in ("Pri adrese", "kataster_ku", "kataster_parcela", "kataster_vlastnici",
                   "CAPTCHA rieši používateľ", "iba s importovanými LV"):
        assert phrase in skill
    assert "Lesnícka" not in skill
