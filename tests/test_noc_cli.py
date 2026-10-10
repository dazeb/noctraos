"""Exercise the machine-readable side of `noc` and `noctraos-hermes`.

Nothing here touches the real system: Ollama is a throwaway local HTTP server, HOME and
XDG_CONFIG_HOME are temp dirs, and the commands an update would run (sudo, apt-get, mise) are
stubs on PATH.
"""
import gzip
import json
import os
import shutil
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


# nomic-embed-text is absent on purpose: a model Ollama cannot describe lists as "unknown" ([]).
SHOW_CAPABILITIES = {"qwen2.5-coder:7b": ["completion", "tools", "insert"]}


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

    def do_POST(self):  # noqa: N802  (/api/show: what a model can do)
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        caps = SHOW_CAPABILITIES.get(request.get("model"))
        if self.path != "/api/show" or caps is None:
            self.send_error(404)
            return
        data = json.dumps({"capabilities": caps}).encode()
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
                   NOC_OLLAMA_URL=self.url, PATH=f"{self.bin}:{os.environ['PATH']}", NOC_TEST_HOOKS="1")
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


class TestHookTests(unittest.TestCase):
    """Root never honours the NOC_* stand-in variables (so the privileged helper and `sudo noc update` always run the installed,
    root-owned copies), unless a test says so with NOC_TEST_HOOKS. `id` is faked here so this runs as any user."""

    def resolved(self, uid, **env):
        script = f'id() {{ echo {uid}; }}; source "{NOC}"; echo "$SELFUPDATE $UPSTREAM $ACCOUNTS"'
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                             env={**{k: v for k, v in os.environ.items() if not k.startswith("NOC_")},
                                  "NOC_SELFUPDATE": "/x/su", "NOC_UPSTREAM": "/x/up", "NOC_ACCOUNTS": "/x/ac", **env})
        return out.stdout.strip().split()

    def test_a_normal_user_can_point_noc_at_stand_ins(self):
        self.assertEqual(self.resolved(1000), ["/x/su", "/x/up", "/x/ac"])

    def test_root_ignores_them(self):
        self.assertEqual(self.resolved(0), ["/usr/local/libexec/noctraos/noc-selfupdate", "/usr/local/bin/noc-upstream",
                                            "/usr/local/bin/noc-accounts"])

    def test_root_honours_them_only_when_a_test_asks(self):
        self.assertEqual(self.resolved(0, NOC_TEST_HOOKS="1"), ["/x/su", "/x/up", "/x/ac"])


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
        self.assertEqual(set(data["models"][0]), {"name", "size", "modified", "is_default", "capabilities"})

    def test_list_json_capabilities(self):
        data = json.loads(Env(self).noc("models", "list", "--json").stdout)
        self.assertEqual({m["name"]: m["capabilities"] for m in data["models"]},
                         {"qwen2.5-coder:7b": ["completion", "tools", "insert"], "nomic-embed-text:latest": []})

    def test_list_json_ollama_down_is_a_state_not_an_error(self):
        e = Env(self, ollama=False)
        e.stub("systemctl", "echo not-found; exit 4")                 # no Ollama service on this machine
        result = e.noc("models", "list", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout),
                         {"ollama": False, "autostart": None, "default": "qwen2.5-coder:7b", "models": []})

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

    def update_row(self, status_json=None):
        e = Env(self)
        extra = {}
        if status_json is not None:
            e.stub("selfupdate", f"echo '{status_json}'")
            extra["NOC_SELFUPDATE"] = str(e.bin / "selfupdate")
        return {r["id"]: r for r in json.loads(e.noc("doctor", "--json", **extra).stdout)}["noctraos-update"]

    def test_doctor_noctraos_update_rows(self):
        self.assertEqual(self.update_row()["status"], "info")   # no updater on this system yet
        ok = self.update_row('{"signing_key": true, "failed_migrations": [], "serial": 3, "channel": "stable"}')
        self.assertEqual((ok["status"], ok["detail"]), ("ok", "update 3, channel stable"))
        stuck = self.update_row('{"signing_key": true, "failed_migrations": ["0002_x.sh"], "serial": 3, "channel": "stable"}')
        self.assertEqual(stuck["status"], "warn")
        self.assertIn("0002_x.sh", stuck["detail"])
        self.assertEqual(self.update_row('{"signing_key": false, "failed_migrations": [], "serial": 0, "channel": "stable"}')["status"], "warn")

    def flatpak_row(self, version, changelog=None):
        e = Env(self)
        e.stub("flatpak", f'[ "$1" = "--version" ] && echo "Flatpak {version}"')
        log = e.home / "changelog.Debian.gz"
        with gzip.open(log, "wt") as f:
            f.write(changelog or "flatpak (1.14.6-1) noble; urgency=medium\n  * Routine update\n")
        out = e.noc("doctor", "--json", NOC_FLATPAK_CHANGELOG=str(log)).stdout
        return {r["id"]: r for r in json.loads(out)}["flatpak-security"]

    def test_doctor_flatpak_at_or_above_the_fixed_version(self):
        for version in ("1.18.4", "1.18.10", "1.19.2", "1.20.0"):
            with self.subTest(version=version):
                self.assertEqual(self.flatpak_row(version)["status"], "ok")

    def test_doctor_flatpak_old_version_warns(self):
        for version in ("1.14.6", "1.18.3", "1.9.0"):
            with self.subTest(version=version):
                row = self.flatpak_row(version)
                self.assertEqual(row["status"], "warn")
                self.assertIn("1.18.4", row["detail"])

    def test_doctor_flatpak_old_version_with_backported_fix_is_ok(self):
        row = self.flatpak_row("1.14.6", "flatpak (1.14.6-1ubuntu0.1) noble-security\n  * SECURITY: CVE-2026-97024\n")
        self.assertEqual((row["status"], row["detail"]), ("ok", "1.14.6 (patched by the distribution)"))

    def test_doctor_json_gpu_detail_has_no_status_markers(self):
        e = Env(self)
        e.stub("noc-gpu", "printf '  \\033[32mOK\\033[0m  GPU: Test Card\\n  \\033[33m..\\033[0m  AMD GPU uses Vulkan only (no ROCm)\\n'")
        row = {r["id"]: r for r in json.loads(e.noc("doctor", "--json").stdout)}["gpu"]
        self.assertEqual((row["status"], row["detail"]), ("ok", "GPU: Test Card; AMD GPU uses Vulkan only (no ROCm)"))

    DISK_GROWABLE = ('{"supported": true, "can_grow": true, "expandable_bytes": 35433480192, "disk_bytes": 68719476736, '
                     '"partition_bytes": 33285996544, "reason": ""}')

    def disk_env(self, doc):
        e = Env(self)
        e.stub("noc-disk", f"echo '{doc}'")
        return e, {"NOC_DISKTOOL": str(e.bin / "noc-disk")}

    def test_doctor_warns_when_the_disk_is_bigger_than_the_system_uses_and_offers_no_one_click_fix(self):
        e, extra = self.disk_env(self.DISK_GROWABLE)
        row = {r["id"]: r for r in json.loads(e.noc("doctor", "--json", **extra).stdout)}["disk-size"]
        self.assertEqual(row["status"], "warn")
        self.assertIn("33.0 GiB of the disk is not used yet", row["detail"])
        self.assertIn("Hardware", row["detail"])
        self.assertIsNone(row["fix"])

    def test_doctor_has_no_disk_size_row_when_there_is_nothing_to_grow(self):
        e, extra = self.disk_env('{"supported": true, "can_grow": false, "expandable_bytes": 0}')
        ids = [r["id"] for r in json.loads(e.noc("doctor", "--json", **extra).stdout)]
        self.assertNotIn("disk-size", ids)
        ids = [r["id"] for r in json.loads(Env(self).noc("doctor", "--json", NOC_DISKTOOL="/nonexistent").stdout)]
        self.assertNotIn("disk-size", ids)

    def test_status_json_carries_the_expandable_disk_space(self):
        e, extra = self.disk_env(self.DISK_GROWABLE)
        disk = json.loads(e.noc("status", **extra).stdout)["disk"]
        self.assertEqual((disk["can_grow"], disk["expandable_bytes"]), (True, 35433480192))
        self.assertEqual((disk["disk_bytes"], disk["partition_bytes"]), (68719476736, 33285996544))
        self.assertIs(disk["needs_fdisk"], False)               # absent in the stub's answer: never guessed as true
        self.assertIn("root_free_bytes", disk)

    def test_status_json_without_the_tool_keeps_the_old_disk_shape(self):
        disk = json.loads(Env(self).noc("status", NOC_DISKTOOL="/nonexistent").stdout)["disk"]
        self.assertEqual(set(disk), {"root_free_bytes", "root_total_bytes"})

    def test_noc_disk_hands_over_to_the_tool(self):
        e, extra = self.disk_env("ignored")
        e.stub("noc-disk", 'echo "args: $*"')
        self.assertEqual(e.noc("disk", "grow", "--dry-run", **extra).stdout.strip(), "args: grow --dry-run")

    def test_doctor_json_ollama_down(self):
        e = Env(self, ollama=False)
        e.stub("ollama", "true")  # installed, but its API does not answer
        e.stub("systemctl", "echo enabled")                           # and set to start with the computer: that is a failure
        rows = json.loads(e.noc("doctor", "--json").stdout)
        self.assertEqual({r["id"]: r["status"] for r in rows}["ollama"], "fail")

    def doctor_languages(self, mise_script):
        e = Env(self, ollama=False)
        e.stub("mise", mise_script)
        return {r["id"]: r for r in json.loads(e.noc("doctor", "--json").stdout)}

    def test_doctor_does_not_fail_a_machine_that_has_node_but_no_python_or_go(self):
        # NoctraOS installs Node (the agent launchers and the Hermes build need it) and leaves other languages to the person.
        rows = self.doctor_languages('case "$*" in --version) echo 2026.1.0 ;; "exec -- node --version") echo v24.1.0 ;; esac')
        self.assertEqual(rows["node"]["status"], "ok")
        for language in ("python", "go"):
            self.assertEqual(rows[language]["status"], "info", language)
            self.assertIn("mise use -g", rows[language]["detail"])

    def test_doctor_still_fails_a_machine_without_node_and_shows_languages_that_are_there(self):
        rows = self.doctor_languages('case "$*" in --version) echo 2026.1.0 ;; "exec -- python --version") echo Python 3.12.3 ;; '
                                     '"exec -- go version") echo go version go1.27.1 linux/amd64 ;; esac')
        self.assertEqual(rows["node"]["status"], "fail")
        self.assertEqual((rows["python"]["status"], rows["python"]["detail"]), ("ok", "Python 3.12.3"))
        self.assertEqual((rows["go"]["status"], rows["go"]["detail"]), ("ok", "go1.27.1"))

    @unittest.skipIf(shutil.which("ollama"), "the test needs a machine without Ollama")
    def test_doctor_json_ollama_not_set_up_is_information_not_a_failure(self):
        rows = json.loads(Env(self, ollama=False).noc("doctor", "--json").stdout)
        row = {r["id"]: r for r in rows}["ollama"]
        self.assertEqual(row["status"], "info")
        self.assertIn("noc llm setup", row["detail"])

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

    def test_status_json_says_whether_ollama_is_installed(self):
        # An answering API implies the engine is there, even when its binary is not on this PATH.
        self.assertTrue(json.loads(Env(self).noc("status", "--json").stdout)["ollama"]["installed"])
        silent = Env(self, ollama=False)
        silent.stub("ollama", "true")                       # installed, but its API does not answer
        data = json.loads(silent.noc("status", "--json").stdout)["ollama"]
        self.assertEqual((data["installed"], data["running"]), (True, False))

    @unittest.skipIf(shutil.which("ollama"), "the test needs a machine without Ollama")
    def test_status_json_never_set_up_is_not_installed(self):
        data = json.loads(Env(self, ollama=False).noc("status", "--json").stdout)["ollama"]
        self.assertEqual((data["installed"], data["running"]), (False, False))


