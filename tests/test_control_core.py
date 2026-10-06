"""The Control Panel's formatting logic: `noc status` JSON in, cards out. No GTK needed."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "control"))
import panel  # noqa: E402

STATUS = {
    "version": "0.3.1", "os": "NoctraOS 0.3.1",
    "updates": {"apt": 3, "flatpak": 0, "reboot_required": False},
    "ollama": {"running": True, "version": "0.9", "models": 2, "default_model": "qwen2.5-coder:7b"},
    "gpu": {"gpus": [{"name": "GeForce RTX 3080 Ti"}], "plan": {}},
    "disk": {"root_free_bytes": 60 * 2**30, "root_total_bytes": 200 * 2**30},
    "ram_gb": 32, "hermes": {"installed": True, "mode": "cloud"},
    "search_index_age_seconds": 600,
}


def by_id(status):
    return {c.id: c for c in panel.cards(status)}


class FormatTests(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(panel.fmt_bytes(0), "0 B")
        self.assertEqual(panel.fmt_bytes(1536), "1.5 KB")
        self.assertEqual(panel.fmt_bytes(60 * 2**30), "60.0 GB")
        self.assertEqual(panel.fmt_bytes(3 * 2**40), "3.0 TB")
        self.assertEqual(panel.fmt_bytes(5000 * 2**40), "5000.0 TB")

    def test_age(self):
        self.assertEqual(panel.fmt_age(5), "just now")
        self.assertEqual(panel.fmt_age(60), "1 minute ago")
        self.assertEqual(panel.fmt_age(600), "10 minutes ago")
        self.assertEqual(panel.fmt_age(7200), "2 hours ago")
        self.assertEqual(panel.fmt_age(90000), "1 day ago")


class CardTests(unittest.TestCase):
    def test_every_card_is_well_formed(self):
        for card in panel.cards(STATUS):
            self.assertIn(card.level, panel.LEVELS)
            self.assertTrue(card.title and card.value)

    def test_ids_are_unique_and_ordered(self):
        ids = [c.id for c in panel.cards(STATUS)]
        self.assertEqual(ids, ["version", "updates", "ollama", "gpu", "disk", "hermes", "search"])

    def test_updates(self):
        self.assertEqual(by_id(STATUS)["updates"].value, "3 updates available")
        self.assertEqual(by_id(STATUS)["updates"].detail, "3 system")
        none = {**STATUS, "updates": {"apt": 0, "flatpak": 0, "reboot_required": False}}
        self.assertEqual((by_id(none)["updates"].value, by_id(none)["updates"].level), ("Up to date", "ok"))

    def test_updates_unknown_is_not_up_to_date(self):
        offline = {**STATUS, "updates": {"apt": None, "flatpak": None, "reboot_required": False}}
        card = by_id(offline)["updates"]
        self.assertEqual(card.value, "Could not check")
        self.assertNotEqual(card.level, "ok")

    def test_updates_partly_unknown_says_so(self):
        partial = {**STATUS, "updates": {"apt": 2, "flatpak": None, "reboot_required": False}}
        self.assertIn("could not be checked", by_id(partial)["updates"].detail)

    def test_reboot_needed_warns_even_when_up_to_date(self):
        status = {**STATUS, "updates": {"apt": 0, "flatpak": 0, "reboot_required": True}}
        card = by_id(status)["updates"]
        self.assertEqual(card.level, "warn")
        self.assertIn("Restart", card.detail)

    def test_ollama_down_is_a_state(self):
        down = {**STATUS, "ollama": {"running": False, "models": 0, "default_model": "x"}}
        card = by_id(down)["ollama"]
        self.assertEqual((card.value, card.level), ("Not running", "warn"))

    def test_gpu(self):
        self.assertEqual(by_id(STATUS)["gpu"].value, "GeForce RTX 3080 Ti")
        self.assertEqual(by_id({**STATUS, "gpu": {"gpus": []}})["gpu"].value, "No GPU for AI")
        self.assertEqual(by_id({**STATUS, "gpu": None})["gpu"].value, "Not checked")

    def test_hermes_cloud_is_never_called_local(self):
        card = by_id(STATUS)["hermes"]
        self.assertEqual(card.value, "Nous free tier")
        self.assertIn("leave this computer", card.detail)
        local = by_id({**STATUS, "hermes": {"installed": True, "mode": "local"}})["hermes"]
        self.assertEqual((local.value, local.level), ("Local only", "ok"))
        missing = by_id({**STATUS, "hermes": {"installed": False, "mode": None}})["hermes"]
        self.assertEqual(missing.value, "Not installed")

    def test_low_disk_warns(self):
        low = {**STATUS, "disk": {"root_free_bytes": 5 * 2**30, "root_total_bytes": 200 * 2**30}}
        self.assertEqual(by_id(low)["disk"].level, "warn")
        self.assertEqual(by_id(STATUS)["disk"].level, "ok")

    def test_search_index(self):
        self.assertEqual(by_id(STATUS)["search"].value, "Updated 10 minutes ago")
        self.assertEqual(by_id({**STATUS, "search_index_age_seconds": None})["search"].value, "Not built yet")

    def test_sparse_status_does_not_raise(self):
        self.assertEqual(len(panel.cards({})), 7)


class DiagnosticsTests(unittest.TestCase):
    def test_text(self):
        text = panel.diagnostics_text(STATUS, "6.8.0")
        for want in ("version: 0.3.1", "kernel: 6.8.0", "60.0 GB free of 200.0 GB",
                     "ollama: running 0.9, 2 models, default qwen2.5-coder:7b",
                     "gpu: GeForce RTX 3080 Ti", "hermes: cloud", "apt 3"):
            self.assertIn(want, text)

    def test_empty_status(self):
        self.assertIn("gpu: none", panel.diagnostics_text({}))


class NocJsonTests(unittest.TestCase):
    def test_missing_noc_is_none(self):
        original = panel.NOC
        panel.NOC = "/nonexistent/noc"
        self.addCleanup(setattr, panel, "NOC", original)
        self.assertIsNone(panel.noc_json("status"))


ROWS = [
    {"id": "os", "label": "OS", "status": "ok", "detail": "NoctraOS", "fix": None},
    {"id": "appmanager", "label": "AppManager", "status": "warn", "detail": "missing", "fix": "module:04d_appmanager.sh"},
    {"id": "ollama", "label": "Ollama", "status": "fail", "detail": "not responding", "fix": None},
    {"id": "hermes", "label": "Hermes Desktop", "status": "warn", "detail": "not installed", "fix": "hermes:install"},
    {"id": "gpu", "label": "GPU", "status": "info", "detail": "none", "fix": None},
]


class HealthTests(unittest.TestCase):
    def test_sort_puts_problems_first_and_is_stable(self):
        self.assertEqual([r["id"] for r in panel.sort_rows(ROWS)], ["ollama", "appmanager", "hermes", "gpu", "os"])

    def test_headline(self):
        self.assertEqual(panel.health_headline(ROWS), ("1 problem needs attention", "fail"))
        self.assertEqual(panel.health_headline([r for r in ROWS if r["status"] != "fail"]),
                         ("2 things could be better", "warn"))
        self.assertEqual(panel.health_headline([ROWS[0], ROWS[4]]), ("Everything checks out", "ok"))
        self.assertEqual(panel.health_headline([]), ("Everything checks out", "ok"))

    def test_fix_commands(self):
        self.assertEqual(panel.fix_command("hermes:install"), [panel.HERMES, "install"])
        # root work only ever goes through the allowlisted helper, never a bare sudo
        self.assertEqual(panel.fix_command("module:04d_appmanager.sh"),
                         [panel.PKEXEC, panel.HELPER, "module", "04d_appmanager.sh"])
        self.assertIsNone(panel.fix_command("module:00_preflight.sh"))
        self.assertIsNone(panel.fix_command(None))
        for argv in panel.FIXES.values():
            self.assertNotIn("sudo", argv)

    def test_run_hint_is_dropped_only_when_there_is_a_button(self):
        hint = "missing (run: bash ~/.local/share/noctraos/install.sh --only 04d_appmanager.sh)"
        self.assertEqual(panel.clean_detail(hint, True), "missing")
        self.assertEqual(panel.clean_detail(hint, False), hint)
        self.assertEqual(panel.clean_detail(None, True), "")
        self.assertEqual(panel.clean_detail("running (0.35.1)", True), "running (0.35.1)")

    def test_report(self):
        text = panel.report_text(ROWS, "6.8.0")
        self.assertIn("kernel: 6.8.0", text)
        self.assertIn("[FAIL] Ollama: not responding", text)
        self.assertIn("[OK  ] OS: NoctraOS", text)
        self.assertEqual(len(text.splitlines()), 2 + len(ROWS))


LISTING = {"ollama": True, "default": "qwen2.5-coder:7b", "models": [
    {"name": "qwen2.5-coder:7b", "size": 4_700_000_000, "modified": "x", "is_default": True},
    {"name": "nomic-embed-text:latest", "size": 274_000_000, "modified": "x", "is_default": False}]}
PRESETS = {"ram_gb": 16, "vram_gb": 0, "presets": [
    {"name": "qwen2.5-coder:7b", "need_gb": 6, "note": "Default", "fit": "cpu", "recommended": True},
    {"name": "qwen2.5-coder:14b", "need_gb": 12, "note": "Bigger", "fit": "no", "recommended": False},
    {"name": "llama3.2:3b", "need_gb": 3, "note": "Small", "fit": "cpu", "recommended": False},
    {"name": "nomic-embed-text", "need_gb": 1, "note": "Embeddings", "fit": "gpu", "recommended": False}]}


class ModelListTests(unittest.TestCase):
    def test_names(self):
        for name in ("llama3.2:3b", "hf.co/user/model:Q4_K_M", "phi4-mini"):
            self.assertTrue(panel.valid_model_name(name), name)
        for name in ("", " x", "a b", "a;b", "../x", "-rf", "a|b", None):
            self.assertFalse(panel.valid_model_name(name), name)

    def test_same_model_ignores_latest(self):
        self.assertTrue(panel.same_model("nomic-embed-text:latest", "nomic-embed-text"))
        self.assertFalse(panel.same_model("llama3.2:3b", "llama3.2:1b"))

    def test_installed_rows(self):
        rows = panel.installed_rows(LISTING)
        self.assertEqual([(r["name"], r["size"], r["default"]) for r in rows],
                         [("qwen2.5-coder:7b", "4.4 GB", True), ("nomic-embed-text:latest", "261.3 MB", False)])
        self.assertEqual(panel.installed_rows({"ollama": False, "models": []}), [])
        self.assertEqual(panel.installed_rows(None), [])

    def test_suggestions_skip_installed_and_rank_fit(self):
        rows = panel.suggestion_rows(PRESETS, [r["name"] for r in panel.installed_rows(LISTING)])
        self.assertEqual([r["name"] for r in rows], ["llama3.2:3b", "qwen2.5-coder:14b"])
        self.assertEqual(rows[0]["fit"], "Runs on the CPU (slower)")
        self.assertEqual(panel.suggestion_rows(None, []), [])

    def test_recommended_comes_first(self):
        rows = panel.suggestion_rows(PRESETS, [])
        self.assertEqual(rows[0]["name"], "qwen2.5-coder:7b")


class PullTrackerTests(unittest.TestCase):
    def test_layers_add_up_instead_of_resetting(self):
        t = panel.PullTracker()
        self.assertEqual(t.feed({"status": "pulling manifest"}), (None, "Fetching the model list"))
        self.assertEqual(t.feed({"status": "pulling aaa", "total": 900, "completed": 900})[0], 1.0)
        fraction, text = t.feed({"status": "pulling bbb", "total": 100, "completed": 0})
        self.assertAlmostEqual(fraction, 0.9)
        fraction, text = t.feed({"status": "pulling bbb", "total": 100, "completed": 50})
        self.assertAlmostEqual(fraction, 0.95)
        self.assertEqual(text, "Downloading: 950 B of 1000 B")

    def test_stages_and_end(self):
        t = panel.PullTracker()
        self.assertEqual(t.feed({"status": "verifying sha256 digest"})[1], "Verifying the download")
        self.assertEqual(t.feed({"status": "success"}), (1.0, "Done"))
        self.assertEqual(t.feed({"status": "something new"})[1], "Something new")

    def test_error(self):
        self.assertEqual(panel.PullTracker().feed({"error": "pull model manifest: file does not exist"}),
                         (None, "Failed: pull model manifest: file does not exist"))


class PullHandler(BaseHTTPRequestHandler):
    EVENTS = [{"status": "pulling manifest"}, {"status": "pulling aaa", "total": 10, "completed": 5},
              {"status": "pulling aaa", "total": 10, "completed": 10}, {"status": "success"}]
    seen = []

    def do_POST(self):  # noqa: N802
        PullHandler.seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for event in self.EVENTS:
                self.wfile.write(json.dumps(event).encode() + b"\n\n")  # blank lines must be ignored
                self.wfile.flush()
        except BrokenPipeError:  # the client cancelled
            pass

    def log_message(self, *args):
        pass


class PullStreamTests(unittest.TestCase):
    def server(self):
        server = HTTPServer(("127.0.0.1", 0), PullHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_streams_every_event(self):
        events = list(panel.iter_pull("llama3.2:3b", self.server()))
        self.assertEqual([e["status"] for e in events], ["pulling manifest", "pulling aaa", "pulling aaa", "success"])
        self.assertEqual(PullHandler.seen[-1], {"model": "llama3.2:3b", "stream": True})

    def test_cancel_stops_the_stream(self):
        got = []
        for event in panel.iter_pull("x", self.server(), cancelled=lambda: len(got) >= 2):
            got.append(event)
        self.assertEqual(len(got), 2)

    def test_unreachable_raises_oserror(self):
        with self.assertRaises(OSError):
            list(panel.iter_pull("x", "http://127.0.0.1:9", timeout=2))


class NocRunTests(unittest.TestCase):
    def test_missing_noc(self):
        original = panel.NOC
        panel.NOC = "/nonexistent/noc"
        self.addCleanup(setattr, panel, "NOC", original)
        ok, message = panel.noc_run("models", "rm", "x")
        self.assertFalse(ok)
        self.assertTrue(message)

    def test_reports_last_line(self):
        original = panel.NOC
        panel.NOC = "/bin/sh"
        self.addCleanup(setattr, panel, "NOC", original)
        self.assertEqual(panel.noc_run("-c", "echo one; echo two; exit 3"), (False, "two"))
        self.assertEqual(panel.noc_run("-c", "echo fine"), (True, "fine"))


UPDATES = {"online": True, "apt": {"count": 3, "download_bytes": 724_000_000}, "flatpak": {"count": 1},
           "mise": {"count": 0}, "models": {"installed": 2}, "reboot_required": False}


def rows_by_id(updates):
    return {r["id"]: r for r in panel.update_rows(updates)}


class UpdateRowTests(unittest.TestCase):
    def test_rows(self):
        rows = rows_by_id(UPDATES)
        self.assertEqual(list(rows), ["apt", "flatpak", "mise", "models"])
        self.assertEqual(rows["apt"]["detail"], "3 updates, 690.5 MB to download")
        self.assertTrue(rows["apt"]["checked"])
        self.assertEqual(rows["flatpak"]["detail"], "1 update")
        self.assertEqual((rows["mise"]["detail"], rows["mise"]["available"]), ("Up to date.", False))

    def test_models_never_start_checked(self):
        row = rows_by_id(UPDATES)["models"]
        self.assertTrue(row["available"])
        self.assertFalse(row["checked"])
        self.assertFalse(rows_by_id({**UPDATES, "models": {"installed": 0}})["models"]["available"])

    def test_unknown_is_not_up_to_date(self):
        rows = rows_by_id({**UPDATES, "apt": {"count": None, "download_bytes": None}, "flatpak": {"count": None},
                           "mise": {"count": None}})
        for step in ("apt", "flatpak", "mise"):
            self.assertEqual(rows[step]["detail"], "Could not check.")
            self.assertFalse(rows[step]["available"])
            self.assertFalse(rows[step]["checked"])

    def test_sparse_input_does_not_raise(self):
        self.assertEqual(len(panel.update_rows({})), 4)

    def test_offline_zero_is_not_up_to_date(self):
        zero = {**UPDATES, "apt": {"count": 0, "download_bytes": 0}, "flatpak": {"count": 0}, "mise": {"count": 0}}
        for step, row in rows_by_id({**zero, "online": False}).items():
            if step != "models":
                self.assertEqual(row["detail"], "Could not check without internet.")
        for step, row in rows_by_id(zero).items():
            if step != "models":
                self.assertEqual(row["detail"], "Up to date.")

    def test_offline_still_shows_known_pending_updates(self):
        self.assertEqual(rows_by_id({**UPDATES, "online": False})["apt"]["detail"], "3 updates, 690.5 MB to download")

    def test_offline_message(self):
        self.assertIn("No internet", panel.offline_message({"online": False}))
        self.assertEqual(panel.offline_message(UPDATES), "")
        self.assertEqual(panel.offline_message(None), "")


class PlanTests(unittest.TestCase):
    def test_root_steps_share_one_prompt_and_run_first(self):
        chunks = panel.plan_chunks(["models", "flatpak", "apt", "mise"])
        self.assertEqual(chunks[0], (["apt", "flatpak"], [panel.PKEXEC, panel.HELPER, "update", "apt,flatpak"]))
        self.assertEqual(chunks[1], (["mise", "models"], [panel.NOC, "update", "--json", "--only", "mise,models"]))
        self.assertEqual(len(chunks), 2)

    def test_only_what_was_chosen(self):
        self.assertEqual([ids for ids, _ in panel.plan_chunks(["mise"])], [["mise"]])
        self.assertEqual(panel.plan_chunks([]), [])
        self.assertEqual(panel.plan_chunks(["bogus"]), [])

    def test_no_chunk_uses_sudo(self):
        for _ids, argv in panel.plan_chunks(list(panel.STEP_ORDER)):
            self.assertNotIn("sudo", argv)

    def test_exit_messages(self):
        self.assertIn("cancelled", panel.exit_message(126))
        self.assertIn("not allowed", panel.exit_message(127))
        self.assertEqual(panel.exit_message(1), "")
        self.assertEqual(panel.exit_message(0), "")


class ProgressTests(unittest.TestCase):
    def test_overall_fraction_across_chunks(self):
        p = panel.UpdateProgress(["apt", "flatpak", "mise"])
        self.assertEqual(p.fraction, 0)
        p.feed({"event": "step", "id": "apt", "label": "apt packages"})
        self.assertEqual(p.text, "apt packages…")
        self.assertEqual(p.feed({"event": "log", "line": "Reading package lists"}), "Reading package lists")
        p.feed({"event": "step_done", "id": "apt", "ok": True})
        self.assertAlmostEqual(p.fraction, 1 / 3)
        p.feed({"event": "step_done", "id": "flatpak", "ok": False})
        p.feed({"event": "done", "ok": False, "reboot_required": True})   # a chunk's done is not the end
        self.assertAlmostEqual(p.fraction, 2 / 3)
        p.feed({"event": "step_done", "id": "mise", "ok": True})
        p.feed({"event": "done", "ok": True, "reboot_required": False})
        self.assertEqual((p.fraction, p.failed, p.reboot_required), (1.0, ["flatpak"], True))

    def test_a_running_step_counts_as_half_done(self):
        p = panel.UpdateProgress(["apt"])
        self.assertEqual(p.display_fraction, 0)
        p.feed({"event": "step", "id": "apt", "label": "apt packages"})
        self.assertEqual(p.display_fraction, 0.5)
        p.feed({"event": "step_done", "id": "apt", "ok": True})
        self.assertEqual(p.display_fraction, 1.0)
        two = panel.UpdateProgress(["apt", "mise"])
        two.feed({"event": "step", "id": "apt"})
        two.feed({"event": "step_done", "id": "apt", "ok": True})
        two.feed({"event": "step", "id": "mise"})
        self.assertEqual(two.display_fraction, 0.75)

    def test_empty_plan_is_complete(self):
        self.assertEqual(panel.UpdateProgress([]).fraction, 1.0)


class RunEventsTests(unittest.TestCase):
    def test_json_log_and_exit(self):
        script = ("echo '{\"event\":\"step\",\"id\":\"mise\"}'; echo plain text; echo oops >&2; "
                  "echo '{\"not\":\"an event\"}'; echo; exit 3")
        events = list(panel.run_events(["/bin/sh", "-c", script]))
        self.assertEqual(events[0], {"event": "step", "id": "mise"})
        lines = [e["line"] for e in events if e["event"] == "log"]
        self.assertIn("plain text", lines)
        self.assertIn("oops", lines)
        self.assertIn('{"not":"an event"}', lines)
        self.assertEqual(events[-1], {"event": "exit", "code": 3})

    def test_missing_program(self):
        events = list(panel.run_events(["/nonexistent/pkexec", "x"]))
        self.assertEqual(events[-1], {"event": "exit", "code": 127})


def det(nvidia="none", amd="none", gpus=()):
    return {"gpus": [dict(g) for g in gpus], "plan": {"nvidia": nvidia, "amd": amd, "amd_hsa_override": None}}


NV = {"name": "GeForce RTX 3080 Ti", "vendor": "nvidia", "tier": "modern"}
AMD_VK = {"name": "Radeon RX 580", "vendor": "amd", "tier": "vulkan"}
AMD_ROCM = {"name": "Radeon RX 7900", "vendor": "amd", "tier": "rocm"}
READY = {"gpus": ["x"], "ready": True, "reboot_pending": False, "rows": [{"status": "ok", "text": "GPU: x"}]}
NOT_READY = {"gpus": ["x"], "ready": False, "reboot_pending": False, "rows": [{"status": "fail", "text": "no driver"}]}


class HardwareTests(unittest.TestCase):
    def test_verdicts(self):
        self.assertIn("CUDA 13", panel.gpu_verdict(NV))
        self.assertIn("Vulkan", panel.gpu_verdict(AMD_VK))
        self.assertIn("CPU", panel.gpu_verdict({"vendor": "nvidia", "tier": "unsupported"}))
        self.assertIn("Not recognised", panel.gpu_verdict({"vendor": "intel", "tier": "x"}))

    def test_install_vendors(self):
        self.assertEqual(panel.install_vendors(det("modern", "vulkan")), ["nvidia", "amd"])
        self.assertEqual(panel.install_vendors(det("legacy")), ["nvidia"])
        self.assertEqual(panel.install_vendors(det("unsupported")), [])     # too old: nothing to install
        self.assertEqual(panel.install_vendors(det()), [])
        self.assertEqual(panel.install_vendors(None), [])

    def test_install_argv_picks_the_vendor_or_all(self):
        self.assertEqual(panel.gpu_install_argv(det("modern", gpus=[NV])), [panel.PKEXEC, panel.HELPER, "gpu-install", "nvidia"])
        self.assertEqual(panel.gpu_install_argv(det(amd="vulkan")), [panel.PKEXEC, panel.HELPER, "gpu-install", "amd"])
        self.assertEqual(panel.gpu_install_argv(det("modern", "rocm"))[-1], "all")
        self.assertIsNone(panel.gpu_install_argv(det()))
        for d in (det("modern", "rocm"), det(amd="vulkan")):
            self.assertNotIn("sudo", panel.gpu_install_argv(d))

    def test_summary_is_honest_about_size_restart_and_consent(self):
        text = " ".join(panel.install_summary(det("modern", gpus=[NV])))
        self.assertIn("about 4 GB", text)
        self.assertIn("restart is needed", text)
        self.assertIn("Nothing changes until you press Install", text)
        vk = " ".join(panel.install_summary(det(amd="vulkan")))
        self.assertIn("ROCm does not support this card", vk)
        self.assertNotIn("restart is needed", vk)
        self.assertIn("about 15 GB", " ".join(panel.install_summary(det(amd="rocm"))))
        self.assertIn("log out", " ".join(panel.install_summary(det(amd="rocm"))))

    def test_disk_blocker(self):
        d = det(amd="rocm")
        self.assertEqual(panel.disk_needed_gb(d), 30)
        self.assertIn("Not enough free disk space", panel.install_blocker(d, 10 * 1024 ** 3))
        self.assertEqual(panel.install_blocker(d, 100 * 1024 ** 3), "")
        self.assertEqual(panel.install_blocker(d, None), "")
        self.assertEqual(panel.install_blocker(det(), 1), "")

    def test_state(self):
        s = panel.hardware_state(det("modern", gpus=[NV]), READY)
        self.assertEqual((s["level"], s["can_install"]), ("ok", False))
        self.assertEqual(s["gpus"][0]["name"], "GeForce RTX 3080 Ti")
        s = panel.hardware_state(det("modern", gpus=[NV]), NOT_READY)
        self.assertEqual((s["level"], s["can_install"]), ("warn", True))
        s = panel.hardware_state(det("modern", gpus=[NV]), {**NOT_READY, "reboot_pending": True})
        self.assertEqual((s["level"], s["can_install"], s["reboot"]), ("warn", False, True))   # never re-install over a pending reboot
        self.assertIn("Restart", s["headline"])
        s = panel.hardware_state(det(), {"gpus": [], "ready": False, "rows": []})
        self.assertEqual((s["level"], s["can_install"]), ("info", False))
        self.assertIn("CPU", s["headline"])
        s = panel.hardware_state(det("unsupported", gpus=[{"name": "GTX 680", "vendor": "nvidia", "tier": "unsupported"}]), NOT_READY)
        self.assertFalse(s["can_install"])
        self.assertIn("not usable", s["headline"])
        self.assertEqual(panel.hardware_state(None, None)["level"], "info")


class PrivacyTests(unittest.TestCase):
    def test_hermes_text_never_calls_the_cloud_local(self):
        cloud = panel.hermes_privacy("cloud")
        self.assertIn("leaves this computer", cloud["text"])
        self.assertEqual((cloud["level"], cloud["can_switch"]), ("warn", True))
        self.assertNotIn("Local", cloud["headline"])
        local = panel.hermes_privacy("local")
        self.assertEqual((local["headline"], local["level"]), ("Local only", "ok"))
        self.assertFalse(panel.hermes_privacy("other")["can_switch"])
        self.assertFalse(panel.hermes_privacy(None)["can_switch"])

    def test_switch_command(self):
        self.assertEqual(panel.switch_command("local", "cloud"), [panel.HERMES, "local", "--no-launch"])
        self.assertEqual(panel.switch_command("cloud", "local"), [panel.HERMES, "cloud"])
        self.assertIsNone(panel.switch_command("local", "local"))
        self.assertIsNone(panel.switch_command("cloud", "other"))     # never touch the user's own provider
        self.assertIsNone(panel.switch_command("local", None))
        self.assertIsNone(panel.switch_command("bogus", "cloud"))

    def test_local_never_launches_the_app(self):
        self.assertIn("--no-launch", panel.HERMES_LOCAL)

    def test_run_ok(self):
        self.assertEqual(panel.run_ok(["/bin/sh", "-c", "echo a; echo b; exit 1"]), (False, "b"))
        self.assertEqual(panel.run_ok(["/bin/sh", "-c", "echo fine"]), (True, "fine"))
        ok, message = panel.run_ok(["/nonexistent/x"])
        self.assertFalse(ok)
        self.assertTrue(message)

    def test_hermes_mode_when_missing(self):
        original = panel.HERMES
        panel.HERMES = "/nonexistent/hermes"
        self.addCleanup(setattr, panel, "HERMES", original)
        self.assertIsNone(panel.hermes_mode())


if __name__ == "__main__":
    unittest.main()
