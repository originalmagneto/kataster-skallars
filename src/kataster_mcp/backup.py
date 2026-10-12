"""Bounded encrypted snapshots and isolated restores, including provider state."""

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LABEL = b"skallars-backup:v1:kataster"
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 4096
OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=LABEL
)


def encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def seal(content: dict, public_key: rsa.RSAPublicKey) -> dict:
    if not isinstance(public_key, rsa.RSAPublicKey) or public_key.key_size < 3072:
        raise ValueError("Vyžaduje sa RSA kľúč s aspoň 3072 bitmi.")
    key, iv = os.urandom(32), os.urandom(12)
    sealed = AESGCM(key).encrypt(iv, canonical(content), LABEL)
    return {
        "format": "skallars-backup-v1",
        "service": "kataster",
        "iv": encoded(iv),
        "tag": encoded(sealed[-16:]),
        "key": encoded(public_key.encrypt(key, OAEP)),
        "ciphertext": encoded(sealed[:-16]),
    }


def retain(directory: Path, days: int) -> None:
    if not 1 <= days <= 30:
        raise ValueError("Retencia musí byť 1 až 30 dní.")
    for path in directory.iterdir():
        if (
            re.fullmatch(r"kataster-\d{4}-\d{2}-\d{2}T[\d-]+Z\.enc\.json", path.name)
            and not path.is_symlink()
            and path.is_file()
            and path.stat().st_mtime < time.time() - days * 86400
        ):
            path.unlink()


