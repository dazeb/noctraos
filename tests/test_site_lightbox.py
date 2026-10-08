"""The screenshot lightbox (site/script.js + site/style.css). Static checks always run; the behaviour is driven in a real
headless Chrome when one is installed (skipped otherwise, like the GTK smoke test)."""
import html
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

SHOT = re.compile(r'<figure class="shot[^"]*"><a href="([^"]+)"[^>]*><img src="([^"]+)" alt="([^"]*)"')


def pages_with_shots():
    return [(p, SHOT.findall(p.read_text())) for p in sorted(SITE.glob("*.html")) if '<figure class="shot' in p.read_text()]


class StaticTests(unittest.TestCase):
    def test_every_screenshot_links_to_an_existing_full_size_image_and_has_alt_text(self):
        pages = pages_with_shots()
        self.assertTrue(pages)
        for page, shots in pages:
            self.assertEqual(len(shots), page.read_text().count('<figure class="shot'), f"{page.name}: a figure.shot has unexpected markup")
            for full, thumb, alt in shots:
                with self.subTest(page=page.name, full=full):
                    self.assertTrue((SITE / full).is_file(), full)
                    self.assertTrue((SITE / thumb).is_file(), thumb)
                    self.assertGreater(len(alt.strip()), 10, "the lightbox caption falls back to the alt text")

    def test_every_page_with_screenshots_loads_the_script_and_the_styles(self):
        for page, _ in pages_with_shots():
            text = page.read_text()
            self.assertIn('<script src="script.js"></script>', text, page.name)
            self.assertIn('href="style.css"', text, page.name)

    def test_it_is_an_enhancement_only(self):
        js = (SITE / "script.js").read_text()
        self.assertIn('typeof probe.showModal !== "function"', js)       # no <dialog>: leave the links alone
        self.assertIn("metaKey", js)                                      # open-in-new-tab keeps working
        css = (SITE / "style.css").read_text()
        self.assertIn(".lb-ready .shot a", css)                           # hover/zoom cursor only once the script is active
        self.assertIn("prefers-reduced-motion", css[css.index("dialog.lb"):])
        self.assertNotIn("http://", js + css.replace("http://www.w3.org", ""))


@unittest.skipUnless(CHROME, "no Chrome/Chromium to drive")
class BrowserTests(unittest.TestCase):
    SCENARIO = r"""
    var $ = function (s) { return document.querySelector(s); };
    var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var d, links = document.querySelectorAll('.shot > a'), log = [];
    function check(name, ok) { log.push((ok ? 'PASS ' : 'FAIL ') + name); }
    function key(k) { d.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })); }
    try {
      d = $('dialog.lb');
      check('enhancement is active', document.documentElement.classList.contains('lb-ready') && !!d);
      var first = links[0]; first.focus(); first.click(); await wait(800);
      check('click opens the viewer', d.open);
      check('it shows the full-size image', $('.lb-stage img').src.indexOf('/full/') > 0);
      check('the counter starts at 1', $('.lb-count').textContent === '1 / ' + links.length);
      check('the caption is the figure text', $('.lb-cap').textContent.length > 5);
      check('the page behind is locked', document.documentElement.classList.contains('lb-open'));
      check('the image is revealed', $('.lb-stage img').classList.contains('ready'));
      key('ArrowRight'); await wait(200);
      check('right arrow goes to 2', $('.lb-count').textContent === '2 / ' + links.length);
      key('ArrowLeft'); key('ArrowLeft'); await wait(200);
      check('left from 1 wraps to the last', $('.lb-count').textContent === links.length + ' / ' + links.length);
      key('Home'); await wait(200);
      check('Home goes to 1', $('.lb-count').textContent === '1 / ' + links.length);
      key('z'); await wait(300);
      check('Z zooms to actual size', d.classList.contains('zoomed') && $('.lb-zoom').getAttribute('aria-pressed') === 'true');
      check('the zoomed image is its natural width', $('.lb-stage img').clientWidth === $('.lb-stage img').naturalWidth);   // layout width: the pop-in transform must not count
      $('.lb-stage img').click(); await wait(300);
      check('clicking the image zooms back out', !d.classList.contains('zoomed'));
      $('.lb-close').click(); await wait(300);
      check('close closes', !d.open);
      check('close unlocks the page', !document.documentElement.classList.contains('lb-open'));
      check('focus returns to the screenshot link', document.activeElement === first);
      first.click(); await wait(300); d.click(); await wait(200);
      check('a click outside the image closes', !d.open);
      var ev = new MouseEvent('click', { ctrlKey: true, bubbles: true, cancelable: true });
      var prevented = !first.dispatchEvent(ev); await wait(200);
      check('ctrl-click is left to the browser', !prevented && !d.open);
    } catch (e) { log.push('FAIL exception: ' + e.message); }
    var pre = document.createElement('pre'); pre.id = 'testlog'; pre.textContent = log.join('\n'); document.body.appendChild(pre);
    """

    def test_the_viewer_behaves_in_a_real_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            shutil.copytree(SITE, site)
            page = (site / "features.html").read_text().replace(
                "</body>", "<script>window.addEventListener('load', function () { setTimeout(async function () {"
                + self.SCENARIO + "}, 300); });</script></body>", 1)
            (site / "t.html").write_text(page)
            out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=1280,800",
                                  "--virtual-time-budget=15000", "--dump-dom", f"file://{site}/t.html"],
                                 capture_output=True, text=True, timeout=120).stdout
        m = re.search(r'<pre id="testlog">(.*?)</pre>', out, re.S)
        self.assertIsNotNone(m, "the test script did not run")
        lines = html.unescape(m.group(1)).splitlines()
        failures = [l for l in lines if l.startswith("FAIL")]
        self.assertGreaterEqual(len([l for l in lines if l.startswith("PASS")]), 15)
        self.assertEqual(failures, [], "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
