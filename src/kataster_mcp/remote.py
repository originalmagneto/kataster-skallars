"""Single-process private HTTP pilot with per-user storage and expiring bearer keys."""

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from . import __version__, lv
from .cache import PERSONAL_TTL, Cache, Quota, purge_files
from .cli import compact
from .envelope import Envelope
from .http import Http
from .policy import PUBLIC_POLICY
from .server import create_server

MAX_UPLOAD = 5 * 1024**2
UPLOAD_TTL = 86400
FILE_ID = re.compile(r"[a-f0-9]{32}")
TENANT = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def read_tokens(path: Path) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) > 16:
        raise ValueError("Expected up to 16 user tokens")
    for record in records:
        if (
            not TENANT.fullmatch(record["tenant"])
            or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])
            or not isinstance(record["expires"], (int, float))
        ):
            raise ValueError("Invalid token record")
    return records


async def parse_upload(raw: bytes) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "kataster_mcp.remote_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(raw), timeout=20)
        if process.returncode or len(output) > 2 * 1024**2:
            raise ToolError(
                "Dokument sa nepodarilo bezpečne prečítať (formát alebo limit parsera)."
            )
        return json.loads(output)
    except TimeoutError:
        raise ToolError("Parser prekročil časový limit 20 sekúnd.") from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def remote_tools(server, directory: Path) -> None:
    server.remove_tool("kataster_lv_import")
    server.remove_tool(
        "kataster_mapa"
    )  # Local filesystem exports need an authenticated download API first.
    server.remove_tool("kataster_status")

    @server.tool()
    async def kataster_lv_import(file_id: str, full: bool = False) -> dict:
        """Import own uploaded LV using file_id from POST /uploads. No local paths. Compact by default."""
        if not FILE_ID.fullmatch(file_id):
            raise ToolError("Neplatný file_id.")
        path = directory / "uploads" / file_id
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_mtime + UPLOAD_TTL <= time.time()
        ):
            raise ToolError("Súbor sa nenašiel alebo expiroval.")
        raw = path.read_bytes()
        if len(raw) > MAX_UPLOAD:
            raise ToolError("Súbor prekračuje limit.")
        data = await parse_upload(raw)
        _, saved = lv.store_import(server.app_state.osoby, data, [f"upload:{file_id}"])
        data["ulozenie"] = {"stav": "stored" if saved else "preserved_existing"}
        env = Envelope()
        env.source(lv.IMPORT, f"upload:{file_id}", oficialny=False, z_cache=False)
        env.warn(
            "Rozsah výpisu nie je overený ako úplný. Chýbajúca časť C nepotvrdzuje neprítomnosť tiarch."
        )
        if not saved:
            env.warn(
                "Uložený výpis má novší dátum alebo širší rozsah. Výsledok opisuje vstup, prehľad používa pôvodný výpis."
            )
        return env.ok(data if full else compact(data))

    @server.tool()
    async def kataster_status() -> dict:
        """Remote version and retention, without filesystem paths or other users' statistics."""
        return Envelope().ok(
            {
                "verzia": __version__,
                "mode": "remote",
                "auth": "personal_bearer",
                "upload_ttl_seconds": UPLOAD_TTL,
                "personal_ttl_seconds": PERSONAL_TTL,
            }
        )