class LocalLlmTests(unittest.TestCase):
    """`noc llm`: the optional local AI step. Nothing here downloads a model; the installer is a stand-in."""

    def test_setup_runs_only_the_optional_module_from_the_installer(self):
        e = Env(self)
        log = Path(e.tmp.name) / "installer-args"
        stand_in = Path(e.tmp.name) / "install.sh"
        stand_in.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\n')
        result = e.noc("llm", "setup", NOC_INSTALLER=str(stand_in))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text().split(), ["--only", "optional/local_llm.sh"])

    def test_setup_refuses_when_the_installer_snapshot_is_missing(self):
        result = Env(self).noc("llm", "setup", NOC_INSTALLER="/nonexistent/install.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not in place", result.stdout)

    def test_fit_says_how_to_get_llmfit_when_it_is_missing(self):
        e = Env(self)
        # A real LLMFIT in /usr/local/bin (or anywhere on the caller's PATH) would be found, so use a bare PATH.
        result = e.noc("llm", "fit", HOME=str(e.home), PATH=f"{e.bin}:/usr/bin:/bin")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("noc llm setup", result.stdout)

    def test_fit_runs_llmfit_with_its_arguments(self):
        e = Env(self)
        e.stub("llmfit", 'echo "llmfit $*"')
        self.assertEqual(e.noc("llm", "fit", "recommend", "--json").stdout.strip(), "llmfit recommend --json")

    def test_usage_for_anything_else(self):
        result = Env(self).noc("llm")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage: noc llm", result.stdout)

    def test_models_pull_and_rm_name_the_setup_step_when_nothing_is_installed(self):
        for verb in ("pull", "rm"):
            with self.subTest(verb=verb):
                e = Env(self, ollama=False)
                result = e.noc("models", verb, "llama3.2:3b", PATH=str(e.bin) + ":/usr/bin:/bin")
                self.assertEqual(result.returncode, 1)
                self.assertIn("noc llm setup", result.stdout)

    def test_models_list_names_the_setup_step_when_nothing_is_installed(self):
        e = Env(self, ollama=False)
        result = e.noc("models", "list", PATH=str(e.bin) + ":/usr/bin:/bin")
        self.assertEqual(result.returncode, 1)
        self.assertIn("noc llm setup", result.stdout)
        self.assertNotIn("command not found", result.stdout + result.stderr)

    def test_update_has_no_models_step_failure_without_local_ai(self):
        e = Env(self, ollama=False)
        result = e.noc("update", "--only", "models", PATH=str(e.bin) + ":/usr/bin:/bin")
        self.assertNotIn("skipped model refresh", result.stdout + result.stderr)


