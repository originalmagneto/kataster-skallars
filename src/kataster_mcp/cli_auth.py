"""Native OAuth with exact discovery binding and a locked, atomic token store."""

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

import httpx
from mcp.client.auth.oauth2 import PKCEParameters

from .envelope import KatasterError

DEFAULT_AUTH_FILE = Path.home() / ".config/kataster-skallars/oauth.json"


def failure(
    message: str = "OAuth požiadavka zlyhala. Skúste remote login.",
) -> KatasterError:
    return KatasterError("unavailable", message)


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        (
            parsed.scheme != "https"
            and not (parsed.scheme == "http" and parsed.hostname == "127.0.0.1")
        )
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise KatasterError(
            "invalid_input",
            "OAuth URL vyžaduje HTTPS alebo lokálne 127.0.0.1 bez poverení.",
        )
    return url


def new_client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=False)


def request_json(client: httpx.Client, method: str, url: str, **kwargs) -> dict:
    safe_url(url)
    try:
        response = client.request(method, url, **kwargs)
        if response.status_code != 200 and response.status_code != 201:
            raise failure()
        data = response.json()
        if not isinstance(data, dict):
            raise failure()
        return data
    except (httpx.HTTPError, ValueError):
        raise failure() from None


def discover(client: httpx.Client, resource: str, issuer: str | None = None) -> dict:
    safe_url(resource)
    parsed = urlsplit(resource)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    prm = request_json(
        client, "GET", origin + "/.well-known/oauth-protected-resource" + parsed.path
    )
    servers = prm.get("authorization_servers")
    if (
        prm.get("resource") != resource
        or not isinstance(servers, list)
        or len(servers) != 1
        or not isinstance(servers[0], str)
    ):
        raise failure("OAuth discovery nezodpovedá presnému resource.")
    expected = safe_url(servers[0])
    if issuer is not None and issuer != expected:
        raise failure("OAuth issuer sa zmenil. Vyžaduje sa nové prihlásenie.")
    parsed_issuer = urlsplit(expected)
    metadata_url = f"{parsed_issuer.scheme}://{parsed_issuer.netloc}/.well-known/oauth-authorization-server{parsed_issuer.path.rstrip('/')}"
    metadata = request_json(client, "GET", metadata_url)
    if metadata.get("issuer") != expected or "S256" not in metadata.get(
        "code_challenge_methods_supported", []
    ):
        raise failure("OAuth discovery má neplatný issuer alebo nepodporuje S256.")
    for name in (
        "authorization_endpoint",
        "token_endpoint",
        "registration_endpoint",
        "revocation_endpoint",
    ):
        endpoint = metadata.get(name)
        if name in ("authorization_endpoint", "token_endpoint") and not endpoint:
            raise failure()
        if endpoint:
            if not isinstance(endpoint, str):
                raise failure()
            safe_url(endpoint)
            endpoint_url = urlsplit(endpoint)
            if (endpoint_url.scheme, endpoint_url.netloc) != (
                parsed_issuer.scheme,
                parsed_issuer.netloc,
            ):
                raise failure("OAuth endpoint nezodpovedá issuer origin.")
    return metadata


