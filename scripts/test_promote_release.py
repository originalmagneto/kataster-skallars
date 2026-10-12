import sys

sys.dont_write_bytecode = True
import unittest
from unittest.mock import patch

import promote_release as release

SHA = "a" * 40
DIGEST = "registry-mcp.aittorney.online/kataster@sha256:" + "b" * 64


class Git:
    def __init__(self, stale=False):
        self.stale = stale
        self.production = "f" * 40
        self.calls = []
        self.trees = {SHA: "current-workflows", self.production: "old-workflows"}
        self.previous = {
            "source": "c" * 40,
            "image": "registry-mcp.aittorney.online/kataster@sha256:" + "d" * 64,
            "service": "kataster",
            "origin": "https://mcp-kataster.aittorney.online",
            "retained_field": "preserve raw manifest bytes",
        }
        self.previous_manifest = release.json.dumps(self.previous, indent=4) + "\n\n"
        self.template = "services:\n  kataster:\n    build: .\n    environment:\n      SOURCE_REVISION: ${SOURCE_REVISION:-unknown}\n    volumes:\n      - kataster-data:/data\nvolumes:\n  kataster-data:\n"
        self.previous_template = self.template.replace("kataster-data", "previous-data")
        self.previous_compose = release.compose_release(
            self.previous_template, self.previous["image"], self.previous["source"]
        )

    def ref(self, name):
        return ("e" * 40 if self.stale else SHA) if name == "main" else self.production

    def file(self, path, ref):
        if path == ".dokploy-release.json":
            return self.previous_manifest
        if ref == "f" * 40:
            return self.previous_compose
        return self.previous_template if ref == self.previous["source"] else self.template

    def commit(self, source, parent, files, message):
        self.calls.append(("commit", source, parent, files))
        sha = str(len(self.calls)) * 40
        self.trees[sha] = self.trees[source]
        return sha

    def update(self, sha):
        if self.trees[sha] != "current-workflows":
            raise RuntimeError("403: native CI token cannot restore old workflows")
        self.calls.append(("update", sha, False))
        self.production = sha