class SkipCommandTests(unittest.TestCase):
    """`noc skip`: the setup chores a person chose to do themselves, kept in one file the panel and Welcome app read."""

    def skipped(self, e):
        return json.loads(e.noc("skip", "list", "--json").stdout)

    def test_empty_by_default_and_a_json_list(self):
        e = Env(self, ollama=False)
        self.assertEqual(self.skipped(e), [])
        self.assertEqual(e.noc("skip").returncode, 0)

    def test_add_is_remembered_once_and_rm_takes_it_back(self):
        e = Env(self, ollama=False)
        for chore in ("github", "gpu", "github"):
            self.assertEqual(e.noc("skip", "add", chore).returncode, 0)
        self.assertEqual(self.skipped(e), ["github", "gpu"])        # no duplicates, a fixed order
        self.assertEqual(sorted((e.home / ".config/noctraos/skipped").read_text().split()), ["github", "gpu"])
        self.assertEqual(e.noc("skip", "rm", "github").returncode, 0)
        self.assertEqual(self.skipped(e), ["gpu"])
        self.assertEqual(e.noc("skip", "rm", "github").returncode, 0)  # taking back what is not skipped is fine
        self.assertEqual(e.noc("skip", "rm", "gpu").returncode, 0)
        self.assertEqual(self.skipped(e), [])

    def test_unknown_chores_and_commands_are_refused(self):
        e = Env(self, ollama=False)
        for args in (("add", "everything"), ("add",), ("rm", "../x"), ("frobnicate",)):
            result = e.noc("skip", *args)
            self.assertEqual(result.returncode, 1, args)
        self.assertEqual(self.skipped(e), [])

    def test_a_hand_edited_file_cannot_inject_anything(self):
        e = Env(self, ollama=False)
        path = e.home / ".config/noctraos"
        path.mkdir(parents=True)
        (path / "skipped").write_text("gpu\nrm -rf /\n\"; evil\ngit extra\n")
        self.assertEqual(self.skipped(e), ["gpu"])

    def test_status_carries_the_list(self):
        e = Env(self, ollama=False)
        self.assertEqual(json.loads(e.noc("status", "--json").stdout)["skipped"], [])
        e.noc("skip", "add", "git")
        self.assertEqual(json.loads(e.noc("status", "--json").stdout)["skipped"], ["git"])


