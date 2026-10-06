"""Exercise the machine-readable side of `noc` and `noctraos-hermes`.

Nothing here touches the real system: Ollama is a throwaway local HTTP server, HOME and
XDG_CONFIG_HOME are temp dirs, and the commands an update would run (sudo, apt-get, mise) are
stubs on PATH.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOC = ROOT / "bin/noc"
HERMES = ROOT / "bin/noctraos-hermes"

TAGS = {"models": [
    {"name": "qwen2.5-coder:7b", "size": 4_700_000_000, "modified_at": "2026-10-01T10:00:00Z"},
    {"name": "nomic-embed-text:latest", "size": 274_000_000, "modified_at": "2026-10-01T10:00:00Z"},
]}


class FakeOllama(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = {"/api/tags": TAGS, "/api/version": {"version": "0.0.test"}}.get(self.path)
        if body is None:
            self.send_error(404)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):  # noqa: N802  (the online check uses curl -I)
        self.send_response(200 if self.path in ("/api/tags", "/api/version") else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


class Env:
    """A temp HOME, optional fake Ollama and stub commands, and a way to run noc in them."""

    def __init__(self, test, ollama=True):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.bin = Path(self.tmp.name) / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.url = "http://127.0.0.1:9"  # discard port: nothing listens, so Ollama is "down"
        if ollama:
            server = HTTPServer(("127.0.0.1", 0), FakeOllama)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            test.addCleanup(server.server_close)
            test.addCleanup(server.shutdown)
            self.url = f"http://127.0.0.1:{server.server_address[1]}"

    def stub(self, name, script):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + script + "\n")
        path.chmod(0o755)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k != "NOCTRAOS_MODEL"}
        env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                   NOC_OLLAMA_URL=self.url, PATH=f"{self.bin}:{os.environ['PATH']}")
        env.update(extra)
        return env

    def run(self, script, *args, check=False, **extra):
        return subprocess.run([str(script), *args], capture_output=True, text=True,
                              env=self.env(**extra), check=check)

    def noc(self, *args, **extra):
        return self.run(NOC, *args, **extra)

    @property
    def model_file(self):
        return self.home / ".config/noctraos/model"


def bash_fn(expr):
    return subprocess.run(["bash", "-c", f'source "{NOC}"; {expr}'],
                          capture_output=True, text=True, check=True).stdout.strip()


class SuggestionTests(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(bash_fn("preset_fit 6 16 8"), "gpu")
        self.assertEqual(bash_fn("preset_fit 6 16 4"), "cpu")      # 16 GB RAM holds a 6 GB model
        self.assertEqual(bash_fn("preset_fit 12 16 0"), "no")      # 14B needs 24 GB RAM on the CPU
        self.assertEqual(bash_fn("preset_fit 12 32 0"), "cpu")

    def test_recommend(self):
        cases = [
            ((64, 12), "qwen2.5-coder:14b"),   # 12 GB of VRAM holds the 14B
            ((32, 8), "qwen2.5-coder:7b"),     # 8 GB VRAM: the biggest that fits is the 7B class
            ((32, 0), "qwen2.5-coder:7b"),     # CPU only, but plenty of RAM: stay 7B-class
            ((8, 0), "phi4-mini"),             # 8 GB RAM: 4 GB model is the biggest that fits
            ((4, 0), "llama3.2:3b"),           # nothing fits half the RAM: fall back to the smallest preset
            ((2, 0), "llama3.2:3b"),
        ]
        for (ram, vram), want in cases:
            with self.subTest(ram=ram, vram=vram):
                self.assertEqual(bash_fn(f"recommend {ram} {vram}"), want)

    def test_presets_json(self):
        out = subprocess.run([str(NOC), "models", "presets", "--json"], capture_output=True, text=True,
                             check=True, env={**os.environ, "NOC_RAM_GB": "32", "NOC_VRAM_GB": "8"}).stdout
        data = json.loads(out)
        self.assertEqual((data["ram_gb"], data["vram_gb"]), (32, 8))
        self.assertEqual([p["name"] for p in data["presets"] if p["recommended"]], ["qwen2.5-coder:7b"])
        for p in data["presets"]:
            self.assertEqual(set(p), {"name", "need_gb", "note", "fit", "recommended"})
            self.assertIn(p["fit"], {"gpu", "cpu", "no"})


class ModelTests(unittest.TestCase):
    def test_list_json(self):
        data = json.loads(Env(self).noc("models", "list", "--json").stdout)
        self.assertTrue(data["ollama"])
        self.assertEqual(data["default"], "qwen2.5-coder:7b")
        self.assertEqual({m["name"]: m["is_default"] for m in data["models"]},
                         {"qwen2.5-coder:7b": True, "nomic-embed-text:latest": False})
        self.assertEqual(set(data["models"][0]), {"name", "size", "modified", "is_default"})

    def test_list_json_ollama_down_is_a_state_not_an_error(self):
        result = Env(self, ollama=False).noc("models", "list", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"ollama": False, "default": "qwen2.5-coder:7b", "models": []})

    def test_default_round_trip(self):
        e = Env(self)
        self.assertEqual(e.noc("models", "default").stdout.strip(), "qwen2.5-coder:7b")
        self.assertEqual(e.noc("models", "default", "nomic-embed-text").returncode, 0)  # :latest matches
        self.assertEqual(e.model_file.read_text(), "nomic-embed-text\n")
        self.assertEqual(e.noc("models", "default").stdout.strip(), "nomic-embed-text")
        listed = json.loads(e.noc("models", "list", "--json").stdout)
        self.assertEqual([m["name"] for m in listed["models"] if m["is_default"]], ["nomic-embed-text:latest"])

    def test_env_beats_file(self):
        e = Env(self)
        e.model_file.parent.mkdir(parents=True)
        e.model_file.write_text("from-file\n")
        self.assertEqual(e.noc("models", "default").stdout.strip(), "from-file")
        self.assertEqual(e.noc("models", "default", NOCTRAOS_MODEL="from-env").stdout.strip(), "from-env")

    def test_default_rejects_uninstalled_and_bad_names(self):
        e = Env(self)
        for name in ("llama3.2:3b", "bad name", "a;b", "../x", "-rf"):
            with self.subTest(name=name):
                self.assertNotEqual(e.noc("models", "default", name).returncode, 0)
        self.assertFalse(e.model_file.exists())

    def test_default_saves_when_ollama_is_down(self):
        e = Env(self, ollama=False)
        self.assertEqual(e.noc("models", "default", "llama3.2:3b").returncode, 0)
        self.assertEqual(e.model_file.read_text(), "llama3.2:3b\n")

    def test_default_rewrites_only_our_continue_lines(self):
        e = Env(self)
        cfg = e.home / ".continue/config.yaml"
        cfg.parent.mkdir()
        cfg.write_text((ROOT / "configs/vscode/continue_config.yaml").read_text() + "# keep: model: me\n")
        e.noc("models", "default", "nomic-embed-text")
        text = cfg.read_text()
        self.assertEqual(text.count("    model: nomic-embed-text\n"), 2)
        self.assertNotIn("model: qwen2.5-coder", text)
        self.assertIn("# keep: model: me", text)


class DoctorStatusTests(unittest.TestCase):
    def test_doctor_json_shape(self):
        e = Env(self)
        e.stub("code", "echo 1.0.0")
        result = e.noc("doctor", "--json")
        rows = json.loads(result.stdout)
        self.assertGreater(len(rows), 5)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "check ids must be unique")
        for r in rows:
            self.assertEqual(set(r), {"id", "label", "status", "detail", "fix"})
            self.assertIn(r["status"], {"ok", "warn", "fail", "info"})
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id["ollama"]["status"], "ok")
        self.assertIn(by_id["appmanager"]["fix"], (None, "module:04d_appmanager.sh"))

    def test_doctor_json_gpu_detail_has_no_status_markers(self):
        e = Env(self)
        e.stub("noc-gpu", "printf '  \\033[32mOK\\033[0m  GPU: Test Card\\n  \\033[33m..\\033[0m  AMD GPU uses Vulkan only (no ROCm)\\n'")
        row = {r["id"]: r for r in json.loads(e.noc("doctor", "--json").stdout)}["gpu"]
        self.assertEqual((row["status"], row["detail"]), ("ok", "GPU: Test Card; AMD GPU uses Vulkan only (no ROCm)"))

    def test_doctor_json_ollama_down(self):
        rows = json.loads(Env(self, ollama=False).noc("doctor", "--json").stdout)
        self.assertEqual({r["id"]: r["status"] for r in rows}["ollama"], "fail")

    def test_doctor_text_is_still_text(self):
        out = Env(self).noc("doctor").stdout
        self.assertTrue(out.startswith("NoctraOS doctor\n"))
        self.assertTrue(out.rstrip().endswith("done."))

    def test_status_json_shape(self):
        e = Env(self)
        e.stub("apt-get", "printf 'Inst a\\nInst b\\nConf a\\n'")
        e.stub("flatpak", "exit 1")  # remote unreachable: unknown, never a false zero
        data = json.loads(e.noc("status", "--json").stdout)
        self.assertEqual(data["version"], subprocess.run([str(NOC), "--version"], capture_output=True,
                                                         text=True).stdout.split()[1])
        self.assertEqual(data["updates"]["apt"], 2)
        self.assertIsNone(data["updates"]["flatpak"])
        self.assertTrue(data["ollama"]["running"])
        self.assertEqual(data["ollama"]["models"], 2)
        self.assertEqual(data["ollama"]["default_model"], "qwen2.5-coder:7b")
        self.assertGreaterEqual(data["disk"]["root_total_bytes"], data["disk"]["root_free_bytes"])
        self.assertIn("hermes", data)

    def test_status_json_ollama_down(self):
        data = json.loads(Env(self, ollama=False).noc("status", "--json").stdout)
        self.assertFalse(data["ollama"]["running"])
        self.assertEqual(data["ollama"]["models"], 0)


class UpdatesCommandTests(unittest.TestCase):
    def run_updates(self, e):
        return json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version").stdout)

    def test_shape_and_apt_download_size(self):
        e = Env(self)
        e.stub("apt-get", 'case "$*" in *print-uris*) printf "\'http://x/a.deb\' a.deb 1500 MD5Sum:aa\\n\'http://x/b.deb\' b.deb 9000000 MD5Sum:bb\\n";; *) printf "Inst a\\nInst b\\nConf a\\n";; esac')
        e.stub("flatpak", "printf 'org.a\\norg.b\\n'")
        e.stub("mise", 'echo \'{"node":{},"go":{}}\'')
        data = self.run_updates(e)
        self.assertEqual(data["online"], True)
        self.assertEqual(data["apt"], {"count": 2, "download_bytes": 9_001_500})
        self.assertEqual(data["flatpak"], {"count": 2})
        self.assertEqual(data["mise"], {"count": 2})
        self.assertEqual(data["models"], {"installed": 2})
        self.assertIsInstance(data["reboot_required"], bool)

    def test_offline_and_unknowns_are_unknown_not_zero(self):
        e = Env(self, ollama=False)
        e.stub("apt-get", "exit 100")
        e.stub("flatpak", "exit 1")
        e.stub("mise", "exit 1")
        data = self.run_updates(e)
        self.assertEqual(data["online"], False)
        self.assertEqual(data["apt"]["count"], None)
        self.assertEqual(data["flatpak"]["count"], None)
        self.assertEqual(data["mise"]["count"], None)

    def test_apt_size_parser_sums_the_size_column(self):
        lines = ("'http://a/x_1.deb' x_1.deb 94556 MD5Sum:7454\n"
                 "'https://b/y_2.deb' y_2.deb 7776 MD5Sum:6666\n")
        out = subprocess.run(["bash", "-c", f'source "{NOC}"; apt_download_bytes'], input=lines,
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "102332")
        for empty in ("", "NOTE: nothing\n"):
            out = subprocess.run(["bash", "-c", f'source "{NOC}"; apt_download_bytes'], input=empty,
                                 capture_output=True, text=True).stdout.strip()
            self.assertEqual(out, "0")


class UpdateTests(unittest.TestCase):
    def events(self, e, *args):
        result = e.noc("update", "--json", *args)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        return result, lines

    def test_json_event_stream(self):
        e = Env(self)
        e.stub("mise", "echo upgrading node; printf 'progress\\r50%%\\r'; echo done")
        result, ev = self.events(e, "--only", "mise")
        self.assertEqual(result.returncode, 0)
        self.assertEqual([x["event"] for x in ev if x["event"] != "log"], ["step", "step_done", "done"])
        step = ev[0]
        self.assertEqual((step["id"], step["index"], step["total"], step["percent"]), ("mise", 1, 1, 0))
        logs = [x["line"] for x in ev if x["event"] == "log"]
        self.assertEqual(logs, ["upgrading node", "progress", "50%", "done"])  # \r splits into lines
        self.assertEqual(ev[-1]["ok"], True)
        self.assertIsInstance(ev[-1]["reboot_required"], bool)

    def test_percent_advances_across_steps(self):
        e = Env(self)
        e.stub("mise", "true")
        _, ev = self.events(e, "--only", "mise,models")
        steps = [x for x in ev if x["event"] == "step"]
        self.assertEqual([(s["id"], s["percent"], s["total"]) for s in steps], [("mise", 0, 2), ("models", 50, 2)])

    def test_failed_step_is_reported(self):
        e = Env(self)
        e.stub("sudo", 'if [ "$1" = -n ]; then shift; fi; exec "$@"')
        e.stub("apt-get", "echo 'E: no network'; exit 100")
        result, ev = self.events(e, "--only", "apt")
        self.assertEqual(result.returncode, 1)
        self.assertEqual([x["ok"] for x in ev if x["event"] == "step_done"], [False])
        self.assertEqual(ev[-1], {"event": "done", "ok": False, "reboot_required": ev[-1]["reboot_required"]})
        self.assertIn("E: no network", [x["line"] for x in ev if x["event"] == "log"])

    def test_apt_refresh_failures_fail_the_step(self):
        e = Env(self)
        e.stub("sudo", 'if [ "$1" = -n ]; then shift; fi; exec "$@"')
        log = e.home / "apt-args"
        e.stub("apt-get", f'echo "$*" >> "{log}"')
        self.events(e, "--only", "apt")
        self.assertIn("update --error-on=any", log.read_text().splitlines()[0])

    def test_unknown_step_is_refused(self):
        result = Env(self).noc("update", "--only", "reboot")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown step", result.stderr)


class HermesModeTests(unittest.TestCase):
    def setUp(self):
        self.e = Env(self, ollama=False)
        self.hermes_home = self.e.home / ".hermes"
        self.hermes_home.mkdir()
        self.calls = self.e.home / "hermes-calls"
        (self.e.home / ".local/bin").mkdir(parents=True)
        stub = self.e.home / ".local/bin/hermes"
        stub.write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\n')
        stub.chmod(0o755)

    def hermes(self, *args):
        return self.e.run(HERMES, *args, HERMES_HOME=str(self.hermes_home))

    def config(self, text):
        (self.hermes_home / "config.yaml").write_text(text)

    def test_mode(self):
        for text, want in [
            ("", "cloud"),
            ("model:\n  provider: auto\n", "cloud"),
            ("model:\n  provider: custom\n  base_url: http://127.0.0.1:11434/v1\n  default: x\n", "local"),
            ("model:\n  provider: custom\n  base_url: https://example.com/v1\n", "other"),
            ("model:\n  provider: openrouter\n", "other"),
        ]:
            with self.subTest(config=text):
                self.config(text)
                self.assertEqual(self.hermes("mode").stdout.strip(), want)

    def test_status_reports_mode(self):
        self.config("")
        self.assertIn("mode:    cloud\n", self.hermes("status").stdout)

    def test_cloud_undoes_local(self):
        self.config("model:\n  provider: custom\n  base_url: http://127.0.0.1:11434/v1\n  default: x\n")
        result = self.hermes("cloud")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.calls.read_text().splitlines(),
                         ["config unset model.base_url", "config unset model.default", "config set model.provider auto"])

    def test_local_no_launch_sets_the_provider_and_never_opens_the_app(self):
        server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.config("")
        result = self.e.run(HERMES, "local", "--no-launch", HERMES_HOME=str(self.hermes_home),
                            NOCTRAOS_OLLAMA_API=f"http://127.0.0.1:{server.server_address[1]}",
                            NOCTRAOS_MODEL="qwen2.5-coder:7b")
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls[0], "config set model.provider custom")
        self.assertTrue(all(c.startswith("config set model.") for c in calls), calls)   # no `desktop`, no launch

    def test_local_refuses_when_the_model_is_not_ready(self):
        self.config("")
        result = self.e.run(HERMES, "local", "--no-launch", HERMES_HOME=str(self.hermes_home),
                            NOCTRAOS_OLLAMA_API="http://127.0.0.1:9")     # nothing listens: model "not ready"
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.calls.exists())

    def test_cloud_never_touches_a_users_own_provider(self):
        self.config("model:\n  provider: openrouter\n")
        self.assertEqual(self.hermes("cloud").returncode, 1)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
