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
for name in ("NOC", "GPU_BIN", "HERMES", "HELPER", "PKEXEC", "SEAHORSE"):
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
assert not press("0", ctrl=True), "Ctrl+0 is never a page"
assert len(seen) <= 9, "Ctrl+1..9 is all the digit shortcuts there are: add a different way to reach page 10"
window.open_page("no-such-page")

# The skip choice reaches the widgets: feed the Accounts and Hardware pages by hand (the helpers above are all missing).
pump(1.0)
accounts = window.pages["accounts"]
undone = {"git": {"installed": True, "name": "", "email": ""}, "github": {"installed": True, "signed_in": False, "login": ""}}
accounts._loaded((undone, []))
assert accounts.skip_git.get_visible() and accounts.skip_github.get_visible() and accounts.terminal_github.get_visible()
assert accounts.git_form.get_visible() and not accounts.git_skipped.get_visible() and not accounts.github_skipped.get_visible()
accounts._loaded((undone, ["github"]))
assert accounts.github_skipped.get_visible() and not accounts.skip_github.get_visible() and not accounts.signin.get_visible()
assert accounts.git_form.get_visible() and accounts.skip_git.get_visible()
accounts._loaded((undone, ["git", "github"]))
assert accounts.git_skipped.get_visible() and not accounts.git_form.get_visible()
assert "Nothing left" in accounts.headline.get_text(), accounts.headline.get_text()
done = {"git": {"installed": True, "name": "Ada", "email": "ada@example.com"}, "github": {"installed": True, "signed_in": True, "login": "ada"}}
accounts._loaded((done, ["git", "github"]))
assert not accounts.git_skipped.get_visible() and not accounts.github_skipped.get_visible() and not accounts.skip_git.get_visible()
assert accounts.signout.get_visible() and not accounts.skip_github.get_visible()
hardware = window.pages["hardware"]
gpu = {"gpus": [{"name": "X", "vendor": "nvidia", "tier": "modern"}], "plan": {"nvidia": "modern"}}
hardware._loaded((gpu, {"ready": False, "rows": []}, None, []))
assert hardware.setup.get_visible() and hardware.skip.get_visible() and hardware.unskip is None
hardware._loaded((gpu, {"ready": False, "rows": []}, None, ["gpu"]))
assert not hardware.setup.get_visible() and not hardware.skip.get_visible() and hardware.unskip is not None
# The setup checklist on the Overview: what is left gets a row and a button, finished steps are only counted.
overview = window.pages["overview"]
status = {"version": "1", "ollama": {"running": True, "models": 1, "default_model": "m"}, "hermes": {"installed": True, "mode": "cloud"},
          "accounts": undone, "skipped": ["github"], "gpu": gpu}
overview._loaded((status, {"gpu_status": {"ready": False, "rows": []}, "onboarded": False, "weather_city": ""}))
def texts(widget, found):
    if isinstance(widget, (Gtk.Label, Gtk.Button)):
        found.append(widget.get_text() if isinstance(widget, Gtk.Label) else widget.get_label())
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            texts(child, found)
    return found
shown = texts(overview, [])
for want in ("3 things left to set up", "Git name and e-mail", "GitHub sign-in", "GPU for local AI", "Meet Hermes", "Open Hermes", "Pick a city"):
    assert want in shown, (want, shown)
overview._loaded((None, {}))
# The NoctraOS update section: the installed update, the channel that is chosen, and Go back only when there is something to go back to.
updates = window.pages["updates"]
layer = {"channel": "nightly", "serial": 4, "version": "1.0", "applied": "2026-10-09T10:00:00Z", "can_rollback": True,
         "held": 0, "failed_migrations": ["0002_x.sh"], "signing_key": True}
