"""bin/noc-upstream: latest-release lookup (GitHub Releases, npm), installed versions, version history, updates.
A fake GitHub + npm server and stub binaries stand in for the network and the apps; nothing real is touched."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin/noc-upstream"
mod = SourceFileLoader("noc_upstream", str(TOOL)).load_module()

HERMES_NEW = {"tag_name": "v0.21.6", "name": "Hermes Agent v0.21.6", "published_at": "2026-10-08T11:51:57Z"}
HERMES_DATED = {"tag_name": "v2026.9.24", "name": "Hermes Agent v0.21.5 (v2026.9.24)"}


class Upstream(BaseHTTPRequestHandler):
    routes = {}
    hits = []
    redirect_repos = {}

    def do_GET(self):  # noqa: N802
        type(self).hits.append(self.path)
        body = self.routes.get(self.path)
        if body is None:
            self.send_error(404)
            return
        if body == "ratelimit":
            self.send_error(403)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):  # noqa: N802
        type(self).hits.append("HEAD " + self.path)
        for repo, tag in self.redirect_repos.items():
            if self.path == f"/{repo}/releases/latest":
                self.send_response(302)
                self.send_header("Location", f"https://github.com/{repo}/releases/tag/{tag}")
                self.end_headers()
                return
        self.send_error(404)

    def log_message(self, *a):
        pass


def routes(hermes=HERMES_NEW, ollama="v0.40.1", appmanager="v3.2.0", npm=None):
    npm = npm if npm is not None else {"@openai%2Fcodex": "1.2.0", "@anthropic-ai%2Fclaude-code": "2.0.0",
                                       "opencode-ai": "0.9.0", "@vibe-kit%2Fgrok-cli": "0.1.0",
                                       "@google%2Fgemini-cli": "0.5.0", "@qwen-code%2Fqwen-code": "0.3.0"}
    r = {"/repos/NousResearch/hermes-agent/releases/latest": hermes,
         "/repos/ollama/ollama/releases/latest": {"tag_name": ollama, "name": ollama},
         "/repos/kem-a/AppManager/releases/latest": {"tag_name": appmanager, "name": appmanager}}
    for pkg, v in npm.items():
        r[f"/{pkg}/latest"] = {"version": v}
    return r


NPM_STUB = r'''#!/usr/bin/env bash
case "$1 $2" in
  "root -g") echo "$NPM_ROOT" ;;
  "install -g") echo "$3" >> "$NPM_LOG"
     [ -z "${NPM_FAIL:-}" ] || [[ "$3" != *"$NPM_FAIL"* ]] || exit 1
     pkg="${3%@*}"; ver="${3##*@}"; mkdir -p "$NPM_ROOT/$pkg"; echo "{\"version\":\"$ver\"}" > "$NPM_ROOT/$pkg/package.json" ;;
esac
'''


class Box(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        Upstream.routes, Upstream.hits, Upstream.redirect_repos = routes(), [], {}
        server = HTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_address[1]}"
        self.npm_root = self.tmp / "node_modules"
        self.npm_root.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.script("npm", NPM_STUB)
        self.script("hermes", 'echo "Hermes Agent v0.21.5+9141.ga28a5d0 (2026.9.24) · upstream a28a5d03"')
        self.script("ollama", 'echo "Warning: could not connect to a running Ollama instance" >&2; echo "Warning: client version is 0.32.5" >&2')
        self.script("hermes-updater", 'echo "updating hermes: $*"; echo "$*" >> "$UPDATER_LOG"')
        (self.tmp / "appmanager-VERSION").write_text("v3.2.0\n")
        self.install_npm("@openai/codex", "1.0.0")
        self.install_npm("opencode-ai", "0.9.0")
        self.env = {**os.environ, "NOC_UPSTREAM_GITHUB_API": self.url, "NOC_UPSTREAM_NPM_REGISTRY": self.url,
                    "NOC_UPSTREAM_GITHUB_WEB": self.url, "NOC_UPSTREAM_CACHE": str(self.tmp / "cache.json"),
                    "NOC_UPSTREAM_STATE": str(self.tmp / "state.json"), "NOC_UPSTREAM_HERMES": str(self.bin / "hermes"),
                    "NOC_UPSTREAM_OLLAMA": str(self.bin / "ollama"), "NOC_UPSTREAM_NPM": str(self.bin / "npm"),
                    "NOC_UPSTREAM_APPMANAGER_VERSION": str(self.tmp / "appmanager-VERSION"),
                    "NOC_UPSTREAM_HERMES_UPDATER": str(self.bin / "hermes-updater"), "NPM_ROOT": str(self.npm_root),
                    "NPM_LOG": str(self.tmp / "npm.log"), "UPDATER_LOG": str(self.tmp / "updater.log")}

    def script(self, name, body):
        p = self.bin / name
        p.write_text("#!/usr/bin/env bash\n" + body + "\n" if not body.startswith("#!") else body)
        p.chmod(0o755)

    def install_npm(self, pkg, version):
        d = self.npm_root / pkg
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps({"version": version}))

    def tool(self, *args, **env):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                              env={**self.env, **env})

    def listing(self, *args, **env):
        r = self.tool("list", "--json", *args, **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        return data, {a["id"]: a for a in data["apps"]}


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(mod.parse_version("Hermes Agent v0.21.5+9141.ga28a5d0 (2026.9.24) · upstream a28a5d03"), "0.21.5")
        self.assertEqual(mod.parse_version("ollama version is 0.32.5"), "0.32.5")
        self.assertEqual(mod.parse_version("v3.2.0\n"), "3.2.0")
        self.assertIsNone(mod.parse_version("no digits here"))
        self.assertIsNone(mod.parse_version(None))

    def test_ordering(self):
        newer = [("0.21.6", "0.21.5+9141"), ("0.40.1", "0.32.5"), ("1.10.0", "1.9.9"), ("2.0.0", "1.99.99"),
                 ("1.0.0", "1.0.0-rc.1"), ("1.0.1-rc.1", "1.0.0")]
        for a, b in newer:
            with self.subTest(a=a, b=b):
                self.assertTrue(mod.is_newer(a, b), (a, b))
                self.assertFalse(mod.is_newer(b, a), (b, a))
        for same in (("0.21.6", "0.21.6"), ("0.21.6", "0.21.6+120"), ("v1.2.3", "1.2.3")):
            with self.subTest(same=same):
                self.assertFalse(mod.is_newer(*same))
                self.assertFalse(mod.is_newer(*reversed(same)))


class ListTests(Box):
    def test_statuses_for_every_kind_of_app(self):
        data, apps = self.listing()
        self.assertEqual((apps["hermes"]["installed"], apps["hermes"]["latest"], apps["hermes"]["status"]),
                         ("0.21.5", "0.21.6", "outdated"))
        self.assertEqual((apps["ollama"]["installed"], apps["ollama"]["latest"], apps["ollama"]["status"]),
                         ("0.32.5", "0.40.1", "outdated"))
        self.assertEqual(apps["appmanager"]["status"], "current")
        self.assertEqual((apps["codex"]["installed"], apps["codex"]["latest"], apps["codex"]["status"]),
                         ("1.0.0", "1.2.0", "outdated"))
        self.assertEqual(apps["opencode"]["status"], "current")
        self.assertEqual(apps["claude"]["status"], "absent")          # installed on first use, nothing to update
        self.assertTrue(apps["hermes"]["critical"] and apps["ollama"]["critical"])
        self.assertEqual(apps["hermes"]["updater"], "user")
        self.assertEqual((apps["ollama"]["updater"], apps["ollama"]["module"]), ("root", "03b_ollama_update.sh"))
        self.assertEqual(data["updates"], 3)
        self.assertEqual(data["user_updates"], 2)
        self.assertTrue(data["online"])

    def test_hermes_dated_tags_take_the_version_from_the_release_name(self):
        Upstream.routes = routes(hermes=HERMES_DATED)
        _, apps = self.listing()
        self.assertEqual((apps["hermes"]["latest"], apps["hermes"]["latest_tag"]), ("0.21.5", "v2026.9.24"))
        self.assertEqual(apps["hermes"]["status"], "current")     # 0.21.5+9141 is not behind 0.21.5

    def test_the_github_redirect_is_the_fallback_when_the_api_is_rate_limited(self):
        Upstream.routes = routes()
        Upstream.routes["/repos/ollama/ollama/releases/latest"] = "ratelimit"
        Upstream.redirect_repos = {"ollama/ollama": "v0.41.0"}
        _, apps = self.listing()
        self.assertEqual((apps["ollama"]["latest"], apps["ollama"]["latest_tag"]), ("0.41.0", "v0.41.0"))

    def test_answers_are_cached_and_refresh_goes_back_to_the_source(self):
        self.listing()
        first = len(Upstream.hits)
        self.assertGreater(first, 0)
        self.listing()
        self.assertEqual(len(Upstream.hits), first)               # fresh cache: no requests
        self.listing("--refresh")
        self.assertEqual(len(Upstream.hits), first * 2)

    def test_offline_uses_the_cache_and_never_the_network(self):
        self.listing()
        hits = len(Upstream.hits)
        data, apps = self.listing("--offline")
        self.assertEqual(len(Upstream.hits), hits)
        self.assertEqual(apps["hermes"]["latest"], "0.21.6")
        self.assertTrue(data["checked_at"])

    def test_offline_without_a_cache_is_unknown_not_current(self):
        data, apps = self.listing("--offline")
        self.assertEqual(apps["hermes"]["status"], "unknown")
        self.assertIsNone(apps["hermes"]["latest"])
        self.assertEqual(data["updates"], 0)

    def test_an_unreachable_source_keeps_the_old_answer_marked_stale(self):
        self.listing()
        cache = json.loads((self.tmp / "cache.json").read_text())
        for entry in cache.values():
            entry["checked_at"] = "2020-01-01T00:00:00Z"
        (self.tmp / "cache.json").write_text(json.dumps(cache))
        Upstream.routes = {}
        data, apps = self.listing()
        self.assertFalse(data["online"])
        self.assertTrue(apps["hermes"]["stale"])
        self.assertEqual(apps["hermes"]["latest"], "0.21.6")

    def test_an_unreachable_source_and_no_cache_is_unknown(self):
        Upstream.routes = {}
        data, apps = self.listing()
        self.assertFalse(data["online"])
        self.assertEqual(apps["hermes"]["status"], "unknown")


class TrackingTests(Box):
    def test_first_sight_then_version_changes_are_recorded(self):
        _, apps = self.listing()
        self.assertTrue(apps["hermes"]["first_seen"])
        self.assertEqual(apps["hermes"]["updated_at"], "")
        self.script("hermes", 'echo "Hermes Agent v0.21.6 (2026.10.8)"')       # someone updated it by hand
        _, apps = self.listing()
        self.assertEqual((apps["hermes"]["installed"], apps["hermes"]["previous"]), ("0.21.6", "0.21.5"))
        self.assertTrue(apps["hermes"]["updated_at"])
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertEqual(state["hermes"]["version"], "0.21.6")

    def test_an_app_that_is_not_installed_is_not_recorded(self):
        self.listing()
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertNotIn("claude", state)


class UpdateTests(Box):
    def test_updates_hermes_and_installed_agents_to_the_exact_latest_version(self):
        r = self.tool("update")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.tmp / "updater.log").read_text().strip(), "update")      # noctraos-hermes update
        self.assertEqual((self.tmp / "npm.log").read_text().split(), ["@openai/codex@1.2.0"])   # not opencode (current), not claude (absent)
        self.assertIn("Codex is now 1.2.0", r.stdout)

    def test_root_apps_are_never_touched_by_the_user_level_update(self):
        self.tool("update")
        self.assertNotIn("ollama", (self.tmp / "npm.log").read_text())
        data, apps = self.listing("--offline")
        self.assertEqual(apps["ollama"]["status"], "outdated")      # reported, left to the privileged helper

    def test_only_limits_the_update(self):
        r = self.tool("update", "--only", "codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.tmp / "updater.log").exists())
        self.assertEqual((self.tmp / "npm.log").read_text().split(), ["@openai/codex@1.2.0"])
        self.assertNotEqual(self.tool("update", "--only", "nonsense").returncode, 0)

    def test_one_failure_does_not_stop_the_others_and_is_reported(self):
        r = self.tool("update", NPM_FAIL="codex")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Codex could not be updated", r.stdout)
        self.assertTrue((self.tmp / "updater.log").exists())         # Hermes still ran
        self.assertIn("1.0.0", r.stdout)

    def test_nothing_to_do_when_everything_is_current(self):
        self.script("hermes", 'echo "Hermes Agent v0.21.6"')
        self.install_npm("@openai/codex", "1.2.0")
        r = self.tool("update")
        self.assertEqual(r.returncode, 0)
        self.assertIn("up to date", r.stdout)
        self.assertFalse((self.tmp / "updater.log").exists())

    def test_no_connection_is_reported_not_called_up_to_date(self):
        Upstream.routes = {}
        r = self.tool("update")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Could not check", r.stdout)
        self.assertFalse((self.tmp / "updater.log").exists())


class LatestCommandTests(Box):
    def test_prints_version_or_tag(self):
        self.assertEqual(self.tool("latest", "hermes").stdout.strip(), "0.21.6")
        self.assertEqual(self.tool("latest", "hermes", "--tag").stdout.strip(), "v0.21.6")
        self.assertEqual(self.tool("latest", "codex").stdout.strip(), "1.2.0")
        self.assertNotEqual(self.tool("latest", "bogus").returncode, 0)

    def test_fails_cleanly_when_nothing_is_known(self):
        Upstream.routes = {}
        r = self.tool("latest", "hermes", "--tag")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
