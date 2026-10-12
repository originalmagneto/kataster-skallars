import base64
import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kataster_mcp.backup import restore, retain, seal, snapshot


@pytest.fixture
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    return private, private.public_key()


def test_wal_snapshot_restore_and_existing_destination(tmp_path, keys):
    source = tmp_path / "source"
    source.mkdir()
    db = sqlite3.connect(source / "quota.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE quota (used INTEGER)")
    db.execute("INSERT INTO quota VALUES (42)")
    db.commit()
    (source / "uploads").mkdir()
    (source / "uploads" / "synthetic").write_bytes(b"synthetic")
    out = tmp_path / "backups"
    result = snapshot(source, keys[1], out, config={"quota": 50})
    destination = tmp_path / "restore"
    restore(Path(result["output"]), keys[0], destination)
    restored = sqlite3.connect(destination / "quota.sqlite")
    assert restored.execute("SELECT used FROM quota").fetchone() == (42,)
    restored.close()
    assert not list(destination.rglob("*-wal"))
    assert (destination / "uploads" / "synthetic").read_bytes() == b"synthetic"
    with pytest.raises(ValueError):
        restore(Path(result["output"]), keys[0], destination)
    db.close()


def test_corruption_wrong_key_and_unsafe_paths(tmp_path, keys):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_bytes(b"test")
    output = Path(snapshot(source, keys[1], tmp_path / "backups")["output"])
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    with pytest.raises(ValueError):
        restore(output, wrong, tmp_path / "wrong")
    envelope = json.loads(output.read_text())
    envelope["tag"] = base64.b64encode(b"0" * 16).decode()
    output.write_text(json.dumps(envelope))
    with pytest.raises(ValueError):
        restore(output, keys[0], tmp_path / "corrupt")
    for name in ["../escape", "/escape", "a/../escape", "a\\escape"]:
        output.write_text(
            json.dumps(
                seal(
                    {
                        "format": "skallars-restore-v1",
                        "service": "kataster",
                        "createdAt": "synthetic",
                        "revision": "unknown",
                        "files": {name: ""},
                        "config": {},
                        "manifest": {},
                    },
                    keys[1],
                )
            )
        )
        with pytest.raises(ValueError):
            restore(output, keys[0], tmp_path / "unsafe")
    assert not (tmp_path / "unsafe").exists()
    output.write_text(
        json.dumps(
            seal(
                {
                    "format": "skallars-restore-v1",
                    "service": "kataster",
                    "createdAt": "synthetic",
                    "revision": "unknown",
                    "files": [],
                    "config": {},
                    "manifest": {},
                },
                keys[1],
            )
        )
    )
    with pytest.raises(ValueError):
        restore(output, keys[0], tmp_path / "malformed")


def test_symlink_and_retention_no_recursion(tmp_path, keys):
    source = tmp_path / "source"
    source.mkdir()
    try:
        (source / "link").symlink_to(tmp_path)
    except OSError:
        pytest.skip("Platforma nepovoľuje vytvorenie testovacieho symlinku.")
    with pytest.raises(ValueError):
        snapshot(source, keys[1], tmp_path / "backups")
    out = tmp_path / "retention"
    out.mkdir()
    nested = out / "kataster-2000-01-01T00-00-00Z.enc.json"
    nested.mkdir()
    (nested / "keep").write_text("keep")
    retain(out, 7)
    assert (nested / "keep").exists()


