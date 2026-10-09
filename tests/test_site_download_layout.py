"""The downloads table on site/download.html must fit the page, so the Download column (and the torrent button in it)
(the torrent button is in the second row) is never pushed off the right edge. Driven in a real headless Chrome when one is installed (skipped otherwise)."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

PROBE = """<script>addEventListener('load', function () {
  var box = document.querySelector('#files .scroll'), table = box.querySelector('table');
  var btn = table.querySelector('tbody tr:nth-child(2) td:last-child a'), r = btn.getBoundingClientRect(), b = box.getBoundingClientRect();
  document.title = 'table=' + table.scrollWidth + ' box=' + box.clientWidth + ' btnRight=' + Math.round(r.right) + ' boxRight=' + Math.round(b.right);
});</script></body>"""


class StaticTests(unittest.TestCase):
    def test_the_long_proxmox_command_can_wrap(self):
        # `.term-line code` is nowrap, so the wrapping rule must be at least as specific or the command widens the table
        css = (SITE / "style.css").read_text()
        self.assertRegex(css, r"\.term-line code\.wrap-code\s*\{[^}]*white-space:\s*normal")
        self.assertIn('class="wrap-code"', (SITE / "download.html").read_text())


@unittest.skipUnless(CHROME, "no Chrome/Chromium to drive")
class LayoutTests(unittest.TestCase):
    def measure(self, width):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / "site"
            shutil.copytree(SITE, site)
            page = site / "download.html"
            page.write_text(page.read_text().replace("</body>", PROBE))
            out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=3000",
                                  f"--window-size={width},900", "--dump-dom", f"file://{page}"],
                                 capture_output=True, text=True, timeout=60).stdout
        found = re.search(r"<title>table=(\d+) box=(\d+) btnRight=(\d+) boxRight=(\d+)", out)
        self.assertTrue(found, "the probe did not run")
        return [int(n) for n in found.groups()]

    def test_the_table_and_its_download_buttons_fit_on_desktop_and_laptop_widths(self):
        for width in (1280, 1024, 820):
            with self.subTest(width=width):
                table, box, button, edge = self.measure(width)
                self.assertLessEqual(table, box, "the table is wider than its box: the Download column is cut off")
                self.assertLessEqual(button, edge, "the torrent button is outside the table")


if __name__ == "__main__":
    unittest.main()