class PromotionTests(unittest.TestCase):
    def test_exact_digest_parent_and_literal_revision(self):
        git = Git()
        release.promote(
            git,
            SHA,
            DIGEST,
            "kataster",
            "https://mcp-kataster.aittorney.online",
            lambda sha: None,
            lambda manifest: None,
        )
        call = git.calls[0]
        self.assertEqual(call[1:3], (SHA, "f" * 40))
        self.assertIn("image: " + DIGEST, call[3]["compose.yaml"])
        self.assertIn('SOURCE_REVISION: "' + SHA + '"', call[3]["compose.yaml"])
        self.assertIn("kataster-data:/data", call[3]["compose.yaml"])
        self.assertEqual(git.calls[1][2], False)

    def test_stale_main_no_mutation(self):
        git = Git(stale=True)
        self.assertFalse(
            release.promote(
                git,
                SHA,
                DIGEST,
                "kataster",
                "https://mcp-kataster.aittorney.online",
                lambda sha: None,
                lambda manifest: None,
            )
        )
        self.assertEqual(git.calls, [])

    def test_failure_rolls_back_exact_runtime_on_current_workflows_linearly(self):
        for error in (TimeoutError(), RuntimeError("secret URL")):
            git = Git()
            manifests = []

            def smoke(manifest):
                manifests.append(manifest)
                if manifest["source"] == SHA:
                    raise error

            with self.assertRaisesRegex(
                RuntimeError, "^Vydanie zlyhalo; predchádzajúce vydanie obnovené.$"
            ):
                release.promote(
                    git,
                    SHA,
                    DIGEST,
                    "kataster",
                    "https://mcp-kataster.aittorney.online",
                    lambda sha: None,
                    smoke,
                )
            self.assertEqual(manifests[-1], git.previous)
            second = git.calls[2]
            self.assertEqual(second[1], git.calls[1][1])
            self.assertEqual(second[2], git.calls[1][1])
            self.assertEqual(
                second[3],
                {
                    "compose.yaml": git.previous_compose,
                    ".dokploy-release.json": git.previous_manifest,
                },
            )
            self.assertEqual(git.trees[git.production], "current-workflows")
            self.assertEqual(git.calls[-1][2], False)

    def test_invalid_previous_compose_fails_before_mutation(self):
        for invalid in (
            lambda git: git.previous_compose.replace(git.previous["image"], DIGEST),
            lambda git: git.previous_compose.replace(git.previous["source"], SHA),
            lambda git: git.previous_compose + "    build: .\n",
            lambda git: git.previous_compose.replace("previous-data", "unexpected-data"),
        ):
            git = Git()
            git.previous_compose = invalid(git)
            with self.assertRaises(ValueError):
                release.promote(
                    git,
                    SHA,
                    DIGEST,
                    "kataster",
                    "https://mcp-kataster.aittorney.online",
                    lambda sha: self.fail("trigger"),
                    lambda manifest: self.fail("smoke"),
                )
            self.assertEqual(git.calls, [])

    def test_invalid_digest_fails_before_mutation(self):
        git = Git()
        with self.assertRaises(ValueError):
            release.promote(
                git,
                SHA,
                "image:latest",
                "kataster",
                "https://mcp-kataster.aittorney.online",
                lambda sha: None,
                lambda manifest: None,
            )
        self.assertEqual(git.calls, [])

    def test_second_main_check_skips_prepared_candidate(self):
        git = Git()
        original = git.commit

        def commit(*args):
            result = original(*args)
            git.stale = True
            return result

        git.commit = commit
        self.assertFalse(
            release.promote(
                git,
                SHA,
                DIGEST,
                "kataster",
                "https://mcp-kataster.aittorney.online",
                lambda sha: self.fail("trigger"),
                lambda manifest: self.fail("smoke"),
            )
        )
        self.assertEqual([call[0] for call in git.calls], ["commit"])

    def test_ambiguous_update_reconciles_candidate_parent_and_other_actor(self):
        for state in ("candidate", "parent", "other", "unreadable"):
            git = Git()
            original_update, original_ref = git.update, git.ref
            triggers = []

            def update(sha):
                if not any(call[0] == "update" for call in git.calls):
                    if state == "candidate":
                        original_update(sha)
                    elif state == "other":
                        git.production = "9" * 40
                    if state == "unreadable":
                        git.ref = lambda name: (_ for _ in ()).throw(
                            TimeoutError("secret")
                        )
                    raise TimeoutError("secret")
                original_update(sha)

            git.update = update
            with self.assertRaises(RuntimeError) as error:
                release.promote(
                    git,
                    SHA,
                    DIGEST,
                    "kataster",
                    "https://mcp-kataster.aittorney.online",
                    triggers.append,
                    lambda manifest: None,
                )
            self.assertNotIn("secret", str(error.exception))
            self.assertEqual(len(triggers), 1 if state == "candidate" else 0)
            if state == "candidate":
                self.assertEqual(
                    git.calls[2][1:3], (git.calls[1][1], git.calls[1][1])
                )
                self.assertEqual(
                    git.calls[2][3],
                    {
                        "compose.yaml": git.previous_compose,
                        ".dokploy-release.json": git.previous_manifest,
                    },
                )
            else:
                self.assertEqual([call[0] for call in git.calls], ["commit"])

    def test_wrong_authority_is_rejected(self):
        manifest = {
            "source": SHA,
            "service": "kataster",
            "origin": "https://mcp-kataster.aittorney.online",
        }
        for authorities in (
            ["https://wrong.example"],
            "https://auth.aittorney.online",
            ["https://auth.aittorney.online", "https://wrong.example"],
        ):
            responses = [
                (200, release.json.dumps({"revision": SHA}).encode()),
                (
                    200,
                    release.json.dumps(
                        {
                            "resource": manifest["origin"] + "/mcp",
                            "authorization_servers": authorities,
                        }
                    ).encode(),
                ),
            ]
            with patch.object(release, "request", side_effect=responses) as request:
                with self.assertRaisesRegex(RuntimeError, "Health alebo discovery"):
                    release.smoke(manifest, timeout=0)
                self.assertEqual(request.call_count, 2)

    def test_github_uses_tree_sha_linear_parent_and_non_force_ref(self):
        git = release.GitHub("synthetic/repo", "synthetic-token")
        calls = []

        def api(path, method="GET", data=None):
            calls.append((path, method, data))
            if path == "/git/commits/" + SHA:
                return {"tree": {"sha": "source-tree"}}
            return {"sha": "created-tree" if path == "/git/trees" else "created-commit"}

        git.api = api
        commit = git.commit(SHA, "parent", {"compose.yaml": "image"}, "message")
        git.update(commit)
        self.assertEqual(calls[1][2]["base_tree"], "source-tree")
        self.assertEqual(calls[2][2]["parents"], ["parent"])
        self.assertEqual(calls[3][2], {"sha": "created-commit", "force": False})

    def test_smoke_requires_exact_revision_and_separate_401(self):
        manifest = {
            "source": SHA,
            "service": "kataster",
            "origin": "https://mcp-kataster.aittorney.online",
        }
        responses = [
            (200, release.json.dumps({"revision": SHA}).encode()),
            (
                200,
                release.json.dumps(
                    {
                        "resource": manifest["origin"] + "/mcp",
                        "authorization_servers": ["https://auth.aittorney.online"],
                    }
                ).encode(),
            ),
            (401, b""),
        ]
        with patch.object(release, "request", side_effect=responses) as request:
            release.smoke(manifest, timeout=0)
            self.assertEqual(request.call_count, 3)
            self.assertEqual(request.call_args.kwargs["allowed"], (401,))
        with patch.object(
            release, "request", return_value=(200, b'{"revision":"old"}')
        ):
            with self.assertRaisesRegex(RuntimeError, "Health alebo discovery"):
                release.smoke(manifest, timeout=0)

    def test_request_declares_user_agent_and_preserves_override(self):
        for headers, expected in (
            (None, "SKALLARS-Release/1.0"),
            ({"User-Agent": "synthetic-caller/1.0"}, "synthetic-caller/1.0"),
        ):
            with patch.object(
                release.urllib.request, "urlopen", side_effect=OSError()
            ) as open_request:
                with self.assertRaises(RuntimeError):
                    release.request("https://example.com/endpoint", headers=headers)
                self.assertEqual(
                    open_request.call_args.args[0].get_header("User-agent"), expected
                )

    def test_sanitized_network_failure(self):
        with patch.object(
            release.urllib.request,
            "urlopen",
            side_effect=OSError("https://secret/token"),
        ):
            with self.assertRaisesRegex(RuntimeError, "^HTTP požiadavka zlyhala.$"):
                release.request("https://example.com/secret")


if __name__ == "__main__":
    unittest.main()
