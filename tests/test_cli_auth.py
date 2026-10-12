"""Offline OAuth boundaries use only synthetic credentials and HTTP transports."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
import pytest

from kataster_mcp import cli_auth as auth
from kataster_mcp.envelope import KatasterError

RESOURCE = "https://resource.example/mcp"
ISSUER = "https://auth.example"


def record():
    return {
        "resource": RESOURCE,
        "issuer": ISSUER,
        "client_id": "synthetic-client",
        "access_token": "synthetic-access",
        "refresh_token": "synthetic-refresh",
        "expires_at": time.time() + 120,
        "scope": "mcp:tools",
    }


def transport(request):
    if request.url.path == "/.well-known/oauth-protected-resource/mcp":
        return httpx.Response(
            200, json={"resource": RESOURCE, "authorization_servers": [ISSUER]}
        )
    if request.url.path == "/.well-known/oauth-authorization-server":
        return httpx.Response(
            200,
            json={
                "issuer": ISSUER,
                "authorization_endpoint": ISSUER + "/auth",
                "token_endpoint": ISSUER + "/token",
                "registration_endpoint": ISSUER + "/register",
                "revocation_endpoint": ISSUER + "/revoke",
                "code_challenge_methods_supported": ["S256"],
            },
        )
    return httpx.Response(
        200,
        json={
            "access_token": "synthetic-new",
            "refresh_token": "synthetic-rotated",
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": "mcp:tools",
        },
    )


def test_pkce_and_callback():
    pkce = auth.PKCEParameters.generate()
    assert pkce.code_challenge == base64.urlsafe_b64encode(
        hashlib.sha256(pkce.code_verifier.encode()).digest()
    ).decode().rstrip("=")
    assert (
        auth.callback_code(
            "/callback?code=synthetic&state=expected&iss=https%3A%2F%2Fauth.example",
            "expected",
            ISSUER,
        )
        == "synthetic"
    )
    for path in (
        "/other?code=x&state=expected",
        "/callback?code=x&state=wrong",
        "/callback?code=x&state=expected&state=expected",
        "/callback?code=x&state=expected&iss=https://evil.example",
        "/callback?error=secret&state=expected",
    ):
        with pytest.raises(KatasterError) as error:
            auth.callback_code(path, "expected", ISSUER)
        assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/mcp",
        "https://user:password@remote.example/mcp",
        "https://remote.example/mcp?token=x",
        "https://remote.example/mcp#x",
    ],
)
def test_reject_unsafe_urls(url):
    with pytest.raises(KatasterError):
        auth.safe_url(url)


@pytest.mark.parametrize("change", ["resource", "issuer", "redirect", "http"])
def test_discovery_rejects_mismatch(change):
    def response(request):
        result = transport(request)
        if change == "redirect":
            return httpx.Response(302, headers={"Location": ISSUER})
        data = result.json()
        if change == "resource" and "resource" in data:
            data["resource"] = "https://resource.example"
        if change == "issuer" and "issuer" in data:
            data["issuer"] = "https://other.example"
        if change == "http" and "token_endpoint" in data:
            data["token_endpoint"] = "http://auth.example/token"
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(KatasterError):
            auth.discover(client, RESOURCE)


def test_storage_permissions_atomic_and_status(tmp_path):
    path = tmp_path / "private" / "oauth.json"
    auth.write_record(path, record())
    assert auth.status(path, RESOURCE)["authenticated"] is True
    assert "token" not in json.dumps(auth.status(path, RESOURCE))
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(KatasterError):
        auth.status(path, "https://other.example/mcp")
    assert not list(path.parent.glob("*.tmp"))
    path.write_text('{"access_token": "secret"}')
    with pytest.raises(KatasterError) as error:
        auth.status(path, RESOURCE)
    assert "secret" not in str(error.value)


def test_concurrent_refresh_rotates_once(tmp_path, monkeypatch):
    path = tmp_path / "oauth.json"
    old = record()
    old["expires_at"] = 0
    auth.write_record(path, old)
    calls = []

    def response(request):
        if request.url.path == "/token":
            calls.append(request.content)
            time.sleep(0.05)
        return transport(request)

    monkeypatch.setattr(
        auth,
        "new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(response)),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert (
            list(pool.map(lambda _: auth.access_token(path, RESOURCE), range(2)))
            == ["synthetic-new"] * 2
        )
    assert len(calls) == 1
    assert json.loads(path.read_text())["refresh_token"] == "synthetic-rotated"


def test_invalid_grant_is_sanitized_and_requires_login(tmp_path, monkeypatch):
    path = tmp_path / "oauth.json"
    old = record()
    old["expires_at"] = 0
    auth.write_record(path, old)

    def response(request):
        if request.url.path == "/token":
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "synthetic-secret",
                },
            )
        return transport(request)

    monkeypatch.setattr(
        auth,
        "new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(response)),
    )
    with pytest.raises(KatasterError) as error:
        auth.access_token(path, RESOURCE)
    assert "synthetic" not in str(error.value)
    assert not path.exists()


def test_native_login_and_logout(tmp_path, monkeypatch, capsys):
    import threading
    from urllib.parse import parse_qs, urlsplit

    path = tmp_path / "oauth.json"
    requests = []
    browser_threads = []

    def response(request):
        requests.append(request)
        if request.url.path == "/register":
            body = json.loads(request.content)
            assert body["application_type"] == "native"
            assert body["token_endpoint_auth_method"] == "none"
            return httpx.Response(
                201,
                json={
                    "client_id": "synthetic-client",
                    "redirect_uris": body["redirect_uris"],
                    "token_endpoint_auth_method": "none",
                },
            )
        return transport(request)

    def browser(url):
        values = parse_qs(urlsplit(url).query)
        assert values["resource"] == [RESOURCE]
        assert values["scope"] == ["mcp:tools"]
        assert values["code_challenge_method"] == ["S256"]
        callback = values["redirect_uri"][0]

        def send_callback():
            with httpx.Client(trust_env=False) as client:
                assert (
                    client.get(
                        callback, params={"state": "wrong", "code": "wrong"}
                    ).status_code
                    == 400
                )
                assert (
                    client.get(
                        callback,
                        params={
                            "state": values["state"][0],
                            "code": "synthetic-code",
                            "iss": ISSUER,
                        },
                    ).status_code
                    == 200
                )

        thread = threading.Thread(target=send_callback)
        thread.start()
        browser_threads.append(thread)
        return True

    monkeypatch.setattr(
        auth,
        "new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(response)),
    )
    monkeypatch.setattr(auth.webbrowser, "open", browser)
    assert auth.login(path, RESOURCE)["authenticated"] is True
    for thread in browser_threads:
        thread.join(5)
        assert not thread.is_alive()
    token_request = next(r for r in requests if r.url.path == "/token")
    values = parse_qs(token_request.content.decode())
    assert values["code"] == ["synthetic-code"]
    assert values["resource"] == [RESOURCE]
    assert len(values["code_verifier"][0]) >= 43
    captured = capsys.readouterr()
    assert "synthetic-new" not in captured.out + captured.err
    assert "synthetic-rotated" not in captured.out + captured.err
    assert auth.logout(path, RESOURCE)["revoked"] is True
    assert not path.exists()
    assert len([r for r in requests if r.url.path == "/revoke"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("access_token", "bad\nheader"),
        ("expires_in", -1),
        ("expires_in", float("nan")),
        ("token_type", "MAC"),
        ("scope", "other"),
        ("refresh_token", {}),
    ],
)
def test_invalid_token_response(field, value):
    data = transport(httpx.Request("POST", ISSUER + "/token")).json()
    data[field] = value
    with pytest.raises(KatasterError):
        auth.token_record(data, record())


def test_refresh_issuer_change_never_sends_credentials(tmp_path, monkeypatch):
    path = tmp_path / "oauth.json"
    old = record()
    old["expires_at"] = 0
    auth.write_record(path, old)
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "resource": RESOURCE,
                "authorization_servers": ["https://evil.example"],
            },
        )

    monkeypatch.setattr(
        auth,
        "new_client",
        lambda: httpx.Client(transport=httpx.MockTransport(response)),
    )
    with pytest.raises(KatasterError):
        auth.access_token(path, RESOURCE)
    assert len(calls) == 1
    assert "synthetic-refresh" not in str(calls[0].headers)


def test_logout_removes_local_record_when_revocation_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "oauth.json"
    auth.write_record(path, record())
    monkeypatch.setattr(
        auth,
        "new_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(503))
        ),
    )
    assert auth.logout(path, RESOURCE)["revoked"] is False
    assert not path.exists()


def test_process_refresh_uses_one_rotation(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "oauth.json"
    log = tmp_path / "requests.log"
    old = record()
    old["expires_at"] = 0
    auth.write_record(path, old)
    code = """import sys,time,httpx
