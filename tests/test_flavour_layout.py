"""Flavour folder layout (guardrails for docs/flavours.md).

Desktop code lives in its desktop's folder, and each flavour's base ISO script has a known name.
Each folder keeps a README, so the layout stays tracked by git while it is empty.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FOLDERS = {"gnome": ROOT / "install/desktop/gnome", "plasma": ROOT / "install/desktop/plasma"}
ISO_FOLDER = ROOT / "iso/flavours"
FLAVOUR_IDS = {"zorin", "kubuntu"}


class FlavourLayoutTests(unittest.TestCase):
    def test_desktop_folders_exist_with_a_readme(self):
        for desktop, folder in DESKTOP_FOLDERS.items():
            self.assertTrue((folder / "README.md").is_file(), f"install/desktop/{desktop}/README.md is missing")

    def test_desktop_modules_declare_their_own_desktop(self):
        for desktop, folder in DESKTOP_FOLDERS.items():
            for path in sorted(folder.glob("*.sh")):
                second = path.read_text(encoding="utf-8").splitlines()[1:2]
                self.assertEqual(second, [f"# desktops: {desktop}"],
                                 f"{path.name} must declare '# desktops: {desktop}' on line 2")

    def test_flavour_iso_scripts_use_known_ids(self):
        self.assertTrue((ISO_FOLDER / "README.md").is_file(), "iso/flavours/README.md is missing")
        for path in sorted(ISO_FOLDER.glob("*.sh")):
            self.assertIn(path.stem, FLAVOUR_IDS, f"{path.name}: flavour scripts must be named by a known id")


if __name__ == "__main__":
    unittest.main()
