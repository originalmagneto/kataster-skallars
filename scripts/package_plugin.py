"""Build reproducible local and remote plugin ZIPs from a pinned Git commit."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_FILES = {
    "plugin.json", "mcp.json", ".mcp.json", ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json", "skills/kataster-skallars/SKILL.md",
}
RUNTIME_FILES = {"pyproject.toml", "uv.lock", "README.md", "LICENSE"}


def runtime_path_allowed(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return path in RUNTIME_FILES or path == "src/kataster_mcp/data/ku.json" or (
        len(parts) >= 3 and parts[:2] == ("src", "kataster_mcp")
        and all(not part.startswith(".") for part in parts)
        and "data" not in parts and path.endswith(".py")
    )


def check_source_mode(mode: str, path: str) -> None:
    if mode not in {"100644", "100755"}:
        raise ValueError(f"Unsupported source mode (symbolic link or non-file): {path}")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def local_files(files: dict[str, bytes]) -> dict[str, bytes]:
    result = dict(files)
    for path in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        manifest = json.loads(result[path])
        manifest["name"] = "kataster-skallars-local"
        manifest["description"] = "Slovenský kataster s pribaleným lokálnym MCP a CLI runtime."
        interface = manifest.get("interface") or manifest.get("extensions", {}).get("com.openai", {}).get("interface")
        if interface:
            interface["displayName"] = "Kataster SKALLARS Local"
            interface["longDescription"] = manifest["description"]
        result[path] = json_bytes(manifest)
    for path, variable in (("mcp.json", "PLUGIN_ROOT"), (".mcp.json", "CLAUDE_PLUGIN_ROOT")):
        transport = json.loads(result[path])
        transport["mcpServers"] = {"kataster-skallars-local": {
            "type": "stdio", "command": "uv",
            "args": ["run", "--frozen", "--no-dev", "--directory", f"${{{variable}}}/runtime", "kataster-mcp"],
        }}
        result[path] = json_bytes(transport)
    return result


def package(source_ref: str, output_dir: Path) -> list[Path]:
    commit = git("rev-parse", "--verify", f"{source_ref}^{{commit}}").decode().strip()
    files: dict[str, bytes] = {}
    runtime: dict[str, bytes] = {}
    for entry in git("ls-tree", "-rz", commit).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        mode, kind, oid = metadata.decode().split()
        if path not in PLUGIN_FILES and not runtime_path_allowed(path):
            continue
        check_source_mode(mode, path)
        content = git("cat-file", "blob", oid)
        if path in PLUGIN_FILES:
            files[path] = content
        else:
            runtime[f"runtime/{path}"] = content
    if set(files) != PLUGIN_FILES or not all(f"runtime/{p}" in runtime for p in RUNTIME_FILES):
        raise ValueError("Pinned source is missing required plugin/runtime files")
    version = json.loads(files["plugin.json"])["version"]
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for profile, name, payload in (
        ("remote", "kataster-skallars", files),
        ("local", "kataster-skallars-local", {**local_files(files), **runtime}),
    ):
        inventory = {"profile": profile, "source_commit": commit, "sha256": {
            path: hashlib.sha256(content).hexdigest() for path, content in sorted(payload.items())
        }}
        archive_path = output_dir / f"{name}-{version}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for path, content in sorted({**payload, "SOURCE.json": json_bytes(inventory)}.items()):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        outputs.append(archive_path)
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/plugins")
    args = parser.parse_args()
    for output in package(args.source_ref, args.output_dir):
        print(output)