updates._layer_loaded(layer)
assert updates.layer.get_visible() and "update 4" in updates.layer_head.get_text()
assert updates.channel_radios["nightly"].get_active() and not updates.channel_radios["stable"].get_active()
assert updates.rollback.get_visible() and updates.layer_problem.get_visible() and "0002_x.sh" in updates.layer_problem.get_text()
updates._layer_loaded({**layer, "channel": "stable", "can_rollback": False, "failed_migrations": []})
assert updates.channel_radios["stable"].get_active() and not updates.rollback.get_visible() and not updates.layer_problem.get_visible()
updates._layer_loaded(None)
assert updates.layer.get_visible() and not updates.channel_radios["stable"].get_visible() and not updates.rollback.get_visible()
# Privacy: remote login, clipboard history and saved passwords each show their state, and a button only where it can act.
privacy = window.pages["privacy"]
assert not privacy.remote_button.get_visible() and not privacy.clip_button.get_visible() and not privacy.key_button.get_visible()
seen_state = {"hermes": None, "remote": "on", "clipboard": {"installed": True, "running": True, "count": 4},
              "keyring": "unprotected", "can_open_keyring": True}
privacy._loaded(seen_state)
assert privacy.remote_button.get_visible() and privacy.remote_button.get_label() == "Turn off remote login"
assert privacy.clip_button.get_visible() and privacy.clip_head.get_text() == "4 copies saved"
assert privacy.key_button.get_visible() and "not locked" in privacy.key_head.get_text()
privacy._loaded({**seen_state, "remote": "off", "clipboard": {"installed": True, "running": True, "count": 0}, "keyring": "protected"})
assert privacy.remote_button.get_label() == "Turn on remote login"
assert not privacy.clip_button.get_visible() and not privacy.key_button.get_visible()
privacy._loaded({**seen_state, "remote": None, "clipboard": {"installed": False}, "keyring": None, "can_open_keyring": False})
assert not privacy.remote_button.get_visible() and not privacy.clip_button.get_visible() and not privacy.key_button.get_visible()
# AI models without a running Ollama: never set up gets the offer, installed-but-silent and unreadable do not.
models = window.pages["models"]
never = {"ollama": {"installed": False, "running": False}, "gpu": gpu, "ram_gb": 16, "disk": {"root_free_bytes": 50 * 2**30}}
models._loaded((None, None, never))
assert models.setup_button is not None and models.setup_button.get_label() == "Set up local AI…"
assert "Local AI is not set up" in texts(models.holder, [])
# The engine row. Stopped and not meant to start with the computer is the normal state after the setup: a plain Start, no alarm.
models._loaded((None, None, {**never, "ollama": {"installed": True, "running": False, "autostart": False}}))
shown = texts(models.holder, [])
assert models.setup_button is None and "Ollama is off" in shown and "Start Ollama" in shown and "Start with this computer" in shown, shown
models._loaded((None, None, {**never, "ollama": {"installed": True, "running": False, "autostart": True}}))
shown = texts(models.holder, [])
assert "Ollama is not running" in shown and "Do not start with this computer" in shown and "Start Ollama" in shown, shown
models._loaded(({"ollama": True, "autostart": False, "default": "m", "models": []}, None, None))
shown = texts(models.holder, [])
assert "Ollama is running" in shown and "Stop Ollama" in shown and "Start with this computer" in shown, shown
models._loaded(({"ollama": True, "autostart": None, "default": "m", "models": []}, None, None))
shown = texts(models.holder, [])
assert "Stop Ollama" in shown and "Start with this computer" not in shown and "Do not start with this computer" not in shown, shown
# Pressing the buttons runs the fixed helper verbs and refreshes. A helper that is missing says so instead of raising.
ran_engine = []
panel.run_ok = lambda argv, timeout=120: (ran_engine.append(argv), (True, ""))[1]
panel.wait_for_ollama = lambda *a, **k: True
models._loaded((None, None, {**never, "ollama": {"installed": True, "running": False, "autostart": False}}))
models._engine_service("start", False)
pump(1.0)
assert ran_engine == [[panel.PKEXEC, panel.HELPER, "ollama-service", "start"]], ran_engine
assert "Ollama is running" in models.note.get_text(), models.note.get_text()
models._engine_boot("on", False)
pump(1.0)
assert ran_engine[-1] == [panel.PKEXEC, panel.HELPER, "ollama-autostart", "on"], ran_engine
assert "starts with this computer" in models.note.get_text(), models.note.get_text()
models._engine_service("start", True)    # it is running already: nothing to do
models._engine_boot("on", True)          # it starts with the computer already: nothing to do
pump(0.5)
assert len(ran_engine) == 2, ran_engine
panel.run_ok = lambda argv, timeout=120: (False, "polkit said no")
models._engine_service("stop", True)
pump(1.0)
assert "Could not stop Ollama: polkit said no" in models.note.get_text(), models.note.get_text()
models._loaded((None, None, None))
assert models.setup_button is None and any("Could not check" in t for t in texts(models.holder, []))
# Pressing Set up: the summary dialog (answered yes here), then the helper's module through the allowlisted verb, then the result.
models._loaded((None, None, never))
asked, ran = [], []
def fake_dialog(self):
    asked.append(self.get_property("secondary-text"))
    return Gtk.ResponseType.OK
