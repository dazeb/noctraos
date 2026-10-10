"""AppImage and Flatpak prerequisites are installed by the core module, on every flavour.

Apps come from Flathub and AppImages, so the packages that let them run must not depend on the
desktop: FUSE 2 and FUSE 3 for AppImages, and every desktop's portal backend for Flatpak file
dialogs (docs/flavours.md, "What must stay identical"). Flatpak apps bring their own runtimes.
"""
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "install" / "01_system.sh"
PORTAL_PACKAGES = [
    "xdg-desktop-portal",
    "xdg-desktop-portal-gtk",
    "xdg-desktop-portal-gnome",
    "xdg-desktop-portal-kde",
]


class AppImageFlatpakPrereqTests(unittest.TestCase):
    def setUp(self):
        self.text = MODULE.read_text(encoding="utf-8")

    def test_fuse_packages_for_appimages(self):
        self.assertIn("for p in fuse3 libfuse2t64 libfuse2; do", self.text)

    def test_every_desktop_portal_backend_is_installed(self):
        loop = self.text.split("for p in xdg-desktop-portal ", 1)
        self.assertEqual(len(loop), 2, "the portal loop is missing from install/01_system.sh")
        header_line = "for p in " + " ".join(PORTAL_PACKAGES) + "; do"
        self.assertIn(header_line, self.text)

    def test_portal_failures_warn_and_do_not_abort(self):
        self.assertIn('warn "Flatpak portal failed to install: $p"', self.text)
        self.assertIn('warn "Flatpak portal not available in this release (skipped): $p"', self.text)


if __name__ == "__main__":
    unittest.main()