def test_cli_envelopes_and_private_files(tmp_path, keys, capsys):
    from kataster_mcp.cli import main

    source = tmp_path / "source"
    source.mkdir()
    (source / "quota.json").write_text('{"used":42}')
    public, private = tmp_path / "public.pem", tmp_path / "private.pem"
    public.write_bytes(
        keys[1].public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    private.write_bytes(
        keys[0].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    assert (
        main(
            [
                "--json",
                "--data-dir",
                str(source),
                "backup",
                "snapshot",
                "--public-key",
                str(public),
                "--directory",
                str(tmp_path / "backups"),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    output = Path(result["data"]["output"])
    assert (
        main(
            [
                "--json",
                "backup",
                "restore",
                "--input",
                str(output),
                "--private-key",
                str(private),
                "--destination",
                str(tmp_path / "restore"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["data"]["revision"]
    if __import__("os").name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "restore" / "quota.json").stat().st_mode & 0o777 == 0o600


def test_backup_exclusion_retention_and_bound(tmp_path, keys, monkeypatch):
    import os
    import kataster_mcp.backup as backup

    source = tmp_path / "source"
    source.mkdir()
    backups = source / "backups"
    backups.mkdir()
    old = backups / "kataster-2000-01-01T00-00-00Z.enc.json"
    old.write_text("old")
    os.utime(old, (0, 0))
    outside = backups / "keep.json"
    outside.write_text("keep")
    (source / "state.json").write_text("{}")
    output = Path(snapshot(source, keys[1], backups)["output"])
    assert not old.exists() and outside.exists()
    restore(output, keys[0], tmp_path / "restore")
    assert not (tmp_path / "restore" / "backups").exists()
    monkeypatch.setattr(backup, "MAX_BYTES", 1)
    with pytest.raises(ValueError):
        snapshot(source, keys[1], backups)
    weak = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError):
        seal({}, weak.public_key())


def test_restore_does_not_reset_provider_quota_or_block(tmp_path, keys):
    from kataster_mcp.cache import Cache, Quota
    from kataster_mcp.http import Http
    from kataster_mcp.policy import PUBLIC_POLICY

    source = tmp_path / "source"
    cache = Cache(source / "shared" / "cache.sqlite", private=True)
    quota = Quota(cache.db)
    quota.record("synthetic")
    result = snapshot(source, keys[1], tmp_path / "backups")
    cache.db.close()
    restore(Path(result["output"]), keys[0], tmp_path / "restore")
    restored = Cache(tmp_path / "restore" / "shared" / "cache.sqlite", private=True)
    assert Quota(restored.db).used() >= PUBLIC_POLICY.owners_daily_hard
    http = Http(PUBLIC_POLICY)
    http.blocks = restored
    assert http.blocked_until() > __import__("time").time()
    restored.db.close()


def test_windows_paths_are_rejected_before_publication(tmp_path, keys):
    unsafe = [
        "C:/outside/file",
        "C:outside",
        "//server/share/file",
        "\\outside",
        "file:stream",
        "dir/CON.txt",
        "dir/CON .txt",
        "dir/LPT1",
        "dir/trailing.",
        "dir/trailing ",
        "dir/a?b",
    ]
    for name in unsafe:
        raw = b"synthetic"
        from kataster_mcp.backup import canonical, digest, encoded

        content = {
            "format": "skallars-restore-v1",
            "service": "kataster",
            "createdAt": "synthetic",
            "revision": "unknown",
            "config": {},
            "files": {name: encoded(raw)},
            "manifest": {
                "configSha256": digest(canonical({})),
                "files": {name: digest(raw)},
            },
        }
        backup = tmp_path / "unsafe.enc.json"
        backup.write_text(json.dumps(seal(content, keys[1])))
        with pytest.raises(ValueError):
            restore(backup, keys[0], tmp_path / "restore")
        assert not (tmp_path / "restore").exists()
        assert not list(tmp_path.glob(".kataster-restore-*"))


def test_sqlite_wal_limit_and_persistent_staging(tmp_path, keys, monkeypatch):
    import kataster_mcp.backup as backup

    source = tmp_path / "source"
    source.mkdir()
    db = sqlite3.connect(source / "large.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE payload (value BLOB)")
    db.execute("INSERT INTO payload VALUES (?)", (b"x" * 32768,))
    db.commit()
    assert (source / "large.sqlite").stat().st_size < 8192
    monkeypatch.setattr(backup, "MAX_BYTES", 8192)
    with pytest.raises(ValueError):
        snapshot(source, keys[1], source / "snapshots")
    assert not list((source / "snapshots").glob("*.enc.json"))
    monkeypatch.setattr(backup, "MAX_BYTES", 1024 * 1024)
    original = backup.tempfile.TemporaryDirectory
    locations = []

    def staging(*args, **kwargs):
        locations.append(kwargs.get("dir"))
        return original(*args, **kwargs)

    monkeypatch.setattr(backup.tempfile, "TemporaryDirectory", staging)
    result = snapshot(source, keys[1], source / "snapshots")
    assert locations == [(source / "snapshots").resolve()]
    restore(Path(result["output"]), keys[0], tmp_path / "restored")
    assert not (tmp_path / "restored" / "snapshots").exists()
    db.close()


def test_sqlite_progress_rejects_growth_before_read(tmp_path, keys, monkeypatch):
    from unittest.mock import Mock
    import kataster_mcp.backup as backup

    source = tmp_path / "source"
    source.mkdir()
    (source / "quota.sqlite").write_bytes(b"synthetic")
    db, copied = Mock(), Mock()
    db.execute.return_value.fetchone.side_effect = [(4096,), (1,)]
    progress_calls = []

    def grows(destination, *, pages, progress):
        progress_calls.append(pages)
        progress(0, 0, 3)

    db.backup.side_effect = grows
    monkeypatch.setattr(backup.sqlite3, "connect", Mock(side_effect=[db, copied]))
    monkeypatch.setattr(backup, "MAX_BYTES", 8192)
    with pytest.raises(ValueError, match="SQLite"):
        snapshot(source, keys[1], tmp_path / "snapshots")
    assert progress_calls and not list((tmp_path / "snapshots").iterdir())
    db.close.assert_called_once()
    copied.close.assert_called_once()