def private_directory(path: Path) -> None:
    if path.resolve() in (Path.home().resolve(), Path(path.anchor).resolve()):
        raise failure("OAuth súbor vyžaduje samostatný súkromný adresár.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise failure("OAuth adresár nesmie byť symlink.")
    if os.name != "nt":
        path.chmod(0o700)


@contextmanager
def locked(path: Path):
    private_directory(path.parent)
    lock_path = path.with_name(path.name + ".lock")
    if lock_path.is_symlink():
        raise failure("OAuth zámok nesmie byť symlink.")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    with os.fdopen(fd, "r+b") as handle:
        if os.name == "nt":
            import msvcrt

            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            deadline = time.monotonic() + 360
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise failure("OAuth úložisko je obsadené.") from None
                    time.sleep(0.1)
        else:
            import fcntl

            os.fchmod(handle.fileno(), 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_record(path: Path, data: dict) -> None:
    private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_record(path: Path, resource: str) -> dict | None:
    if path.is_symlink():
        raise failure("OAuth súbor nesmie byť symlink.")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, encoding="utf-8") as handle:
            data = json.loads(handle.read(65537))
        if not isinstance(data, dict) or data.get("resource") != resource:
            raise failure("OAuth úložisko nezodpovedá resource.")
        for key in ("issuer", "client_id", "access_token", "scope"):
            if (
                not isinstance(data.get(key), str)
                or not data[key]
                or any(ord(c) < 32 for c in data[key])
            ):
                raise failure()
        safe_url(data["issuer"])
        expires = data.get("expires_at")
        if (
            not isinstance(expires, (float, int))
            or not math.isfinite(expires)
            or isinstance(expires, bool)
        ):
            raise failure()
        if data.get("refresh_token") is not None and (
            not isinstance(data["refresh_token"], str) or not data["refresh_token"]
        ):
            raise failure()
        if "mcp:tools" not in data["scope"].split():
            raise failure()
        if os.name != "nt":
            path.chmod(0o600)
        return data
    except FileNotFoundError:
        return None
    except (ValueError, TypeError):
        raise failure("OAuth úložisko je poškodené. Skúste remote login.") from None


def status(path: Path, resource: str) -> dict:
    with locked(path):
        data = read_record(path, resource)
        if data is None:
            return {"authenticated": False, "resource": resource}
        return {
            "authenticated": True,
            "resource": resource,
            "issuer": data["issuer"],
            "expires_at": data["expires_at"],
            "expired": data["expires_at"] <= time.time(),
            "refresh_available": bool(data.get("refresh_token")),
        }


def token_record(data: dict, previous: dict) -> dict:
    if not isinstance(data, dict):
        raise failure("OAuth odpoveď obsahuje neplatný token.")
    token = data.get("access_token")
    expiry = data.get("expires_in")
    refresh = data.get("refresh_token", previous.get("refresh_token"))
    scope = data.get("scope", previous.get("scope", "mcp:tools"))
    if (
        not isinstance(token, str)
        or not token
        or any(ord(c) < 33 or ord(c) > 126 for c in token)
        or not isinstance(data.get("token_type"), str)
        or data["token_type"].lower() != "bearer"
        or not isinstance(expiry, (int, float))
        or isinstance(expiry, bool)
        or not math.isfinite(expiry)
        or expiry <= 0
        or not isinstance(scope, str)
        or "mcp:tools" not in scope.split()
        or (refresh is not None and (not isinstance(refresh, str) or not refresh))
    ):
        raise failure("OAuth odpoveď obsahuje neplatný token.")
    return {
        **previous,
        "access_token": token,
        "refresh_token": refresh,
        "scope": scope,
        "expires_at": time.time() + expiry,
    }


def access_token(path: Path, resource: str) -> str:
    with locked(path):
        data = read_record(path, resource)
        if data is None:
            raise failure("Chýba OAuth prihlásenie. Spustite remote login.")
        if data["expires_at"] > time.time() + 30:
            return data["access_token"]
        if not data.get("refresh_token"):
            raise failure("OAuth prihlásenie expirovalo. Spustite remote login.")
        with new_client() as client:
            metadata = discover(client, resource, data["issuer"])
            response = client.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "refresh_token",
                    "client_id": data["client_id"],
                    "refresh_token": data["refresh_token"],
                    "resource": resource,
                },
            )
            if response.status_code == 400:
                try:
                    invalid = response.json().get("error") == "invalid_grant"
                except (ValueError, AttributeError):
                    invalid = False
                if invalid:
                    path.unlink(missing_ok=True)
                    raise failure(
                        "OAuth prihlásenie bolo odobraté alebo expirovalo. Spustite remote login."
                    )
            if response.status_code != 200:
                raise failure()
            try:
                updated = token_record(response.json(), data)
            except (ValueError, AttributeError):
                raise failure() from None
            write_record(path, updated)
            return updated["access_token"]


