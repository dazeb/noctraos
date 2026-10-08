"""Open the real GTK window against a machine where nothing works and make sure no page raises.

Every page has a "not ready" state (no noc, no Ollama, no GPU tools, no Hermes); this proves it by
building the whole window under Xvfb with every external program missing, at 1x and 2x scale, and
by pressing the keyboard shortcuts. Skipped where PyGObject, GTK or Xvfb is not available (CI's
bare container), so it never fails for lack of a display.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

CONTROL = Path(__file__).resolve().parents[1] / "control"

DRIVER = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
import gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
import panel
for name in ("NOC", "GPU_BIN", "HERMES", "HELPER", "PKEXEC"):
    setattr(panel, name, "/nonexistent/" + name)
panel.FIXES = {k: ["/nonexistent/fix"] for k in panel.FIXES}
panel.OLLAMA_URL = "http://127.0.0.1:9"
import main

app = main.App()
app.register(None)
provider = Gtk.CssProvider(); provider.load_from_data(main.CSS)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
window = main.ControlPanel(app)
window.show_all()

def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.02)

def press(keyname, ctrl=False):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.window = window.get_window()
    event.keyval = Gdk.keyval_from_name(keyname)
    event.state = Gdk.ModifierType.CONTROL_MASK if ctrl else 0
    return window._on_key(window, event)

pump(1.5)
seen = []
for number, page_id in enumerate([p[0] for p in main.pages.PAGES], 1):
    assert press(str(number), ctrl=True), f"Ctrl+{number} not handled"
    pump(1.0)
    assert window.current_page() == page_id, (number, window.current_page(), page_id)
    assert press("r", ctrl=True), "Ctrl+R not handled"
    pump(1.0)
    seen.append(page_id)
assert not press("x", ctrl=True), "an unrelated key must pass through"
assert not press("9", ctrl=True), "Ctrl+9 has no page"
window.open_page("no-such-page")
print("PAGES", ",".join(seen))
'''


def have_display_stack():
    if not shutil.which("xvfb-run") or not Path("/usr/bin/python3").exists():
        return False
    probe = subprocess.run(["/usr/bin/python3", "-c", "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk"],
                           capture_output=True)
    return probe.returncode == 0


@unittest.skipUnless(have_display_stack(), "needs xvfb-run and system PyGObject/GTK 3")
class SmokeTests(unittest.TestCase):
    def run_driver(self, scale):
        env = {**os.environ, "GDK_SCALE": str(scale), "NO_AT_BRIDGE": "1"}
        return subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", "/usr/bin/python3", "-c", DRIVER, str(CONTROL)],
                              capture_output=True, text=True, env=env, timeout=180)

    def check(self, scale):
        result = self.run_driver(scale)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("PAGES overview,updates,apps,models,hardware,health,privacy,about", result.stdout)

    def test_every_page_survives_a_machine_where_nothing_works(self):
        self.check(1)

    def test_hidpi(self):
        self.check(2)


if __name__ == "__main__":
    unittest.main()