class Remote:
    def __init__(self, data_dir: Path, token_file: Path, origin: str):
        self.data_dir, self.token_file, self.origin = (
            data_dir,
            token_file,
            origin.rstrip("/"),
        )
        parsed = urlsplit(self.origin)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.path:
            raise ValueError("Invalid public origin")
        if parsed.scheme != "https" and parsed.hostname not in (
            "localhost",
            "127.0.0.1",
            "testserver",
        ):
            raise ValueError("HTTPS required")
        self.host = parsed.netloc
        self.http = Http(PUBLIC_POLICY)
        self.shared = Cache(data_dir / "shared" / "cache.sqlite", private=True)
        self.quota = Quota(self.shared.db)
        self.lock = asyncio.Lock()
        self.pending = 0
        self.servers, self.apps = {}, {}
        for tenant in {r["tenant"] for r in read_tokens(token_file)}:
            directory = data_dir / "users" / tenant
            server = create_server(data_dir=directory, http=self.http)
            server.app_state.quota = self.quota
            page_size = server.app_state.osoby.db.execute(
                "PRAGMA page_size"
            ).fetchone()[0]
            server.app_state.osoby.db.execute(
                f"PRAGMA max_page_count={64 * 1024**2 // page_size}"
            )
            remote_tools(server, directory)
            self.servers[tenant] = server
            self.apps[tenant] = server.streamable_http_app(
                stateless_http=True,
                json_response=True,
                max_request_body_size=65536,
                transport_security=TransportSecuritySettings(
                    allowed_hosts=[self.host], allowed_origins=[self.origin]
                ),
            )
        self.http.blocks = self.shared
        self.app = Starlette(
            routes=[
                Route("/health", self.health),
                Route("/uploads", self.upload, methods=["POST"]),
            ],
            lifespan=self.lifespan,
        )

    async def health(self, request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "revision": os.environ.get("SOURCE_REVISION", "unknown"),
            }
        )

    async def upload(self, request: Request) -> JSONResponse:
        if request.headers.get("content-type", "").split(";")[0] not in (
            "text/html",
            "application/pdf",
            "application/xhtml+xml",
        ):
            return JSONResponse(
                {"error": "HTML alebo PDF je povinné."}, status_code=415
            )
        directory = self.data_dir / "users" / request.scope["tenant"] / "uploads"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        purge_files(directory, UPLOAD_TTL)
        if len(list(directory.iterdir())) >= 50:
            return JSONResponse(
                {"error": "Limit 50 uploadov za 24 hodín."}, status_code=429
            )
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_UPLOAD:
                return JSONResponse({"error": "Limit 5 MiB."}, status_code=413)
        if not raw:
            return JSONResponse({"error": "Prázdny upload."}, status_code=400)
        file_id = secrets.token_hex(16)
        path = directory / file_id
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        return JSONResponse(
            {"file_id": file_id, "expires": int(time.time() + UPLOAD_TTL)},
            status_code=201,
        )

    async def purge_loop(self) -> None:
        while True:
            async with self.lock:
                for directory in (self.data_dir / "users").glob("*"):
                    if not directory.is_dir() or directory.is_symlink():
                        continue
                    server = self.servers.get(directory.name)
                    if server:
                        server.app_state.osoby.purge()
                    elif (directory / "osoby.sqlite").is_file():
                        cache = Cache(
                            directory / "osoby.sqlite",
                            private=True,
                            max_age_s=PERSONAL_TTL,
                        )
                        cache.db.close()
                    purge_files(directory / "uploads", UPLOAD_TTL)
                    purge_files(directory / "snapshots", PERSONAL_TTL)
            await asyncio.sleep(60)

    @asynccontextmanager
    async def lifespan(self, app):
        async with AsyncExitStack() as stack:
            for child in self.apps.values():
                await stack.enter_async_context(child.router.lifespan_context(child))
            purge = asyncio.create_task(self.purge_loop())
            try:
                yield
            finally:
                purge.cancel()
                with suppress(asyncio.CancelledError):
                    await purge
                await self.http.aclose()
                for server in self.servers.values():
                    server.app_state.cache.db.close()
                    server.app_state.osoby.db.close()
                self.shared.db.close()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        if headers.get("host") != self.host:
            return await JSONResponse({"error": "Invalid host"}, 421)(
                scope, receive, send
            )
        if headers.get("origin") not in (None, self.origin):
            return await JSONResponse({"error": "Invalid origin"}, 403)(
                scope, receive, send
            )
        if scope["path"] == "/health":
            return await self.app(scope, receive, send)
        auth = headers.get("authorization", "")
        digest = (
            hashlib.sha256(auth[7:].encode()).hexdigest()
            if auth.startswith("Bearer ")
            else ""
        )
        try:
            tenant = next(
                (
                    r["tenant"]
                    for r in read_tokens(self.token_file)
                    if hmac.compare_digest(digest, r["sha256"])
                    and r["expires"] > time.time()
                ),
                None,
            )
        except (OSError, ValueError, KeyError, TypeError):
            tenant = None
        if tenant not in self.apps:
            return await JSONResponse(
                {"error": "Unauthorized"},
                401,
                headers={"WWW-Authenticate": 'Bearer realm="kataster"'},
            )(scope, receive, send)
        scope["tenant"] = tenant
        # shortcut: one replica serializes requests; use a shared queue before scaling.
        if self.pending >= 8:
            return await JSONResponse(
                {"error": "Server busy, retry shortly"},
                429,
                headers={"Retry-After": "3"},
            )(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        (k, v)
                        for k, v in message["headers"]
                        if k.lower() != b"content-length"
                    ]
                    + [(b"cache-control", b"no-store")],
                }
            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                if b'"isError":true' in body or b'"isError": true' in body:
                    message = {
                        **message,
                        "body": body.replace(str(self.data_dir).encode(), b"[private]"),
                    }
            await send(message)

        self.pending += 1
        try:
            async with asyncio.timeout(120):
                async with self.lock:
                    target = self.apps[tenant] if scope["path"] == "/mcp" else self.app
                    await target(scope, receive, private_send)
        except TimeoutError:
            return await JSONResponse({"error": "Request timeout"}, 504)(
                scope, receive, send
            )
        finally:
            self.pending -= 1


def create_app(data_dir: Path, token_file: Path, origin: str) -> Remote:
    return Remote(data_dir, token_file, origin)


def main() -> None:
    import uvicorn

    data = Path(os.environ.get("SK_KATASTER_DATA_DIR", "/data"))
    token_file = Path(os.environ.get("SK_KATASTER_TOKEN_FILE", "/run/tokens.json"))
    # Dokploy injects hashes only; plaintext credentials stay on the user's computer.
    if config := os.environ.get("SK_KATASTER_TOKENS"):
        token_file = Path("/tmp/kataster-tokens.json")
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(config)
    uvicorn.run(
        create_app(data, token_file, os.environ["SK_KATASTER_ORIGIN"]),
        host="0.0.0.0",
        port=8000,
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
