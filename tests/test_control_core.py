"""The Control Panel's formatting logic: `noc status` JSON in, cards out. No GTK needed."""
from pathlib import Path
import sys
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


if __name__ == "__main__":
    unittest.main()