Gtk.MessageDialog.run = fake_dialog
def fake_events(argv):
    ran.append(argv)
    yield {"event": "log", "line": "Installing Ollama (official installer)..."}
    yield {"event": "log", "line": "REBOOT REQUIRED: the GPU driver was installed"}
    yield {"event": "exit", "code": 0}
panel.run_events = fake_events
models.setup_button.clicked()
pump(1.5)
assert ran == [panel.LOCAL_AI_SETUP], ran
assert len(asked) == 1 and "No model is downloaded yet" in asked[0] and "NVIDIA" in asked[0], asked
assert not models.running and not models.run.get_visible(), "a finished setup hides its progress"
assert "Restart the computer" in models.note.get_text(), models.note.get_text()
# A failed setup keeps its log open and says so.
def failing_events(argv):
    yield {"event": "log", "line": "something broke"}
    yield {"event": "exit", "code": 1}
panel.run_events = failing_events
models._loaded((None, None, never))
models.setup_button.clicked()
pump(1.5)
assert models.run.get_visible() and "did not finish" in models.run.label.get_text() and "did not finish" in models.note.get_text()
# Too little disk: the dialog only offers Cancel, so nothing runs.
tight = {**never, "disk": {"root_free_bytes": 2 * 2**30}}
models._loaded((None, None, tight))
asked.clear(); ran.clear()
buttons = []
Gtk.MessageDialog.run = lambda self: (asked.append(self.get_property("secondary-text")), Gtk.ResponseType.CANCEL)[1]
models.setup_button.clicked()
pump(0.5)
assert ran == [] and "Not enough free disk space" in asked[0], (ran, asked)
for page_id in ("updates", "apps", "models", "hardware", "health", "privacy", "accounts"):
    page = window.pages[page_id]
    tips = []
    def walk(widget):
        if isinstance(widget, Gtk.Button) and widget.get_style_context().has_class("terminal"):
            tips.append(widget.get_tooltip_text())
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                walk(child)
    walk(page)
    assert tips and all(t.startswith("In a terminal:") for t in tips), (page_id, tips)
print("PAGES", ",".join(seen))
'''


def gtk_python():
    """The first system Python whose PyGObject loads GTK 3. Ubuntu's python3-gi is built for the distro's default python3,
    which is not always /usr/bin/python3 (where that is 3.13, the bindings exist only for 3.12)."""
    if not shutil.which("xvfb-run"):
        return None
    for py in ("/usr/bin/python3", "/usr/bin/python3.12"):
        if not Path(py).exists():
            continue
        probe = subprocess.run([py, "-c", "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk"],
                               capture_output=True)
        if probe.returncode == 0:
            return py
    return None


GTK_PYTHON = gtk_python()


@unittest.skipUnless(GTK_PYTHON, "needs xvfb-run and system PyGObject/GTK 3")
class SmokeTests(unittest.TestCase):
    def run_driver(self, scale):
        env = {**os.environ, "GDK_SCALE": str(scale), "NO_AT_BRIDGE": "1"}
        return subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", GTK_PYTHON, "-c", DRIVER, str(CONTROL)],
                              capture_output=True, text=True, env=env, timeout=180)

    def check(self, scale):
        result = self.run_driver(scale)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("PAGES overview,accounts,updates,apps,models,hardware,health,privacy,about", result.stdout)

    def test_every_page_survives_a_machine_where_nothing_works(self):
        self.check(1)

    def test_hidpi(self):
        self.check(2)


if __name__ == "__main__":
    unittest.main()