def callback_code(target: str, state: str, issuer: str) -> str:
    parsed = urlsplit(target)
    values = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.path != "/callback"
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or any(len(v) != 1 for v in values.values())
        or values.get("error")
        or not secrets.compare_digest(
            values.get("state", [""])[0].encode(), state.encode()
        )
        or ("iss" in values and values["iss"][0] != issuer)
        or not values.get("code", [""])[0]
    ):
        raise failure("OAuth callback neprešiel kontrolou state, issuer alebo cesty.")
    return values["code"][0]


def login(path: Path, resource: str, no_browser: bool = False) -> dict:
    with locked(path), new_client() as client:
        metadata = discover(client, resource)
        state = secrets.token_urlsafe(32)
        pkce = PKCEParameters.generate()
        result: list[str] = []

        class Callback(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    if (
                        self.headers.get("Host")
                        != f"127.0.0.1:{self.server.server_port}"
                    ):
                        raise failure()
                    code = callback_code(self.path, state, metadata["issuer"])
                    result.append(code)
                    self.send_response(200)
                    body = b"Prihlasenie dokoncene. Mozete zatvorit toto okno."
                except KatasterError:
                    self.send_response(400)
                    body = b"Neplatny OAuth callback."
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        class LoopbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(5)
                return connection, address

        with LoopbackServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = 1
            redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
            registration = metadata.get("registration_endpoint")
            if not registration:
                raise failure("OAuth autorita nepodporuje registráciu CLI klienta.")
            info = request_json(
                client,
                "POST",
                registration,
                json={
                    "client_name": "Kataster SKALLARS CLI",
                    "application_type": "native",
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": "mcp:tools",
                },
            )
            client_id = info.get("client_id")
            if (
                not isinstance(client_id, str)
                or not client_id
                or info.get("client_secret")
                or info.get("redirect_uris") != [redirect_uri]
                or info.get("token_endpoint_auth_method", "none") != "none"
            ):
                raise failure("OAuth registrácia nevrátila platného native klienta.")
            url = (
                metadata["authorization_endpoint"]
                + "?"
                + urlencode(
                    {
                        "response_type": "code",
                        "client_id": client_id,
                        "redirect_uri": redirect_uri,
                        "scope": "mcp:tools",
                        "resource": resource,
                        "state": state,
                        "code_challenge": pkce.code_challenge,
                        "code_challenge_method": "S256",
                    }
                )
            )
            print("Otvorte prihlasovací odkaz v prehliadači:\n" + url, file=sys.stderr)
            if not no_browser:
                webbrowser.open(url)
            deadline = time.monotonic() + 300
            while not result and time.monotonic() < deadline:
                server.handle_request()
            if not result:
                raise failure("OAuth callback neprišiel do 5 minút.")
            tokens = request_json(
                client,
                "POST",
                metadata["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": result[0],
                    "redirect_uri": redirect_uri,
                    "code_verifier": pkce.code_verifier,
                    "resource": resource,
                },
            )
            data = token_record(
                tokens,
                {
                    "resource": resource,
                    "issuer": metadata["issuer"],
                    "client_id": client_id,
                },
            )
            write_record(path, data)
        return {"authenticated": True, "resource": resource, "issuer": data["issuer"]}


def logout(path: Path, resource: str) -> dict:
    revoked = False
    with locked(path):
        try:
            data = read_record(path, resource)
            if data:
                with new_client() as client:
                    metadata = discover(client, resource, data["issuer"])
                    endpoint = metadata.get("revocation_endpoint")
                    if endpoint:
                        for name in ("refresh_token", "access_token"):
                            if data.get(name):
                                response = client.post(
                                    endpoint,
                                    data={
                                        "token": data[name],
                                        "token_type_hint": name,
                                        "client_id": data["client_id"],
                                    },
                                )
                                if response.status_code != 200:
                                    raise failure()
                        revoked = True
        except (KatasterError, httpx.HTTPError, ValueError):
            pass
        finally:
            path.unlink(missing_ok=True)
    return {"authenticated": False, "resource": resource, "revoked": revoked}