class UpdatesCommandTests(unittest.TestCase):
    def run_updates(self, e):
        return json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version").stdout)

    def test_shape_and_apt_download_size(self):
        e = Env(self)
        e.stub("apt-get", 'case "$*" in *print-uris*) printf "\'http://x/a.deb\' a.deb 1500 MD5Sum:aa\\n\'http://x/b.deb\' b.deb 9000000 MD5Sum:bb\\n";; *) printf "Inst a\\nInst b\\nConf a\\n";; esac')
        e.stub("flatpak", "printf 'org.a\\norg.b\\n'")
        e.stub("mise", 'echo \'{"node":{},"go":{}}\'')
        e.stub("ollama", "true")  # `noc updates` only asks the API when the binary exists; CI has none
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

    def test_noctraos_update_is_null_without_the_updater_and_passed_through_with_it(self):
        e = Env(self)
        e.stub("ollama", "true")
        self.assertIsNone(self.run_updates(e)["noctraos"])   # CI has no /usr/local/libexec/noctraos
        e.stub("selfupdate", 'echo \'{"status": "available", "channel": "stable", "available": {"serial": 4, "version": "0.3.3"}}\'')
        data = json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version", NOC_SELFUPDATE=str(e.bin / "selfupdate")).stdout)
        self.assertEqual(data["noctraos"]["status"], "available")
        self.assertEqual(data["noctraos"]["available"]["serial"], 4)

    def test_apps_is_null_without_the_tracker_and_passed_through_with_it(self):
        e = Env(self)
        e.stub("ollama", "true")
        self.assertIsNone(self.run_updates(e)["apps"])
        e.stub("tracker", 'echo \'{"updates": 1, "user_updates": 1, "online": true, "apps": [{"id": "hermes", "status": "outdated"}]}\'')
        data = json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version", NOC_UPSTREAM=str(e.bin / "tracker")).stdout)
        self.assertEqual(data["apps"]["apps"][0]["id"], "hermes")
        e.stub("tracker", "echo not-json")
        data = json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version", NOC_UPSTREAM=str(e.bin / "tracker")).stdout)
        self.assertIsNone(data["apps"])

    def test_status_carries_the_cached_app_versions_and_never_goes_online_for_them(self):
        e = Env(self)
        e.stub("tracker", 'echo "$*" >> "$TRACKER_LOG"; echo \'{"updates": 0, "apps": []}\'')
        log = e.home / "tracker.log"
        data = json.loads(e.noc("status", "--json", NOC_UPSTREAM=str(e.bin / "tracker"), TRACKER_LOG=str(log)).stdout)
        self.assertEqual(data["apps"], {"updates": 0, "apps": []})
        self.assertIn("--offline", log.read_text())
        self.assertIsNone(json.loads(e.noc("status", "--json").stdout)["apps"])

    def test_status_carries_the_accounts_state(self):
        e = Env(self)
        e.stub("acct", 'echo \'{"git": {"ready": false}, "github": {"signed_in": false}}\'')
        data = json.loads(e.noc("status", "--json", NOC_ACCOUNTS=str(e.bin / "acct")).stdout)
        self.assertEqual(data["accounts"]["git"]["ready"], False)
        self.assertIsNone(json.loads(e.noc("status", "--json").stdout)["accounts"])
        e.stub("acct", "echo not-json")
        self.assertIsNone(json.loads(e.noc("status", "--json", NOC_ACCOUNTS=str(e.bin / "acct")).stdout)["accounts"])

    def test_noc_accounts_passes_everything_through(self):
        e = Env(self)
        e.stub("acct", 'echo "ran: $*"')
        r = e.noc("accounts", "git", "set", "--name", "Ada Lovelace", "--email", "a@b.co", NOC_ACCOUNTS=str(e.bin / "acct"))
        self.assertEqual(r.stdout.strip(), "ran: git set --name Ada Lovelace --email a@b.co")
        self.assertNotEqual(e.noc("accounts", NOC_ACCOUNTS="/nonexistent").returncode, 0)

    def test_noc_apps_runs_the_tracker_with_its_arguments(self):
        e = Env(self)
        e.stub("tracker", 'echo "ran: $*"')
        r = e.noc("apps", "--json", "--refresh", NOC_UPSTREAM=str(e.bin / "tracker"))
        self.assertEqual(r.stdout.strip(), "ran: list --json --refresh")
        self.assertNotEqual(e.noc("apps", NOC_UPSTREAM="/nonexistent").returncode, 0)

    def test_a_garbled_updater_answer_becomes_null_not_a_broken_document(self):
        e = Env(self)
        e.stub("selfupdate", "echo not-json")
        data = json.loads(e.noc("updates", NOC_ONLINE_URLS=e.url + "/api/version", NOC_SELFUPDATE=str(e.bin / "selfupdate")).stdout)
        self.assertIsNone(data["noctraos"])

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
    def events(self, e, *args, **extra):
        result = e.noc("update", "--json", *args, **extra)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        return result, lines

    def test_apps_step_as_root_runs_the_tracker_as_the_asking_user_or_refuses(self):
        """These are the person's own apps, never root's: as root the step runs through `sudo -u $SUDO_USER`, and refuses without
        one. `id` is faked so this runs as any user, and a stub sudo records what it was asked to run."""
        e = Env(self)
        e.stub("sudo", 'echo "sudo $*"')
        e.stub("tracker", "echo tracker-ran")

        def step(sudo_user):
            script = (f'id() {{ echo 0; }}; source "{NOC}"; UPSTREAM="{e.bin}/tracker"; '
                      f'{f"SUDO_USER={sudo_user}; " if sudo_user else "unset SUDO_USER; "}step_apps')
            return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e.env())
        ok = step("ada")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn(f"sudo -u ada -H {e.bin}/tracker update", ok.stdout)
        refused = step("")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("run this as your own user", refused.stdout)
        self.assertNotIn("tracker-ran", refused.stdout)
        self.assertNotEqual(step("root").returncode, 0)

    @unittest.skipIf(os.geteuid() == 0, "as root the step runs as SUDO_USER through sudo; the test above covers that")
    def test_apps_step_runs_the_tracker_update_and_reports_failure(self):
        e = Env(self)
        e.stub("tracker", 'echo "Hermes is now 0.21.7."; [ "$1" = update ] || exit 9; [ -z "${TRACKER_FAIL:-}" ]')
        result, ev = self.events(e, "--only", "apps", NOC_UPSTREAM=str(e.bin / "tracker"))
        self.assertEqual(result.returncode, 0, result.stderr)
        step = [x for x in ev if x["event"] == "step"][0]
        self.assertEqual((step["id"], step["label"]), ("apps", "Hermes and coding agents (latest upstream releases)"))
        self.assertTrue(any("0.21.7" in x.get("line", "") for x in ev))
        self.assertTrue([x for x in ev if x["event"] == "step_done"][0]["ok"])
        result, ev = self.events(e, "--only", "apps", NOC_UPSTREAM=str(e.bin / "tracker"), TRACKER_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([x for x in ev if x["event"] == "step_done"][0]["ok"])
        result, ev = self.events(e, "--only", "apps", NOC_UPSTREAM="/nonexistent")
        self.assertFalse([x for x in ev if x["event"] == "step_done"][0]["ok"])

    def test_noctraos_step_runs_the_updater_and_reports_failure(self):
        e = Env(self)
        e.stub("sudo", 'if [ "$1" = "-n" ]; then shift; fi; exec "$@"')
        e.stub("selfupdate", 'echo "Updated to NoctraOS 0.3.3 (update 4)."; [ "$1" = apply ] || exit 9')
        result, ev = self.events(e, "--only", "noctraos", NOC_SELFUPDATE=str(e.bin / "selfupdate"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([x for x in ev if x["event"] == "step"][0]["id"], "noctraos")
        self.assertTrue(any("update 4" in x.get("line", "") for x in ev))
        self.assertTrue([x for x in ev if x["event"] == "step_done"][0]["ok"])
        e.stub("selfupdate", "exit 1")
        result, ev = self.events(e, "--only", "noctraos", NOC_SELFUPDATE=str(e.bin / "selfupdate"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([x for x in ev if x["event"] == "step_done"][0]["ok"])

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


class ChannelTests(unittest.TestCase):
    """`noc channel`: the terminal route to the same choice the Updates page offers."""

    def env(self):
        e = Env(self, ollama=False)
        e.stub("selfupdate", 'if [ "$1" = status ]; then printf "channel: stable\\nserial: 3\\nversion: 0.4.1\\nmirrors: [x]\\n"; '
                             'else echo "$@" >> "$HOME/calls"; fi')
        e.stub("sudo", 'exec "$@"')                              # a real sudo would ask for a password in a test
        return e, {"NOC_SELFUPDATE": str(e.bin / "selfupdate")}

    def test_it_shows_the_channel_and_the_installed_update(self):
        e, extra = self.env()
        out = e.noc("channel", **extra).stdout
        self.assertEqual(out.splitlines(), ["channel: stable", "serial: 3", "version: 0.4.1"])

    def test_it_sets_only_the_two_known_channels(self):
        e, extra = self.env()
        self.assertEqual(e.noc("channel", "nightly", **extra).returncode, 0)
        self.assertEqual((e.home / "calls").read_text().strip(), "set-channel nightly")
        for bad in ("beta", "../x", "stable; id"):
            self.assertEqual(e.noc("channel", bad, **extra).returncode, 1, bad)
        self.assertEqual((e.home / "calls").read_text().strip(), "set-channel nightly")      # nothing else reached the updater

    def test_without_an_updater_it_says_so(self):
        e = Env(self, ollama=False)
        result = e.noc("channel", NOC_SELFUPDATE="/nonexistent/su")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no NoctraOS updater", result.stdout + result.stderr)


def stand_in_installer(e):
    """A stand-in for the snapshot's install.sh: logs its arguments, one run per line. Returns (extra env, log path)."""
    log = Path(e.tmp.name) / "installer-args"
    script = Path(e.tmp.name) / "install.sh"
    script.write_text(f'#!/bin/sh\necho "$*" >> "{log}"\n')
    return {"NOC_INSTALLER": str(script)}, log


class RepairTests(unittest.TestCase):
    """`noc repair`: what the Health page's Fix buttons do, from a terminal."""

    def test_each_name_runs_its_module_from_the_installer(self):
        for name, module in (("appmanager", "04d_appmanager.sh"), ("vm-guest", "01b_vm_guest.sh")):
            with self.subTest(name=name):
                e = Env(self, ollama=False)
                extra, log = stand_in_installer(e)
                self.assertEqual(e.noc("repair", name, **extra).returncode, 0)
                self.assertEqual(log.read_text().split(), ["--only", module])

    def test_hermes_runs_its_own_installer(self):
        e = Env(self, ollama=False)
        e.stub("noctraos-hermes", f'echo "hermes $*" >> "{e.home}/calls"')
        self.assertEqual(e.noc("repair", "hermes").returncode, 0)
        self.assertEqual((e.home / "calls").read_text().strip(), "hermes install")

    def test_anything_else_is_a_usage_message_and_runs_nothing(self):
        e = Env(self, ollama=False)
        extra, log = stand_in_installer(e)
        for args in ((), ("bogus",), ("03b_ollama_update.sh",), ("../install.sh",)):
            result = e.noc("repair", *args, **extra)
            self.assertEqual(result.returncode, 1, args)
            self.assertIn("usage: noc repair", result.stdout)
        self.assertFalse(log.exists())

    def test_without_the_snapshot_it_says_so(self):
        result = Env(self, ollama=False).noc("repair", "appmanager", NOC_INSTALLER="/nonexistent/install.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not in place", result.stdout)


APPS_JSON = json.dumps({"online": True, "apps": [
    {"id": "hermes", "updater": "user", "status": "current"},
    {"id": "ollama", "updater": "root", "module": "03b_ollama_update.sh", "status": "outdated"},
    {"id": "appmanager", "updater": "root", "module": "04d_appmanager.sh", "status": "current"},
    {"id": "codex", "updater": "user", "status": "outdated"},
    {"id": "claude", "updater": "user", "status": "outdated"},
]})


def tracker_stub(e, rows=APPS_JSON, listing_fails=False):
    """A stand-in for noc-upstream: prints `rows` for `list`, logs every other call. Returns (extra env, log path)."""
    calls = e.home / "tracker-calls"
    listing = "exit 1" if listing_fails else f"echo '{rows}'"
    e.stub("tracker", f'if [ "$1" = list ]; then {listing}; fi\nif [ "$1" != list ]; then echo "$*" >> "{calls}"; fi')
    return {"NOC_UPSTREAM": str(e.bin / "tracker")}, calls


class AppsUpdateTests(unittest.TestCase):
    """`noc apps update`: the Apps page's Update buttons, including the root-owned apps the tracker only reports."""

    def run_noc(self, *args, listing_fails=False):
        e = Env(self, ollama=False)
        extra, log = stand_in_installer(e)
        tracker_env, calls = tracker_stub(e, listing_fails=listing_fails)
        result = e.noc("apps", "update", *args, **extra, **tracker_env)
        installer = log.read_text().splitlines() if log.exists() else []
        tracker = calls.read_text().splitlines() if calls.exists() else []
        return result, installer, tracker

    def test_everything_behind_is_updated_the_root_app_through_its_module(self):
        result, installer, tracker = self.run_noc()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(installer, ["--only 03b_ollama_update.sh"])          # only the one that is behind
        self.assertEqual(tracker, ["update"])                                  # Hermes and the agents, as the person

    def test_a_root_app_alone_never_calls_the_user_tracker(self):
        result, installer, tracker = self.run_noc("ollama")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((installer, tracker), (["--only 03b_ollama_update.sh"], []))

    def test_user_apps_alone_go_to_the_tracker_with_their_names(self):
        result, installer, tracker = self.run_noc("codex,claude")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((installer, tracker), ([], ["update --only codex,claude"]))

    def test_a_current_root_app_is_left_alone(self):
        result, installer, tracker = self.run_noc("appmanager")
        self.assertEqual((result.returncode, installer, tracker), (0, [], []))

    def test_an_unknown_app_is_refused_before_anything_runs(self):
        result, installer, tracker = self.run_noc("ollama,nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown app: nope", result.stdout)
        self.assertEqual((installer, tracker), ([], []))

    def test_no_connection_is_an_error_not_a_silent_success(self):
        result, installer, tracker = self.run_noc(listing_fails=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual((installer, tracker), ([], []))

    def test_the_plain_listing_still_works(self):
        e = Env(self, ollama=False)
        e.stub("tracker", 'echo "tracker $*"')
        self.assertEqual(e.noc("apps", "--json", NOC_UPSTREAM=str(e.bin / "tracker")).stdout.strip(), "tracker list --json")


class ChannelRollbackTests(unittest.TestCase):
    def test_rollback_asks_the_updater_to_put_the_previous_layer_back(self):
        e, extra = ChannelTests.env(self)
        self.assertEqual(e.noc("channel", "rollback", **extra).returncode, 0)
        self.assertEqual((e.home / "calls").read_text().strip(), "rollback")


class PrivacyStatusTests(unittest.TestCase):
    """`noc privacy status`: the one place that reads remote login, clipboard history and the keyring for the panel."""

    def setUp(self):
        self.e = Env(self, ollama=False)
        self.socket = self.e.home / ".config/copyq/.copyq_s"
        self.keyring = self.e.home / "login.keyring"
        self.calls = self.e.home / "calls"

    def systemctl(self, active, enabled):
        """A systemctl that answers is-active/is-enabled with one word per unit."""
        self.e.stub("systemctl", f'echo "$*" >> "{self.calls}"\ncase "$1" in is-active) printf "%s\\n" {active} ;; '
                                 f'is-enabled) printf "%s\\n" {enabled} ;; esac')

    def copyq(self, output):
        self.e.stub("copyq", f'echo "$QT_QPA_PLATFORM|$*" >> "{self.calls}"\necho {output}')

    def status(self, **extra):
        out = self.e.noc("privacy", "status", "--json", NOC_KEYRING_FILE=str(self.keyring), **extra)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_the_keys_are_stable(self):
        self.assertEqual(sorted(self.status()), ["clipboard", "hermes", "keyring", "remote"])

    def test_remote_login_from_what_systemctl_prints(self):
        cases = [("inactive active", "disabled enabled", "on"),
                 ("active", "disabled", "on"),                            # running, not at boot
                 ("inactive inactive", "disabled enabled", "on"),         # starts at boot
                 ("inactive", "enabled-runtime", "on"),
                 ("inactive inactive", "disabled disabled", "off"),
                 ("inactive", "indirect", "off"),
                 ("inactive inactive", "", None),                         # no unit file at all (older systemd prints nothing)
                 ("inactive inactive", "not-found not-found", None)]      # (newer systemd says so)
        for active, enabled, want in cases:
            with self.subTest(active=active, enabled=enabled):
                self.systemctl(active, enabled)
                self.assertEqual(self.status()["remote"], want)

    def test_remote_login_asks_about_both_units(self):
        self.systemctl("inactive", "disabled")
        self.status()
        self.assertEqual(self.calls.read_text().splitlines(),
                         ["is-active ssh.socket ssh.service", "is-enabled ssh.socket ssh.service"])

    def test_clipboard_is_only_asked_while_copyq_runs_because_asking_would_start_it(self):
        self.assertEqual(self.status()["clipboard"], {"installed": False, "running": False, "count": None})
        self.copyq(7)
        self.assertEqual(self.status()["clipboard"], {"installed": True, "running": False, "count": None})
        self.assertFalse(self.calls.exists())
        self.socket.parent.mkdir(parents=True)
        self.socket.write_text("")
        self.assertEqual(self.status()["clipboard"], {"installed": True, "running": True, "count": 7})
        platform, args = self.calls.read_text().strip().split("|", 1)
        self.assertEqual(platform, "xcb")                                  # the X11 client, as bin/noctraos-copyq runs it
        self.assertEqual(args, "eval tab('&clipboard'); print(size());")

    def test_the_keyring_from_the_file_header(self):
        self.assertEqual(self.status()["keyring"], "none")
        self.keyring.write_bytes(b"[keyring]\ndisplay-name=Login\nlock-on-idle=false\n")
        self.assertEqual(self.status()["keyring"], "unprotected")
        self.keyring.write_bytes(self.encrypted_magic() + b"\x00" * 200)
        self.assertEqual(self.status()["keyring"], "protected")
        for other in (b"something else entirely", b""):
            self.keyring.write_bytes(other)
            self.assertIsNone(self.status()["keyring"], other)

    @staticmethod
    def encrypted_magic():
        import importlib.util
        spec = importlib.util.spec_from_file_location("seed_password_store", ROOT / "scripts/seed-password-store.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ENCRYPTED_MAGIC                                       # the bytes the install script checks

    def test_hermes_comes_from_its_wrapper(self):
        self.assertIsNone(self.status()["hermes"])                          # not installed
        for mode in ("cloud", "local", "other"):
            self.e.stub("noctraos-hermes", f'[ "$1" = mode ] && echo {mode}')
            self.assertEqual(self.status()["hermes"], mode)
        self.e.stub("noctraos-hermes", "echo nonsense")
        self.assertIsNone(self.status()["hermes"])

    def test_the_text_form_says_each_thing_in_words(self):
        self.systemctl("active", "enabled")
        self.copyq(212)
        self.socket.parent.mkdir(parents=True)
        self.socket.write_text("")
        self.keyring.write_bytes(b"[keyring]\n")
        out = self.e.noc("privacy", "status", NOC_KEYRING_FILE=str(self.keyring)).stdout
        for want in ("Remote login", "on (other computers can sign in", "212 saved by CopyQ", "not locked by a password"):
            self.assertIn(want, out)


class PrivacyActionTests(unittest.TestCase):
    def setUp(self):
        self.e = Env(self, ollama=False)
        self.calls = self.e.home / "calls"
        self.e.stub("sudo", 'exec "$@"')                                    # a real sudo would ask for a password in a test
        self.e.stub("privileged", f'echo "privileged $*" >> "{self.calls}"')

    def systemctl(self, active, enabled):
        self.e.stub("systemctl", f'case "$1" in is-active) printf "%s\\n" {active} ;; is-enabled) printf "%s\\n" {enabled} ;; esac')

    def remote(self, *args):
        return self.e.noc("privacy", "remote", *args, NOC_PRIVILEGED=str(self.e.bin / "privileged"))

    def logged(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_remote_login_is_switched_by_the_privileged_helper_and_only_when_it_needs_to(self):
        self.systemctl("active", "enabled")
        self.assertEqual(self.remote("off").returncode, 0)
        self.assertEqual(self.logged(), ["privileged remote-access off"])
        self.assertIn("already on", self.remote("on").stdout)               # nothing to change
        self.systemctl("inactive", "disabled")
        self.assertEqual(self.remote("on").returncode, 0)
        self.assertEqual(self.logged(), ["privileged remote-access off", "privileged remote-access on"])

    def test_remote_login_shows_its_state_without_an_argument(self):
        self.systemctl("active", "enabled")
        self.assertEqual(self.remote().stdout.strip(), "remote login is on")

    def test_no_server_is_an_error_that_changes_nothing(self):
        self.systemctl("inactive", "")
        result = self.remote("on")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not installed", result.stdout)
        self.assertEqual(self.logged(), [])

    def test_anything_but_on_or_off_is_refused_before_the_helper_is_called(self):
        self.systemctl("active", "enabled")
        for word in ("maybe", "ON", "off; id", "--now"):
            self.assertEqual(self.remote(word).returncode, 1, word)
        self.assertEqual(self.logged(), [])

    def copyq(self, output, code=0):
        self.e.stub("copyq", f'echo "$QT_QPA_PLATFORM|$*" >> "{self.calls}"\necho {output}\nexit {code}')

    def test_clearing_the_clipboard_empties_only_the_default_tab(self):
        self.copyq(0)
        result = self.e.noc("privacy", "clipboard", "clear")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.logged(), ["xcb|eval tab('&clipboard'); while (size() > 0) remove(0); print(size());"])

    def test_clearing_succeeds_only_when_the_tab_ends_up_empty(self):
        self.copyq(2)
        self.assertEqual(self.e.noc("privacy", "clipboard", "clear").returncode, 1)
        self.copyq("boom", code=1)
        result = self.e.noc("privacy", "clipboard", "clear")
        self.assertEqual(result.returncode, 1)
        self.assertIn("boom", result.stdout)

    def test_clipboard_without_copyq_says_so(self):
        for args in ((), ("clear",)):
            result = self.e.noc("privacy", "clipboard", *args)
            self.assertEqual(result.returncode, 1)
            self.assertIn("CopyQ is not installed", result.stdout)

    def test_hermes_switches_without_launching_the_app(self):
        self.e.stub("noctraos-hermes", f'echo "hermes $*" >> "{self.calls}"; [ "$1" = mode ] && echo cloud; exit 0')
        self.assertEqual(self.e.noc("privacy", "hermes", "local").returncode, 0)
        self.assertEqual(self.e.noc("privacy", "hermes", "cloud").returncode, 0)
        self.assertEqual(self.e.noc("privacy", "hermes").stdout.strip(), "cloud")
        self.assertEqual(self.logged(), ["hermes local --no-launch", "hermes cloud", "hermes mode"])

    def test_hermes_missing_or_unknown_word(self):
        self.assertEqual(self.e.noc("privacy", "hermes", "local").returncode, 1)
        self.e.stub("noctraos-hermes", "true")
        self.assertEqual(self.e.noc("privacy", "hermes", "bogus").returncode, 1)

    def test_usage_for_anything_else(self):
        result = self.e.noc("privacy", "bogus")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: noc privacy", result.stdout)


class OllamaServiceTests(unittest.TestCase):
    """Ollama runs when asked and starts with the computer only if the person says so: `noc llm start|stop|autostart`."""

    def setUp(self):
        self.e = Env(self, ollama=False)
        self.calls = self.e.home / "calls"
        self.up = self.e.home / "up"                 # while this file exists, the stand-in API answers
        self.e.stub("sudo", 'exec "$@"')
        self.e.stub("ollama", "true")
        self.e.stub("curl", f'[ -e "{self.up}" ] && echo \'{{"version":"0.9.0","models":[]}}\' || exit 7')
        self.helper()

    def helper(self, answers=True):
        """A stand-in for noc-privileged: starting it makes the API answer (unless answers is False), stopping silences it."""
        start = f'touch "{self.up}"' if answers else "true"
        self.e.stub("privileged", f'echo "privileged $*" >> "{self.calls}"\ncase "$*" in "ollama-service start") {start} ;; '
                                  f'"ollama-service stop") rm -f "{self.up}" ;; esac')

    def systemctl(self, enabled, active="inactive"):
        self.e.stub("systemctl", f'case "$1" in is-active) echo {active}; [ {active} = active ] ;; is-enabled) echo {enabled} ;; esac')

    def llm(self, *args, **extra):
        return self.e.noc("llm", *args, NOC_PRIVILEGED=str(self.e.bin / "privileged"), NOC_OLLAMA_WAIT="2", **extra)

    def logged(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_autostart_shows_its_state_and_changes_it_only_when_it_needs_to(self):
        self.systemctl("disabled")
        self.assertEqual(self.llm("autostart").stdout.strip(), "Ollama starts with this computer: off")
        self.assertEqual(self.llm("autostart", "off").returncode, 0)
        self.assertEqual(self.logged(), [])                                   # already so: nothing is called
        self.assertEqual(self.llm("autostart", "on").returncode, 0)
        self.assertEqual(self.logged(), ["privileged ollama-autostart on"])
        self.systemctl("enabled")
        self.assertEqual(self.llm("autostart").stdout.strip(), "Ollama starts with this computer: on")
        self.assertEqual(self.llm("autostart", "off").returncode, 0)
        self.assertEqual(self.logged(), ["privileged ollama-autostart on", "privileged ollama-autostart off"])

    def test_autostart_never_starts_or_stops_it(self):
        self.systemctl("disabled")
        self.llm("autostart", "on")
        self.assertFalse(self.up.exists())

    def test_without_the_service_autostart_is_an_error_that_changes_nothing(self):
        for printed in ("not-found", ""):                                     # newer and older systemd
            with self.subTest(printed=printed):
                self.systemctl(printed)
                result = self.llm("autostart", "on")
                self.assertEqual(result.returncode, 1)
                self.assertIn("no Ollama service", result.stdout)
                self.assertEqual(self.logged(), [])

    def test_anything_but_on_or_off_is_refused_before_the_helper_is_called(self):
        self.systemctl("disabled")
        for word in ("maybe", "ON", "on; id", "--now", "start"):
            self.assertEqual(self.llm("autostart", word).returncode, 1, word)
        self.assertEqual(self.logged(), [])

    def test_start_runs_the_helper_and_waits_until_the_api_answers(self):
        self.systemctl("disabled")
        result = self.llm("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.logged(), ["privileged ollama-service start"])
        self.assertIn("is running", result.stdout)
        self.assertIn("already running", self.llm("start").stdout)             # the second call changes nothing
        self.assertEqual(self.logged(), ["privileged ollama-service start"])

    def test_start_that_never_answers_is_an_error(self):
        self.systemctl("disabled")
        self.helper(answers=False)
        result = self.llm("start")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not answer yet", result.stdout)

    def test_stop_runs_the_helper_once(self):
        self.systemctl("disabled", active="active")
        self.up.write_text("")
        self.assertEqual(self.llm("stop").returncode, 0)
        self.assertEqual(self.logged(), ["privileged ollama-service stop"])
        self.systemctl("disabled", active="inactive")
        self.assertIn("already stopped", self.llm("stop").stdout)
        self.assertEqual(self.logged(), ["privileged ollama-service stop"])

    @unittest.skipIf(shutil.which("ollama"), "the test needs a machine without Ollama")
    def test_start_and_stop_without_local_ai_point_at_the_setup(self):
        e = Env(self, ollama=False)
        for action in ("start", "stop"):
            result = e.noc("llm", action)
            self.assertEqual(result.returncode, 1)
            self.assertIn("noc llm setup", result.stdout)

    def test_status_and_models_list_say_whether_it_starts_with_the_computer(self):
        for printed, want in (("enabled", True), ("disabled", False), ("not-found", None), ("", None)):
            with self.subTest(printed=printed):
                self.systemctl(printed)
                status = json.loads(self.e.noc("status", "--json").stdout)
                self.assertEqual(status["ollama"]["autostart"], want)
                listing = json.loads(self.e.noc("models", "list", "--json").stdout)
                self.assertEqual(listing["autostart"], want)

    def test_doctor_does_not_call_a_stopped_ollama_a_failure_when_it_is_not_meant_to_start_with_the_computer(self):
        self.systemctl("disabled")
        row = {r["id"]: r for r in json.loads(self.e.noc("doctor", "--json").stdout)}["ollama"]
        self.assertEqual(row["status"], "info")
        self.assertIn("noc llm start", row["detail"])
        self.systemctl("enabled")
        row = {r["id"]: r for r in json.loads(self.e.noc("doctor", "--json").stdout)}["ollama"]
        self.assertEqual(row["status"], "fail")                                # set to start, and not answering: a real problem


class PanelParityTests(unittest.TestCase):
    """Whatever the Control Panel can do, `noc` can do, so a broken panel never leaves a machine without the option.
    Every root verb of noc-privileged, every module it may run and every Health fix needs a `noc` command; adding one to the
    panel without one fails here."""

    HELPER = (ROOT / "bin/noc-privileged").read_text()
    PANEL = (ROOT / "control/panel.py").read_text()

    # noc-privileged verb -> the noc command (words after `noc`) that does the same; `module` is checked per module below
    VERBS = {"update": "update", "update-channel": "channel", "update-rollback": "channel rollback", "module": None,
             "gpu-install": "gpu install", "disk-grow": "disk grow", "remote-access": "privacy remote",
             "ollama-service": "llm start", "ollama-autostart": "llm autostart"}
    # module the panel may run -> the noc command that runs the same module
    MODULES = {"04d_appmanager.sh": ["repair", "appmanager"], "01b_vm_guest.sh": ["repair", "vm-guest"],
               "03b_ollama_update.sh": ["apps", "update", "ollama"], "optional/local_llm.sh": ["llm", "setup"]}

    def test_every_root_verb_has_a_noc_command(self):
        import re
        main = self.HELPER[self.HELPER.index("main() {"):]
        verbs = set(re.findall(r"(?m)^    ([a-z][a-z-]*)\)", main))
        self.assertEqual(verbs, set(self.VERBS), "a verb was added to or removed from noc-privileged: say which noc command does it")
        noc = (ROOT / "bin/noc").read_text()
        for verb, command in self.VERBS.items():
            if command:
                first = command.split()[0]
                self.assertRegex(noc, rf"(?m)^\s+{first}\)", f"{verb}: noc has no '{first}'")

    def test_every_module_the_panel_may_run_has_a_noc_command_that_runs_that_module(self):
        import re
        allowed = re.search(r"^MODULES=\((.*)\)", self.HELPER, re.M).group(1).split()
        self.assertEqual(sorted(allowed), sorted(self.MODULES), "a module was added to or removed from noc-privileged's MODULES")
        for module, command in self.MODULES.items():
            with self.subTest(module=module):
                e = Env(self, ollama=False)
                extra, log = stand_in_installer(e)
                tracker_env, _ = tracker_stub(e)                           # `noc apps update ollama` needs Ollama to be behind
                result = e.noc(*command, **extra, **tracker_env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(log.read_text().split(), ["--only", module])

    def test_every_health_fix_names_a_noc_command(self):
        import re
        noc = (ROOT / "bin/noc").read_text()
        block = self.PANEL[self.PANEL.index("FIXES = {"):]
        for fix in re.findall(r"(?m)^    '([a-z]+:[A-Za-z0-9_.]+)':", block[:block.index("}")]):
            hints = re.findall(rf'\(run: ([^)]*)\)"[^\n]*"{re.escape(fix)}"', noc)
            self.assertEqual(len(hints), 1, f"{fix}: noc doctor has no (run: ...) hint for it")
            self.assertTrue(hints[0].startswith("noc "), f"{fix}: the hint is '{hints[0]}', not a noc command")

    def test_every_terminal_tip_is_a_noc_command_or_the_tool_for_it(self):
        import sys
        sys.path.insert(0, str(ROOT / "control"))
        try:
            import panel
        finally:
            sys.path.remove(str(ROOT / "control"))
        plain = ("git ", "gh ", "noctraos-search ", "noctraos-weather ", "sudo noc ")   # tools with no noc front, or noc with sudo
        for key, commands in panel.TERMINAL.items():
            for command in commands:
                self.assertTrue(command.startswith("noc ") or command.startswith(plain), f"{key}: '{command}'")


if __name__ == "__main__":
    unittest.main()