def snapshot(
    source: Path,
    public_key: rsa.RSAPublicKey,
    directory: Path,
    *,
    config: dict | None = None,
    retain_days: int = 7,
) -> dict:
    if not 1 <= retain_days <= 30 or source.is_symlink() or directory.is_symlink():
        raise ValueError("Neplatný adresár alebo retencia.")
    source, directory = source.resolve(strict=True), directory.resolve()
    if source == directory:
        raise ValueError("Zálohy potrebujú samostatný adresár.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    files: dict[str, str] = {}
    total = 0
    with tempfile.TemporaryDirectory(prefix="kataster-backup-") as temp:
        for root, dirs, names in os.walk(source, followlinks=False):
            parent = Path(root)
            for name in dirs + names:
                if (parent / name).is_symlink():
                    raise ValueError("Symlinky nie sú podporované.")
            dirs[:] = [
                name
                for name in dirs
                if name != "backups" and parent / name != directory
            ]
            for name in names:
                path = parent / name
                if path.relative_to(source).as_posix() in (
                    "config.json",
                    "manifest.json",
                ):
                    raise ValueError("Zdroj obsahuje vyhradený súbor obnovy.")
                if name.endswith(("-wal", "-shm")) or name.endswith(".enc.json"):
                    continue
                if (
                    not path.is_file()
                    or len(files) >= MAX_FILES
                    or path.stat().st_size > MAX_BYTES
                ):
                    raise ValueError("Zdroj prekračuje limity zálohy.")
                if name.endswith((".sqlite", ".db")):
                    target = Path(temp) / "snapshot.sqlite"
                    with (
                        closing(
                            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                        ) as db,
                        closing(sqlite3.connect(target)) as copied,
                    ):
                        db.backup(copied)
                        copied.execute("PRAGMA journal_mode=DELETE")
                    raw = target.read_bytes()
                    target.unlink()
                else:
                    with path.open("rb") as handle:
                        raw = handle.read(MAX_BYTES + 1)
                total += len(raw)
                if total > MAX_BYTES:
                    raise ValueError("Zdroj prekračuje limit zálohy.")
                files[path.relative_to(source).as_posix()] = encoded(raw)
        config = config or {}
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        manifest = {
            "configSha256": digest(canonical(config)),
            "files": {
                name: digest(base64.b64decode(raw)) for name, raw in files.items()
            },
        }
        content = {
            "format": "skallars-restore-v1",
            "service": "kataster",
            "createdAt": created,
            "revision": os.environ.get("SOURCE_REVISION", "unknown"),
            "config": config,
            "files": files,
            "manifest": manifest,
        }
        output = directory / f"kataster-{created}.enc.json"
        fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(seal(content, public_key)) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            # Hard link publishes atomically without replacing an existing snapshot.
            os.link(temporary, output)
        finally:
            os.unlink(temporary)
    retain(directory, retain_days)
    return {
        "output": str(output),
        "createdAt": created,
        "sha256": digest(output.read_bytes()),
    }


def restore(input: Path, private_key: rsa.RSAPrivateKey, destination: Path) -> dict:
    if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 3072:
        raise ValueError("Vyžaduje sa RSA kľúč s aspoň 3072 bitmi.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Cieľ obnovy už existuje.")
    destination = destination.absolute()
    if input.is_symlink() or input.stat().st_size > MAX_BYTES * 2:
        raise ValueError("Záloha prekračuje limit.")
    try:
        envelope = json.loads(input.read_bytes())
        if (
            envelope["format"] != "skallars-backup-v1"
            or envelope["service"] != "kataster"
        ):
            raise ValueError()
        decode = lambda name: base64.b64decode(envelope[name], validate=True)
        key = private_key.decrypt(decode("key"), OAEP)
        content = json.loads(
            AESGCM(key).decrypt(
                decode("iv"), decode("ciphertext") + decode("tag"), LABEL
            )
        )
        if (
            content["format"] != "skallars-restore-v1"
            or content["service"] != "kataster"
            or not isinstance(content["createdAt"], str)
            or not isinstance(content["revision"], str)
            or not isinstance(content["files"], dict)
            or not isinstance(content["config"], dict)
            or not isinstance(content["manifest"], dict)
            or len(content["files"]) > MAX_FILES
        ):
            raise ValueError()
        files = {}
        for name, raw in content["files"].items():
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or not path.parts
                or any(part in (".", "..") for part in name.split("/"))
                or "\\" in name
                or str(path) != name
                or name in ("config.json", "manifest.json")
            ):
                raise ValueError()
            files[name] = base64.b64decode(raw, validate=True)
        if (
            sum(map(len, files.values())) > MAX_BYTES
            or {name: digest(raw) for name, raw in files.items()}
            != content["manifest"]["files"]
            or digest(canonical(content["config"]))
            != content["manifest"]["configSha256"]
        ):
            raise ValueError()
    except (InvalidTag, KeyError, TypeError, ValueError) as error:
        raise ValueError("Neplatná záloha, kľúč alebo kontrolný súčet.") from error
    temporary = Path(
        tempfile.mkdtemp(prefix=".kataster-restore-", dir=destination.parent)
    )
    try:
        for name, raw in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            if name.endswith((".sqlite", ".db")):
                with closing(
                    sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
                ) as db:
                    if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                        raise ValueError("Poškodená SQLite záloha.")
                # An old snapshot cannot prove remaining live quota or absence of a later block.
                from .cache import today
                from .http import BLOCK_SOURCE
                from .policy import ESKN_HOST, PUBLIC_POLICY

                with closing(sqlite3.connect(path)) as db:
                    tables = {
                        row[0]
                        for row in db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    if "kvota" in tables:
                        db.executemany(
                            "INSERT OR IGNORE INTO kvota VALUES (?, ?)",
                            [
                                (today(), f"restore-guard:{i}")
                                for i in range(PUBLIC_POLICY.owners_daily_hard)
                            ],
                        )
                    if "cache" in tables:
                        db.execute(
                            "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?)",
                            (
                                BLOCK_SOURCE,
                                "1",
                                ESKN_HOST,
                                time.time(),
                                '{"typ":"recovery_pause"}',
                            ),
                        )
                    db.commit()
        content["manifest"]["restoredFilesSha256"] = {
            name: digest((temporary / name).read_bytes()) for name in files
        }
        for name, value in (
            ("config.json", content["config"]),
            ("manifest.json", content["manifest"]),
        ):
            fd = os.open(temporary / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(value))
        # Reserve the isolated target, then publish each already validated file atomically.
        destination.mkdir(mode=0o700)
        try:
            for path in temporary.iterdir():
                os.rename(path, destination / path.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return {"createdAt": content["createdAt"], "revision": content["revision"]}


def execute(args) -> dict:
    from .envelope import Envelope

    try:
        if args.action == "snapshot":
            key = serialization.load_pem_public_key(args.public_key.read_bytes())
            config = {
                name: value
                for name, value in os.environ.items()
                if name
                in (
                    "SK_KATASTER_ORIGIN",
                    "SK_KATASTER_TOKENS",
                    "SK_KATASTER_AUTH_ISSUER",
                    "SK_KATASTER_AUTH_SECRET",
                )
            }
            result = snapshot(
                args.data_dir,
                key,
                args.directory,
                config=config,
                retain_days=args.retain_days,
            )
        else:
            key = serialization.load_pem_private_key(
                args.private_key.read_bytes(), password=None
            )
            result = restore(args.input, key, args.destination)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise ValueError(
            "Záloha alebo obnova zlyhala; skontrolujte argumenty, kľúče a izolovaný cieľ."
        ) from error
    return Envelope().ok(result)
