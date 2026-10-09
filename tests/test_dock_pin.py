"""The Control Panel icon in the dock: pinned by a fresh install, and by a once-only migration for older accounts."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/user/0001_pin_control_panel.sh"
ID = "noctraos-control.desktop"

# A gsettings that keeps favorite-apps in a file and answers like the real one.
FAKE_GSETTINGS = """#!/bin/sh
store="$FAKE_FAVORITES"
case "$1" in
  get) [ -f "$store" ] && cat "$store" || exit 1 ;;
  set) printf '%s\\n' "$4" > "$store" ;;
esac
"""


class PinMigrationTests(unittest.TestCase):
    def run_migration(self, favorites, launcher=True):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "bin").mkdir()
        fake = tmp / "bin/gsettings"
        fake.write_text(FAKE_GSETTINGS)
        fake.chmod(0o755)
        store = tmp / "favorites"
        if favorites is not None:
            store.write_text(favorites + "\n")
        (tmp / "apps").mkdir()
        if launcher:
            (tmp / "apps" / ID).write_text("[Desktop Entry]\n")
        result = subprocess.run(["bash", str(MIGRATION)], capture_output=True, text=True,
                                env={**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "FAKE_FAVORITES": str(store),
                                     "NOCTRAOS_APPLICATIONS_DIR": str(tmp / "apps")})
        return result, store.read_text().strip() if store.exists() else None

    def test_it_appends_to_the_existing_favorites(self):
        result, after = self.run_migration("['org.gnome.Nautilus.desktop', 'code.desktop']")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(after, f"['org.gnome.Nautilus.desktop', 'code.desktop', '{ID}']")

    def test_it_works_on_an_empty_list(self):
        self.assertEqual(self.run_migration("@as []")[1], f"['{ID}']")

    def test_it_never_pins_twice(self):
        favorites = f"['{ID}', 'code.desktop']"
        result, after = self.run_migration(favorites)
        self.assertEqual((result.returncode, after), (0, favorites))

    def test_without_the_launcher_it_changes_nothing_and_tries_again_later(self):
        favorites = "['code.desktop']"
        result, after = self.run_migration(favorites, launcher=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(after, favorites)

    def test_without_desktop_settings_it_tries_again_later(self):
        self.assertNotEqual(self.run_migration(None)[0].returncode, 0)


class FreshInstallTests(unittest.TestCase):
    def test_the_desktop_module_pins_the_panel_and_the_launcher_exists(self):
        module = (ROOT / "install/06_desktop_theme.sh").read_text()
        self.assertIn(ID, module)
        self.assertTrue((ROOT / "configs/applications" / ID).is_file())
        self.assertTrue((ROOT / "assets/icons/noctraos-control.svg").is_file())

    def test_the_running_window_groups_under_the_pinned_icon(self):
        """GNOME matches a window to its launcher by app id; GTK takes it from the program name, so main.py must set it to the
        launcher's file name (found on a real desktop: without it the panel got a second, generic icon next to the pinned one)."""
        main = (ROOT / "control/main.py").read_text()
        self.assertIn(f"GLib.set_prgname('{ID.removesuffix('.desktop')}')", main)

    def test_the_launcher_names_the_panel(self):
        launcher = (ROOT / "configs/applications" / ID).read_text()
        self.assertIn("Name=NoctraOS Control Panel", launcher)
        self.assertIn("Icon=noctraos-control", launcher)


if __name__ == "__main__":
    unittest.main()