from pathlib import Path
from kataster_mcp import cli_auth as auth
path,log=map(Path,sys.argv[1:])
def response(request):
    if request.url.path == '/.well-known/oauth-protected-resource/mcp':
        return httpx.Response(200,json={'resource':'https://resource.example/mcp','authorization_servers':['https://auth.example']})
    if request.url.path == '/.well-known/oauth-authorization-server':
        return httpx.Response(200,json={'issuer':'https://auth.example','authorization_endpoint':'https://auth.example/auth','token_endpoint':'https://auth.example/token','code_challenge_methods_supported':['S256']})
    with log.open('a') as handle: handle.write('refresh\\n')
    time.sleep(0.2)
    return httpx.Response(200,json={'access_token':'synthetic-new','refresh_token':'synthetic-rotated','token_type':'Bearer','expires_in':300,'scope':'mcp:tools'})
auth.new_client=lambda: httpx.Client(transport=httpx.MockTransport(response))
assert auth.access_token(path,'https://resource.example/mcp') == 'synthetic-new'
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(path), str(log)],
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode()
        assert stdout == b""
    assert log.read_text().splitlines() == ["refresh"]


def test_failed_replace_preserves_original_record(tmp_path, monkeypatch):
    path = tmp_path / "oauth.json"
    auth.write_record(path, record())
    original = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("synthetic failure")

    monkeypatch.setattr(auth.os, "replace", fail_replace)
    with pytest.raises(OSError):
        auth.write_record(path, {**record(), "access_token": "synthetic-new"})
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))


def test_symlink_store_and_lock_are_rejected(tmp_path):
    if os.name == "nt":
        pytest.skip("Symlink creation requires a Windows privilege")
    target = tmp_path / "target"
    target.write_text(json.dumps(record()))
    path = tmp_path / "oauth.json"
    path.symlink_to(target)
    with pytest.raises(KatasterError):
        auth.status(path, RESOURCE)
    path.unlink()
    path.with_name("oauth.json.lock").unlink()
    path.with_name("oauth.json.lock").symlink_to(target)
    with pytest.raises(KatasterError):
        auth.status(path, RESOURCE)


def test_logout_clears_corrupt_credentials(tmp_path):
    path = tmp_path / "oauth.json"
    path.write_text('{"access_token":"synthetic-secret"}')
    assert auth.logout(path, RESOURCE)["revoked"] is False
    assert not path.exists()
