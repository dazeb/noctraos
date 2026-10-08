"""install/03b_ollama_update.sh with a fake GitHub, a stub vendor installer and a stub ollama: it pins the vendor
installer to the newest release, does nothing when already current, and refuses to guess when it cannot tell."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "install/03b_ollama_update.sh"


class Github(BaseHTTPRequestHandler):
    body = {"tag_name": "v0.40.1", "name": "v0.40.1"}

    def do_GET(self):  # noqa: N802
        if self.path != "/repos/ollama/ollama/releases/latest" or self.body is None:
            self.send_error(404)
            return
        data = json.dumps(self.body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class OllamaModuleTests(unittest.TestCase):
    def setUp(self):
        Github.body = {"tag_name": "v0.40.1", "name": "v0.40.1"}
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        server = HTTPServer(("127.0.0.1", 0), Github)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (self.tmp / "ollama-version").write_text("0.32.5\n")
        stubs = {
            "ollama": '#!/bin/sh\necho "ollama version is $(cat "$STATE")"\n',
            "sudo": '#!/bin/sh\nexec "$@"\n',
            # the vendor installer arrives as a file: record the version it was pinned to and "install" it
            "curl": '#!/bin/sh\nout=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done\n'
                    'printf \'#!/bin/sh\\necho "$OLLAMA_VERSION" >> "$INSTALL_LOG"\\n[ -n "$INSTALL_BREAKS" ] || echo "$OLLAMA_VERSION" > "$STATE"\\n\' > "$out"\n',
        }
        for name, body in stubs.items():
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "REPO_ROOT": str(ROOT),
                    "TARGET_USER": "t", "TARGET_UID": "1000", "TARGET_HOME": str(self.tmp),
                    "STATE": str(self.tmp / "ollama-version"), "INSTALL_LOG": str(self.tmp / "install.log"),
                    "INSTALL_BREAKS": "", "NOC_UPSTREAM_GITHUB_API": f"http://127.0.0.1:{server.server_address[1]}",
                    "NOC_UPSTREAM_GITHUB_WEB": "http://127.0.0.1:9", "NOC_UPSTREAM_OLLAMA": str(bin_dir / "ollama"),
                    "NOC_UPSTREAM_CACHE": str(self.tmp / "cache.json"), "NOC_UPSTREAM_STATE": str(self.tmp / "state.json"),
                    "NOC_UPSTREAM_NPM": "/nonexistent", "NOC_UPSTREAM_HERMES": "/nonexistent",
                    "NOC_UPSTREAM_APPMANAGER_VERSION": "/nonexistent"}

    def run_module(self, **env):
        return subprocess.run(["bash", str(MODULE)], capture_output=True, text=True, env={**self.env, **env})

    def installs(self):
        log = self.tmp / "install.log"
        return log.read_text().split() if log.exists() else []

    def test_an_old_ollama_is_updated_with_the_installer_pinned_to_the_newest_release(self):
        r = self.run_module()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["0.40.1"])
        self.assertIn("0.32.5 -> 0.40.1", r.stdout)
        self.assertIn("Ollama is now 0.40.1", r.stdout)

    def test_a_current_ollama_is_left_alone(self):
        (self.tmp / "ollama-version").write_text("0.40.1\n")
        r = self.run_module()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), [])
        self.assertIn("already the latest", r.stdout)

    def test_when_the_release_cannot_be_read_nothing_is_changed(self):
        Github.body = None
        r = self.run_module()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.installs(), [])
        self.assertIn("cannot tell", r.stderr)

    def test_an_installer_that_does_not_take_is_an_error(self):
        r = self.run_module(INSTALL_BREAKS="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected 0.40.1", r.stderr)

    def test_a_missing_ollama_is_not_installed_by_this_module(self):
        r = self.run_module(PATH="/usr/bin:/bin")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.installs(), [])


if __name__ == "__main__":
    unittest.main()
