"""Promote tested immutable images using same-repository GitHub access only."""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BRANCH = "dokploy-production"


def request(
    url, *, method="GET", data=None, headers=None, allowed=(200, 201, 202, 204)
):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Vyžaduje sa HTTPS.")
    raw = (
        data
        if isinstance(data, bytes)
        else (None if data is None else json.dumps(data).encode())
    )
    req = urllib.request.Request(
        url,
        data=raw,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status, body = response.status, response.read(1024 * 1024)
        if status not in allowed:
            raise RuntimeError()
        return status, body
    except Exception:
        # Webhook and query strings can contain credentials.
        raise RuntimeError("HTTP požiadavka zlyhala.") from None


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("Neplatný repozitár.")
        self.base = "https://api.github.com/repos/" + repository
        self.headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def api(self, path, method="GET", data=None):
        _, raw = request(
            self.base + path, method=method, data=data, headers=self.headers
        )
        return json.loads(raw)

    def ref(self, name):
        return self.api("/git/ref/heads/" + name)["object"]["sha"]

    def file(self, path, ref):
        value = self.api("/contents/" + path + "?ref=" + ref)
        return base64.b64decode(value["content"]).decode()

    def commit(self, source, parent, files, message):
        tree = self.api("/git/commits/" + source)["tree"]["sha"]
        if files:
            tree = self.api(
                "/git/trees",
                "POST",
                {
                    "base_tree": tree,
                    "tree": [
                        {
                            "path": path,
                            "mode": "100644",
                            "type": "blob",
                            "content": content,
                        }
                        for path, content in files.items()
                    ],
                },
            )["sha"]
        return self.api(
            "/git/commits",
            "POST",
            {"message": message, "tree": tree, "parents": [parent]},
        )["sha"]

    def update(self, sha):
        self.api("/git/refs/heads/" + BRANCH, "PATCH", {"sha": sha, "force": False})


def compose_release(template, image, source):
    # Templates deliberately have one service, one build and one revision slot.
    compose, builds = re.subn(
        r"(?m)^    build: \.\s*$", "    image: " + image, template
    )
    compose, revisions = re.subn(
        r"(?m)^      SOURCE_REVISION: .*?$",
        '      SOURCE_REVISION: "' + source + '"',
        compose,
    )
    if builds != 1 or revisions != 1:
        raise ValueError("Compose šablóna nemá presne jeden build a revision.")
    return compose


def validate(source, image, service, origin):
    if (
        service not in ("kataster", "auth")
        or not re.fullmatch(r"[0-9a-f]{40}", source)
        or not re.fullmatch(
            r"registry-mcp\.aittorney\.online/[a-z0-9/-]+@sha256:[0-9a-f]{64}", image
        )
    ):
        raise ValueError("Neplatný zdroj, služba alebo immutable digest.")
    if (
        origin
        != {
            "kataster": "https://mcp-kataster.aittorney.online",
            "auth": "https://auth.aittorney.online",
        }[service]
    ):
        raise ValueError("Neplatná origin.")


def promote(git, source, image, service, origin, trigger, smoke):
    validate(source, image, service, origin)
    if git.ref("main") != source:
        print("Staršie main vydanie preskočené.")
        return False
    parent = git.ref(BRANCH)
    previous = json.loads(git.file(".dokploy-release.json", parent))
    validate(
        previous["source"], previous["image"], previous["service"], previous["origin"]
    )
    if previous["service"] != service or previous["origin"] != origin:
        raise ValueError("Predchádzajúce vydanie patrí inej službe.")
    manifest = {
        "source": source,
        "image": image,
        "service": service,
        "origin": origin,
        "previous": parent,
    }
    compose = compose_release(git.file("compose.yaml", source), image, source)
    commit = git.commit(
        source,
        parent,
        {
            "compose.yaml": compose,
            ".dokploy-release.json": json.dumps(manifest, indent=2) + "\n",
        },
        "Deploy " + source + " " + image,
    )
    if git.ref("main") != source:
        print("Staršie main vydanie preskočené.")
        return False
    try:
        git.update(commit)
        trigger(commit)
        smoke(manifest)
    except Exception:
        try:
            current = git.ref(BRANCH)
        except Exception:
            raise RuntimeError(
                "Stav production ref je neznámy; vyžaduje sa zásah správcu."
            ) from None
        if current == parent:
            raise RuntimeError(
                "Vydanie zlyhalo; production ref zostal pôvodný."
            ) from None
        if current != commit:
            raise RuntimeError(
                "Production ref zmenil iný aktér; vyžaduje sa zásah správcu."
            ) from None
        try:
            rollback = git.commit(
                parent, commit, {}, "Rollback " + source + " to " + previous["source"]
            )
            git.update(rollback)
            trigger(rollback)
            smoke(previous)
        except Exception:
            raise RuntimeError(
                "Vydanie aj obnova zlyhali; vyžaduje sa zásah správcu."
            ) from None
        raise RuntimeError(
            "Vydanie zlyhalo; predchádzajúce vydanie obnovené."
        ) from None
    print("Vydanie overené: " + source)
    return True


def webhook(url, sha):
    request(
        url,
        method="POST",
        headers={"x-github-event": "push"},
        data={
            "ref": "refs/heads/" + BRANCH,
            "after": sha,
            "head_commit": {"message": "Deploy " + sha},
            "commits": [
                {"added": ["compose.yaml"], "modified": ["compose.yaml"], "removed": []}
            ],
        },
    )


def smoke(manifest, timeout=360):
    origin, revision, service = (
        manifest["origin"],
        manifest["source"],
        manifest["service"],
    )
    deadline = time.monotonic() + timeout
    while True:
        try:
            _, body = request(origin + "/health")
            if json.loads(body)["revision"] != revision:
                raise ValueError()
            path = (
                "/.well-known/oauth-protected-resource/mcp"
                if service == "kataster"
                else "/.well-known/openid-configuration"
            )
            _, body = request(origin + path)
            metadata = json.loads(body)
            if service == "kataster":
                if metadata["resource"] != origin + "/mcp" or metadata[
                    "authorization_servers"
                ] != ["https://auth.aittorney.online"]:
                    raise ValueError()
                status, _ = request(
                    origin + "/mcp",
                    method="POST",
                    data={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "release-smoke", "version": "1"},
                        },
                    },
                    allowed=(401,),
                )
            elif (
                metadata["issuer"] != origin
                or "S256" not in metadata["code_challenge_methods_supported"]
            ):
                raise ValueError()
            if service == "auth":
                request(
                    origin + "/resource/introspect",
                    method="POST",
                    data=b"resource=release-smoke",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    allowed=(401,),
                )
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("Health alebo discovery kontrola zlyhala.") from None
            time.sleep(5)


def main():
    try:
        if (
            os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") != "push"
        ):
            print("Promotion je povolená iba pre push main.")
            return 0
        git = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
        promote(
            git,
            os.environ["GITHUB_SHA"],
            os.environ["RELEASE_IMAGE"],
            os.environ["RELEASE_SERVICE"],
            os.environ["RELEASE_ORIGIN"],
            lambda sha: webhook(os.environ["DOKPLOY_WEBHOOK"], sha),
            smoke,
        )
        return 0
    except Exception as error:
        print(
            (
                str(error)
                if isinstance(error, RuntimeError)
                else "Promotion zlyhala; skontrolujte konfiguráciu a baseline."
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
