"""The installer slideshow page (assets/boot/installer/welcome.html): Super+Space stays the first page, every page has a
title, and the product names the later pages mention exist in the repository."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "assets/boot/installer/welcome.html").read_text()
PAGES = re.findall(r'<div class="pg( on)?" data-title="([^"]+)">(.*?)\n  </div>\n(?=\n  <div class="pg"|</div>\n<script>)', HTML, re.S)


def chips(page):
    return re.findall(r'<span class="key">([^<]+)</span>', page)


class InstallerSlidesTests(unittest.TestCase):
    def test_super_space_is_the_first_and_only_page_shown_without_script(self):
        self.assertGreater(len(PAGES), 1)
        self.assertEqual([on for on, _, _ in PAGES], [" on"] + [""] * (len(PAGES) - 1))
        first = PAGES[0][2]
        self.assertIn('aria-label="Windows key"', first)
        self.assertIn('aria-label="Command key"', first)
        self.assertIn(">Space<", first)

    def test_every_page_has_its_own_title(self):
        titles = [title for _, title, _ in PAGES]
        self.assertEqual(len(set(titles)), len(titles))

    def test_the_control_panel_page_names_real_pages(self):
        titles = set(re.findall(r"\('\w+', '([^']+)', \w+Page\)", (ROOT / "control/pages.py").read_text()))
        panel = next(page for _, title, page in PAGES if "Control Panel" in title)
        for name in chips(panel):
            self.assertIn(name, titles)

    def test_the_assistants_page_names_real_launchers(self):
        launchers = {m for f in (ROOT / "configs/applications").glob("noctraos-*.desktop")
                     for m in re.findall(r"^Name=(.+)$", f.read_text(), re.M)}
        page = next(page for _, title, page in PAGES if "assistants" in title)
        for name in chips(page):
            self.assertIn(name, launchers)

    def test_the_right_click_page_names_real_scripts(self):
        scripts = {p.name for p in (ROOT / "configs/nautilus-scripts").iterdir()}
        page = next(page for _, title, page in PAGES if "Right-click" in title)
        for name in chips(page):
            self.assertIn(name, scripts)


if __name__ == "__main__":
    unittest.main()
