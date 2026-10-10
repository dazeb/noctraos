"""Flavour rules for install modules (docs/flavours.md, rules 5 and 6).

A module whose code touches a desktop (GNOME or Plasma, or a Zorin or Kubuntu name) must declare
which desktop it is for, on its second line, as `# desktops: any|gnome|plasma`. A module that
declares `gnome` must call desktop_is_gnome and print NOT APPLIED on other desktops, so a skipped
step is never reported as a success.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted((ROOT / "install").glob("[0-9]*.sh"))

# Code (not comments) that touches a desktop, a desktop's settings, or a base's name.
COUPLED = re.compile(
    r"gsettings|dconf-|gnome-|nautilus|org\.gnome\.(desktop|shell|nautilus|settings)|kwriteconfig6|plasma|kwin|dolphin|zorin",
    re.I,
)
HEADER = re.compile(r"^# desktops: (any|gnome|plasma)$")


def code_lines(text):
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def second_line(text):
    lines = text.splitlines()
    return lines[1] if len(lines) > 1 else ""


class FlavourHeaderTests(unittest.TestCase):
    def test_desktop_coupled_modules_declare_their_desktop(self):
        missing = []
        for path in MODULES:
            text = path.read_text(encoding="utf-8")
            if any(COUPLED.search(line) for line in code_lines(text)) and not HEADER.match(second_line(text)):
                missing.append(path.name)
        self.assertEqual(
            missing, [],
            "these modules touch a desktop and need '# desktops: any|gnome|plasma' on line 2 (docs/flavours.md)",
        )

    def test_gnome_modules_guard_themselves(self):
        unguarded = []
        for path in MODULES:
            text = path.read_text(encoding="utf-8")
            if second_line(text) == "# desktops: gnome":
                if "desktop_is_gnome" not in text or "NOT APPLIED" not in text:
                    unguarded.append(path.name)
        self.assertEqual(
            unguarded, [],
            "gnome modules must call desktop_is_gnome and print NOT APPLIED off GNOME (docs/flavours.md, rule 6)",
        )


if __name__ == "__main__":
    unittest.main()
